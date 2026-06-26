import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from dateutil import parser as dateparser

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson"
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
NHC_GIS_FEEDS = {
    "Atlantic": "https://www.nhc.noaa.gov/gis-at.xml",
    "Eastern Pacific": "https://www.nhc.noaa.gov/gis-ep.xml",
    "Central Pacific": "https://www.nhc.noaa.gov/gis-cp.xml",
}

STATE_FILE = Path(".catwatch_alert_state.json")
MAX_ALERTS_PER_RUN = int(os.getenv("CATWATCH_MAX_ALERTS", "8"))
# Prevent old feed items/backlog from being announced as new events.
# A genuinely new event must be recent; an old event can still alert later if the source update is recent.
NEW_EVENT_MAX_AGE_HOURS = int(os.getenv("CATWATCH_NEW_EVENT_MAX_AGE_HOURS", "6"))
UPDATE_MAX_AGE_HOURS = int(os.getenv("CATWATCH_UPDATE_MAX_AGE_HOURS", "12"))
STATE_SCHEMA_VERSION = 2


def utc_now():
    return datetime.now(timezone.utc)


def now_text():
    return utc_now().strftime("%Y-%m-%d %H:%M UTC")


def parse_dt(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = dateparser.parse(str(value))
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def dt_text(dt):
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "Unknown"


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text or ""))).strip()


def norm_key(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")


def stable_hash(text):
    return hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()[:16]


def age_hours(dt):
    if not dt:
        return None
    try:
        return max(0, (utc_now() - dt).total_seconds() / 3600)
    except Exception:
        return None


def event_reference_dt(event):
    return event.get("latest_update_dt") or event.get("event_time")


def is_recent(event, max_hours):
    age = age_hours(event_reference_dt(event))
    return age is not None and age <= max_hours


def extract_gdacs_country(title):
    text = clean(title)
    # Examples: "... in Venezuela 24/06/2026 22:05 UTC, ..."
    m = re.search(r"\bin\s+([A-Za-z][A-Za-z .'-]*?)\s+\d{1,2}/\d{1,2}/\d{4}", text)
    if m:
        return m.group(1).strip()
    return extract_country(text)


def extract_gdacs_event_hour(title):
    text = clean(title)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):", text)
    if not m:
        return ""
    day, month, year, hour = m.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T{int(hour):02d}"


def gdacs_event_id(title, link, peril):
    text = clean(title)
    # Prefer official GDACS query identifiers when present.
    m = re.search(r"(?:eventid|eventid=|event_id=)([A-Za-z0-9_.-]+)", str(link), flags=re.I)
    if m:
        return f"GDACS-{norm_key(peril)}-{m.group(1)}"
    country = extract_gdacs_country(text)
    hour = extract_gdacs_event_hour(text)
    if peril == "Earthquake" and country != "Unknown" and hour:
        # Groups GDACS revisions of the same quake, e.g. M7.2 -> M7.5, as one incident.
        return f"GDACS-earthquake-{norm_key(country)}-{hour}"
    compact = re.sub(r"magnitude\s*[:=]?\s*\d+(?:\.\d+)?m?", "magnitude", text, flags=re.I)
    compact = re.sub(r"depth\s*[:=]?\s*\d+(?:\.\d+)?\s*km", "depth", compact, flags=re.I)
    compact = re.sub(r"\d+(?:\.\d+)?\s*(?:thousand|million|billion)", "population", compact, flags=re.I)
    return f"GDACS-{stable_hash(compact + '|' + str(link))}"


def short(text, n=240):
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def extract_country(location_text):
    text = str(location_text or "").strip()
    if not text:
        return "Unknown"
    if "," in text:
        return text.split(",")[-1].strip()
    low = text.lower()
    for marker in [" in ", " near ", " of "]:
        if marker in low:
            return text[low.rfind(marker) + len(marker):].strip().title()
    return text


def infer_peril(text):
    t = str(text).lower()
    pairs = [
        ("earthquake", "Earthquake"),
        ("tropical cyclone", "Tropical Cyclone"),
        ("hurricane", "Tropical Cyclone"),
        ("typhoon", "Tropical Cyclone"),
        ("cyclone", "Tropical Cyclone"),
        ("flood", "Flood"),
        ("wildfire", "Wildfire"),
        ("fire", "Wildfire"),
        ("volcano", "Volcano"),
        ("tsunami", "Tsunami"),
        ("landslide", "Landslide"),
        ("storm", "Severe Storm"),
        ("hail", "Severe Storm"),
        ("tornado", "Severe Storm"),
        ("drought", "Drought"),
    ]
    for k, v in pairs:
        if k in t:
            return v
    return "Other"


def severity_rank(sev):
    return {"Critical": 6, "Red": 5, "Orange": 4, "Amber": 3, "Yellow": 2, "Green": 1, "Unknown": 0}.get(str(sev), 0)


def tier_rank(tier):
    return {"P1": 4, "P2": 3, "P3": 2, "P4": 1}.get(str(tier), 0)


def eq_severity(mag):
    mag = safe_float(mag)
    if mag is None:
        return "Unknown"
    if mag >= 7.5:
        return "Critical"
    if mag >= 6.5:
        return "Red"
    if mag >= 5.5:
        return "Amber"
    return "Green"


def gdacs_severity(title, summary):
    text = f" {title} {summary} ".lower()
    if " red " in text:
        return "Red"
    if " orange " in text:
        return "Orange"
    if " yellow " in text:
        return "Yellow"
    if " green " in text:
        return "Green"
    return "Unknown"


def notification_tier(sev, peril, intensity=""):
    combined = f"{sev} {peril} {intensity}".lower()
    if sev in {"Critical", "Red"}:
        return "P1"
    if "category 4" in combined or "category 5" in combined:
        return "P1"
    if sev in {"Orange", "Amber"}:
        return "P2"
    if sev in {"Yellow", "Green"}:
        return "P3"
    return "P4"


def tier_label(tier):
    return {"P1": "P1 Executive", "P2": "P2 Analyst Watch", "P3": "P3 Monitor", "P4": "P4 Info"}.get(str(tier), "P4 Info")


def severity_symbol(sev):
    return {"Critical": "🔴", "Red": "🔴", "Orange": "🟠", "Amber": "🟡", "Yellow": "🟡", "Green": "🟢", "Unknown": "⚪"}.get(str(sev), "⚪")


def peril_symbol(peril):
    return {"Earthquake": "🌎", "Tropical Cyclone": "🌀", "Flood": "🌊", "Wildfire": "🔥", "Volcano": "🌋", "Tsunami": "🌊", "Landslide": "⛰️", "Severe Storm": "⛈️", "Drought": "☀️", "Other": "📍"}.get(str(peril), "📍")


def expected_impact(peril, severity, intensity=""):
    p = str(peril)
    s = str(severity)
    text = str(intensity or "").lower()
    if p == "Earthquake":
        if s in {"Critical", "Red"}:
            return "Expect aftershocks, building-damage reports, possible casualties, utility / transport disruption, and later insured-loss commentary. Check ShakeMap if available."
        return "Monitor aftershocks, local damage reports, and utility / transport disruption near the epicentre."
    if p == "Tropical Cyclone":
        if "category 4" in text or "category 5" in text or s in {"Critical", "Red"}:
            return "Expect destructive wind, surge, heavy rain, inland flooding, power outages, transport disruption, and fast-changing exposure relevance."
        return "Expect track changes, rainfall/flood risk, warning changes, and impacts beyond the center track."
    if p == "Flood":
        return "Expect road closures, evacuation activity, infrastructure disruption, property damage, and later economic / insured-loss estimates."
    if p == "Wildfire":
        return "Expect perimeter changes, evacuation orders, smoke impacts, property loss potential, and later claims development."
    if p == "Volcano":
        return "Expect ashfall, aviation disruption, exclusion-zone updates, and possible secondary hazards depending on volcano behaviour."
    if p == "Severe Storm":
        return "Expect wind, hail, tornado, flood or power-disruption reports with rapid local escalation or de-escalation."
    return "Monitor official source updates, verified news, casualty reports, and public loss commentary."


def impact_region(peril, location, country):
    if peril == "Tropical Cyclone":
        return "Use advisory track, cone, wind field, rainfall and surge zones. Impact area is wider than the storm center."
    if peril == "Earthquake":
        return "Epicentre is not the full footprint. Use USGS ShakeMap for shaking-intensity extent where available."
    if peril == "Wildfire":
        return "Use active fire detections and perimeter products when available; point location is not the full footprint."
    if peril == "Flood":
        return "Flood footprint may extend across a river basin or urban area, not just the reported point."
    return f"Primary reported area: {location or country or 'Unknown'}."


def category_from_wind(wind_text):
    txt = str(wind_text or "")
    m = re.search(r"(\d{2,3})\s*(?:kt|kts|knots)", txt, flags=re.I)
    if not m:
        return ""
    kt = int(m.group(1))
    mph = kt * 1.15078
    if mph >= 157:
        return "Category 5"
    if mph >= 130:
        return "Category 4"
    if mph >= 111:
        return "Category 3"
    if mph >= 96:
        return "Category 2"
    if mph >= 74:
        return "Category 1"
    if mph >= 39:
        return "Tropical Storm"
    return "Tropical Depression"


def get_entry_attr(entry, *names):
    for name in names:
        if hasattr(entry, name):
            val = getattr(entry, name)
            if val:
                return val
        try:
            val = entry.get(name)
            if val:
                return val
        except Exception:
            pass
    return ""


def update_key(event):
    return " | ".join(str(x) for x in [event.get("latest_update", ""), event.get("severity", ""), event.get("tier", ""), event.get("intensity", "")])


def alert_sort_key(e):
    return ({"ESCALATION": 5, "NEW EVENT": 4, "EVENT UPDATE": 3}.get(e.get("alert_action", ""), 0), tier_rank(e.get("tier")), severity_rank(e.get("severity")), e.get("event_time") or datetime.min.replace(tzinfo=timezone.utc))


def is_alertable(event):
    if event.get("tier") in {"P1", "P2"}:
        return True
    if event.get("source") == "NOAA/NHC":
        return True
    if event.get("peril") in {"Tropical Cyclone", "Earthquake"} and severity_rank(event.get("severity")) >= 3:
        return True
    if event.get("source") == "GDACS" and event.get("severity") in {"Red", "Orange", "Yellow"}:
        return True
    return False


def fetch_usgs_events():
    events = []
    try:
        data = requests.get(USGS_URL, timeout=25).json()
        for feature in data.get("features", []):
            props = feature.get("properties", {}) or {}
            geom = feature.get("geometry", {}) or {}
            coords = geom.get("coordinates", [None, None, None])
            mag = props.get("mag")
            place = props.get("place") or "Unknown location"
            event_dt = parse_dt(props.get("time"))
            updated_dt = parse_dt(props.get("updated"))
            severity = eq_severity(mag)
            peril = "Earthquake"
            intensity = f"Magnitude {mag}; depth {coords[2] if len(coords) > 2 else 'Unknown'} km"
            tier = notification_tier(severity, peril, intensity)
            events.append({"id": f"USGS-{feature.get('id')}", "name": f"M{mag} earthquake – {place}", "peril": peril, "severity": severity, "tier": tier, "country": extract_country(place), "region": place, "intensity": intensity, "event_time": event_dt, "latest_update_dt": updated_dt, "latest_update": dt_text(updated_dt or event_dt), "source": "USGS", "link": props.get("url", ""), "what_to_expect": expected_impact(peril, severity, intensity), "impact_region": impact_region(peril, place, extract_country(place))})
    except Exception as exc:
        print(f"USGS fetch failed: {exc}")
    return events


def fetch_gdacs_events():
    events = []
    try:
        feed = feedparser.parse(GDACS_RSS_URL)
        for entry in feed.entries[:60]:
            title = getattr(entry, "title", "GDACS event")
            summary = clean(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            event_dt = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
            updated_dt = parse_dt(getattr(entry, "updated", None))
            severity = gdacs_severity(title, summary)
            peril = infer_peril(title + " " + summary)
            tier = notification_tier(severity, peril, summary)
            country = extract_gdacs_country(title)
            events.append({"id": gdacs_event_id(title, link, peril), "name": title, "peril": peril, "severity": severity, "tier": tier, "country": country, "region": country, "intensity": short(summary, 200) or "See GDACS alert details", "event_time": event_dt, "latest_update_dt": updated_dt, "latest_update": dt_text(updated_dt or event_dt), "source": "GDACS", "link": link, "what_to_expect": expected_impact(peril, severity, summary), "impact_region": impact_region(peril, country, country)})
    except Exception as exc:
        print(f"GDACS fetch failed: {exc}")
    return events


def fetch_nhc_events():
    events = []
    for basin, url in NHC_GIS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = clean(getattr(entry, "title", ""))
                if "summary" not in title.lower():
                    continue
                summary = clean(getattr(entry, "summary", ""))
                link = getattr(entry, "link", "")
                event_dt = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
                updated_dt = parse_dt(getattr(entry, "updated", None))
                storm_type = get_entry_attr(entry, "nhc_type", "type")
                name = get_entry_attr(entry, "nhc_name", "name")
                movement = get_entry_attr(entry, "nhc_movement", "movement")
                pressure = get_entry_attr(entry, "nhc_pressure", "pressure")
                wind = get_entry_attr(entry, "nhc_wind", "wind")
                if not name and " - " in title:
                    right = title.split(" - ", 1)[1]
                    right = re.sub(r"\([^)]*\)", "", right).strip()
                    name = re.sub(r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)\s+", "", right, flags=re.I).strip()
                    if not storm_type:
                        m = re.match(r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)", right, flags=re.I)
                        storm_type = m.group(1) if m else "Tropical Cyclone"
                category = category_from_wind(wind) or storm_type or "Tropical Cyclone"
                intensity = "; ".join([x for x in [category, f"Wind {wind}" if wind else "", f"Pressure {pressure}" if pressure else "", f"Movement {movement}" if movement else ""] if x]) or summary or "NHC tropical cyclone summary"
                severity = "Red" if "category 4" in intensity.lower() or "category 5" in intensity.lower() else "Orange" if "hurricane" in intensity.lower() else "Amber"
                peril = "Tropical Cyclone"
                tier = notification_tier(severity, peril, intensity)
                display = " ".join([str(storm_type or "Tropical Cyclone").strip(), str(name or "").strip()]).strip() or title
                events.append({"id": f"NHC-{basin}-{display}", "name": display, "peril": peril, "severity": severity, "tier": tier, "country": basin, "region": basin, "intensity": intensity, "event_time": event_dt, "latest_update_dt": updated_dt, "latest_update": dt_text(updated_dt or event_dt), "source": "NOAA/NHC", "link": link or url, "what_to_expect": expected_impact(peril, severity, intensity), "impact_region": impact_region(peril, basin, basin)})
        except Exception as exc:
            print(f"NHC fetch failed for {basin}: {exc}")
    return events


def fetch_all_events():
    events = []
    events.extend(fetch_usgs_events())
    events.extend(fetch_gdacs_events())
    events.extend(fetch_nhc_events())
    by_id = {}
    for e in events:
        if not e.get("id"):
            continue
        old = by_id.get(e["id"])
        if old is None:
            by_id[e["id"]] = e
            continue
        # Keep the most severe / most recently updated revision for the same incident.
        old_key = (severity_rank(old.get("severity")), tier_rank(old.get("tier")), event_reference_dt(old) or datetime.min.replace(tzinfo=timezone.utc))
        new_key = (severity_rank(e.get("severity")), tier_rank(e.get("tier")), event_reference_dt(e) or datetime.min.replace(tzinfo=timezone.utc))
        if new_key >= old_key:
            by_id[e["id"]] = e
    return list(by_id.values())


def load_state():
    if not STATE_FILE.exists():
        return {"created": now_text(), "events": {}, "initialized": False, "schema_version": STATE_SCHEMA_VERSION}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state.setdefault("events", {})
        state.setdefault("initialized", False)
        return state
    except Exception:
        return {"created": now_text(), "events": {}, "initialized": False, "schema_version": STATE_SCHEMA_VERSION}


def save_state(state):
    state["last_run"] = now_text()
    state["schema_version"] = STATE_SCHEMA_VERSION
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def build_alerts(events, state):
    state_events = state.setdefault("events", {})
    first_run = not state.get("initialized", False)
    migration_run = state.get("schema_version") != STATE_SCHEMA_VERSION
    alerts = []
    skipped_old_new = 0
    skipped_stale_update = 0
    for e in events:
        if not is_alertable(e):
            continue
        key = update_key(e)
        old = state_events.get(e["id"])
        if old is None:
            e["alert_action"] = "NEW EVENT"
            # Do not alert on backlog or after state-schema migration. Save it silently.
            if not first_run and not migration_run and is_recent(e, NEW_EVENT_MAX_AGE_HOURS):
                alerts.append(e)
            elif not first_run and not migration_run:
                skipped_old_new += 1
        else:
            changed = key != old.get("update_key", "")
            escalated = severity_rank(e["severity"]) > int(old.get("severity_rank", 0)) or tier_rank(e["tier"]) > int(old.get("tier_rank", 0))
            if (changed or escalated) and not migration_run:
                if is_recent(e, UPDATE_MAX_AGE_HOURS):
                    e["alert_action"] = "ESCALATION" if escalated else "EVENT UPDATE"
                    alerts.append(e)
                else:
                    skipped_stale_update += 1
        state_events[e["id"]] = {"name": e["name"], "peril": e["peril"], "severity": e["severity"], "tier": e["tier"], "source": e["source"], "latest_update": e["latest_update"], "update_key": key, "severity_rank": severity_rank(e["severity"]), "tier_rank": tier_rank(e["tier"]), "last_seen": now_text()}
    state["initialized"] = True
    state["schema_version"] = STATE_SCHEMA_VERSION
    if migration_run:
        print("State schema migrated to v2. Alerts suppressed once to prevent old backlog notifications.")
    if skipped_old_new:
        print(f"Skipped {skipped_old_new} old first-seen event(s); saved to state without Telegram alert.")
    if skipped_stale_update:
        print(f"Skipped {skipped_stale_update} stale update(s); saved to state without Telegram alert.")
    return sorted(alerts, key=alert_sort_key, reverse=True)[:MAX_ALERTS_PER_RUN], first_run, migration_run


def esc(text):
    return html.escape(str(text or ""), quote=False)


def format_alert(event):
    action = event.get("alert_action", "EVENT UPDATE")
    header_icon = {"NEW EVENT": "🚨", "EVENT UPDATE": "🔄", "ESCALATION": "⚠️"}.get(action, "🔔")
    sev_icon = severity_symbol(event["severity"])
    peril_icon = peril_symbol(event["peril"])
    link = html.escape(event.get("link", ""), quote=True)
    lines = [
        f"{header_icon} <b>CATWATCH {esc(action)}</b>",
        "",
        f"{sev_icon} <b>{esc(tier_label(event['tier']))}</b> | {peril_icon} <b>{esc(event['peril'])}</b> | {esc(event['source'])}",
        f"<b>{esc(event['name'])}</b>",
        "",
        f"📍 <b>Region:</b> {esc(event['region'])}",
        f"📊 <b>Severity:</b> {esc(event['severity'])}",
        f"🌡️ <b>Intensity:</b> {esc(short(event['intensity'], 220))}",
        "",
        f"🧭 <b>What to expect:</b> {esc(short(event['what_to_expect'], 280))}",
        f"🗺️ <b>Impact area:</b> {esc(short(event['impact_region'], 220))}",
        "",
        f"⏱ <b>Latest update:</b> {esc(event['latest_update'])}",
    ]
    if link:
        lines.append(f"🔗 <a href=\"{link}\">Open source</a>")
    return "\n".join(lines)


def format_startup_summary(events):
    alertable = sorted([e for e in events if is_alertable(e)], key=lambda e: (tier_rank(e["tier"]), severity_rank(e["severity"]), e.get("event_time") or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    top_lines = []
    for e in alertable[:6]:
        top_lines.append(f"{severity_symbol(e['severity'])} {peril_symbol(e['peril'])} <b>{esc(e['tier'])}</b> — {esc(short(e['name'], 90))}")
    if not top_lines:
        top_lines = ["No P1/P2 or alertable event currently in the watchlist."]
    return "\n".join(["✅ <b>CATWATCH TELEGRAM ALERTS ACTIVATED</b>", "", "Live sources checked: USGS, GDACS, NOAA/NHC", f"Current alertable watchlist: <b>{len(alertable)}</b>", "", "<b>Top current watchlist</b>", *top_lines, "", "Next runs will send only:", "🚨 NEW EVENT", "🔄 EVENT UPDATE", "⚠️ ESCALATION"])


def send_telegram(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        print("Missing TELEGRAM_BOT_TOKEN secret. No Telegram message sent.")
        return False
    if not chat_id:
        print("Missing TELEGRAM_CHAT_ID secret. No Telegram message sent.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=20)
    if r.status_code >= 400:
        print(f"Telegram send failed: {r.status_code} {r.text[:500]}")
        return False
    print("Telegram message sent.")
    return True


def main():
    print(f"CatWatch alert run started: {now_text()}")
    events = fetch_all_events()
    print(f"Fetched {len(events)} total live events.")
    state = load_state()
    alerts, first_run, migration_run = build_alerts(events, state)
    if first_run:
        print("First run: initializing state and sending startup summary only.")
        send_telegram(format_startup_summary(events))
    elif migration_run:
        print("Migration run completed silently; no Telegram alert sent.")
    elif alerts:
        print(f"Sending {len(alerts)} alert(s).")
        for event in alerts:
            send_telegram(format_alert(event))
    else:
        print("No new/update/escalation alerts this run.")
    save_state(state)
    print("State saved.")


if __name__ == "__main__":
    main()
