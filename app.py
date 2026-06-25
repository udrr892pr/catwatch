import hashlib
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
from dateutil import parser as dateparser
from streamlit_autorefresh import st_autorefresh


# ============================================================
# CatWatch v6 — Alert & Footprint Engine
# Mobile-first cat management cockpit
# ============================================================

st.set_page_config(
    page_title="CatWatch Mobile",
    page_icon="🌍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson"
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"

# NHC GIS RSS feeds. Active only when products exist.
NHC_GIS_FEEDS = {
    "Atlantic": "https://www.nhc.noaa.gov/gis-at.xml",
    "Eastern Pacific": "https://www.nhc.noaa.gov/gis-ep.xml",
    "Central Pacific": "https://www.nhc.noaa.gov/gis-cp.xml",
}
NHC_ACTIVE_KML = "https://www.nhc.noaa.gov/gis/kml/nhc_active.kml"

CURRENT_YEAR = datetime.now(timezone.utc).year

VERIFIED_NEWS = [
    "Reuters", "Associated Press", "AP News", "BBC", "The Guardian",
    "Financial Times", "Bloomberg", "Al Jazeera", "CNN", "NHK", "NPR",
    "ABC News", "CBS News", "NBC News", "New York Times", "Washington Post",
    "DW", "France 24",
]


# ============================================================
# CSS / mobile layout
# ============================================================
def inject_css():
    st.markdown(
        """
        <style>
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
        }
        .main { background: linear-gradient(180deg,#f8fafc 0%,#ffffff 34%); }
        .block-container {
            padding: 0.60rem 0.55rem 2.6rem 0.55rem;
            max-width: 780px;
        }
        .hero {
            background: linear-gradient(145deg,#0f172a 0%,#1d4ed8 56%,#0284c7 100%);
            color: white;
            padding: 1rem;
            border-radius: 24px;
            margin-bottom: .78rem;
            box-shadow: 0 14px 32px rgba(15,23,42,.22);
        }
        .title {
            font-size: 1.50rem;
            font-weight: 950;
            letter-spacing: -.035em;
            line-height: 1.08;
            margin: 0;
        }
        .sub {
            font-size: .90rem;
            opacity: .93;
            line-height: 1.38;
            margin-top: .35rem;
        }
        .section {
            font-size: 1.03rem;
            font-weight: 900;
            color: #0f172a;
            margin: .85rem 0 .45rem 0;
        }
        .card {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 20px;
            padding: .86rem;
            box-shadow: 0 8px 22px rgba(15,23,42,.065);
            margin-bottom: .72rem;
        }
        .event { border-left: 6px solid #94a3b8; }
        .b-Critical { border-left-color:#7f1d1d; }
        .b-Red { border-left-color:#dc2626; }
        .b-Orange { border-left-color:#f97316; }
        .b-Amber { border-left-color:#f59e0b; }
        .b-Yellow { border-left-color:#eab308; }
        .b-Green { border-left-color:#22c55e; }
        .b-Unknown { border-left-color:#94a3b8; }

        .headline {
            font-size: .81rem;
            color: #334155;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: .045em;
            margin-bottom: .18rem;
        }
        .et {
            font-size: 1.05rem;
            font-weight: 950;
            color: #0f172a;
            margin: .15rem 0 .26rem 0;
            line-height: 1.25;
        }
        .meta {
            color:#475569;
            font-size:.89rem;
            line-height:1.44;
        }
        .mini {
            color:#64748b;
            font-size:.82rem;
            line-height:1.36;
        }
        .badge {
            display:inline-block;
            border-radius:999px;
            padding:.20rem .55rem;
            font-size:.71rem;
            font-weight:850;
            margin-right:.25rem;
            margin-bottom:.30rem;
        }
        .sev-Critical{background:#7f1d1d;color:white}
        .sev-Red{background:#dc2626;color:white}
        .sev-Orange{background:#f97316;color:white}
        .sev-Amber{background:#f59e0b;color:#111827}
        .sev-Yellow{background:#fde68a;color:#111827}
        .sev-Green{background:#22c55e;color:#052e16}
        .sev-Unknown{background:#cbd5e1;color:#0f172a}
        .tier-P1{background:#991b1b;color:white}
        .tier-P2{background:#ea580c;color:white}
        .tier-P3{background:#2563eb;color:white}
        .tier-P4{background:#64748b;color:white}
        .type-New{background:#dc2626;color:white}
        .type-Update{background:#ea580c;color:white}
        .type-Escalation{background:#7f1d1d;color:white}
        .type-Watch{background:#2563eb;color:white}
        .type-Monitoring{background:#64748b;color:white}
        .pill {
            display:inline-block;
            border-radius:999px;
            padding:.20rem .53rem;
            font-size:.72rem;
            font-weight:800;
            background:#eff6ff;
            color:#1d4ed8;
            border:1px solid #bfdbfe;
            margin-right:.25rem;
            margin-bottom:.30rem;
        }
        .chip {
            display:inline-block;
            border-radius:999px;
            padding:.18rem .50rem;
            font-size:.70rem;
            font-weight:800;
            background:#f1f5f9;
            color:#334155;
            margin-right:.25rem;
            margin-bottom:.30rem;
        }
        .summary {
            background:#f8fafc;
            border-left:5px solid #2563eb;
            border-radius:14px;
            padding:.85rem;
            color:#0f172a;
            line-height:1.50;
            margin-bottom:.70rem;
            font-size:.92rem;
        }
        .warn {
            background:#fff7ed;
            border-left:5px solid #f97316;
            border-radius:14px;
            padding:.85rem;
            color:#0f172a;
            line-height:1.45;
            margin-bottom:.70rem;
            font-size:.90rem;
        }
        .okbox {
            background:#f0fdf4;
            border-left:5px solid #22c55e;
            border-radius:14px;
            padding:.85rem;
            color:#052e16;
            line-height:1.45;
            margin-bottom:.70rem;
            font-size:.90rem;
        }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 18px;
            padding: .50rem;
            box-shadow: 0 5px 18px rgba(15,23,42,.05);
        }
        div[data-testid="stMetricLabel"] { font-size:.72rem; }
        div[data-testid="stMetricValue"] { font-size:1.02rem; }
        .stTabs [data-baseweb="tab-list"] {
            gap:.28rem;
            overflow-x:auto;
            white-space:nowrap;
            padding-bottom:.25rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius:999px;
            background:#eff6ff;
            padding:.38rem .66rem;
            height:auto;
            font-size:.82rem;
        }
        div[data-baseweb="select"]>div { border-radius:14px; }
        .stTextInput input { border-radius:14px; }
        a { text-decoration: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Utility
# ============================================================
def utc_now():
    return datetime.now(timezone.utc)


def now_txt():
    return utc_now().strftime("%Y-%m-%d %H:%M UTC")


def make_id(prefix, text):
    return f"{prefix}-{hashlib.md5(str(text).encode()).hexdigest()[:10].upper()}"


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text or ""))).strip()


def parse_dt(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        d = dateparser.parse(str(value))
        if d and d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


def short(text, n=180):
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def severity_rank(sev):
    return {
        "Critical": 5,
        "Red": 4,
        "Orange": 3,
        "Amber": 3,
        "Yellow": 2,
        "Green": 1,
        "Unknown": 0,
    }.get(str(sev), 0)


def severity_color(sev):
    return {
        "Critical": [127, 29, 29, 220],
        "Red": [220, 38, 38, 210],
        "Orange": [249, 115, 22, 205],
        "Amber": [245, 158, 11, 205],
        "Yellow": [253, 230, 138, 205],
        "Green": [34, 197, 94, 190],
        "Unknown": [100, 116, 139, 180],
    }.get(str(sev), [100, 116, 139, 180])


def eq_severity(magnitude):
    mag = safe_float(magnitude)
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
    text = f"{title} {summary}".lower()
    if "red" in text:
        return "Red"
    if "orange" in text:
        return "Orange"
    if "yellow" in text:
        return "Yellow"
    if "green" in text:
        return "Green"
    return "Unknown"


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
        ("bushfire", "Wildfire"),
        ("fire", "Wildfire"),
        ("volcano", "Volcano"),
        ("tsunami", "Tsunami"),
        ("landslide", "Landslide"),
        ("storm", "Severe Storm"),
        ("hail", "Severe Storm"),
        ("tornado", "Severe Storm"),
        ("drought", "Drought"),
    ]
    for key, value in pairs:
        if key in t:
            return value
    return "Other"


def emoji(peril):
    return {
        "Earthquake": "🌎",
        "Tropical Cyclone": "🌀",
        "Flood": "🌊",
        "Wildfire": "🔥",
        "Volcano": "🌋",
        "Tsunami": "🌊",
        "Landslide": "⛰️",
        "Severe Storm": "⛈️",
        "Drought": "☀️",
        "Other": "📍",
    }.get(str(peril), "📍")


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


def notification_tier(sev, peril, intensity=""):
    combined = f"{sev} {peril} {intensity}".lower()
    if sev in {"Critical", "Red"}:
        return "P1"
    if "magnitude 7" in combined or "magnitude 8" in combined or "magnitude 6." in combined:
        return "P1"
    if "category 4" in combined or "category 5" in combined or "major hurricane" in combined:
        return "P1"
    if sev in {"Orange", "Amber"}:
        return "P2"
    if sev in {"Yellow", "Green"}:
        return "P3"
    return "P4"


def tier_label(tier):
    return {
        "P1": "P1 Executive Alert",
        "P2": "P2 Analyst Watch",
        "P3": "P3 Monitor",
        "P4": "P4 Information",
    }.get(str(tier), "P4 Information")


def alert_type_class(label):
    if "New" in label:
        return "type-New"
    if "Escalation" in label:
        return "type-Escalation"
    if "Update" in label:
        return "type-Update"
    if "Watch" in label:
        return "type-Watch"
    return "type-Monitoring"


def classify_alert_type(event_time, update_time=None, severity="Unknown", tier="P4", source_text=""):
    now = utc_now()
    source_low = str(source_text or "").lower()

    if any(word in source_low for word in ["worsening", "raised", "red alert", "upgraded", "rapid intensification"]):
        return "Escalation"

    if event_time:
        try:
            if (now - event_time).total_seconds() <= 24 * 3600:
                return "New Event"
        except Exception:
            pass

    if update_time:
        try:
            if (now - update_time).total_seconds() <= 24 * 3600:
                return "Event Update"
        except Exception:
            pass

    if tier in {"P1", "P2"} or severity in {"Critical", "Red", "Orange", "Amber"}:
        return "Active Watch"

    return "Monitoring"


def expected_impact(peril, severity, intensity="", country=""):
    p = str(peril)
    s = str(severity)
    text = str(intensity or "").lower()

    if p == "Earthquake":
        if s in {"Critical", "Red"}:
            return "Expect aftershocks, potential building damage, infrastructure disruption, casualty reports, and possible business interruption. Check tsunami advisories if offshore."
        if s == "Amber":
            return "Expect local shaking impacts, aftershocks, possible damage reports near the epicentre, and rapid changes as USGS products update."
        return "Monitor for aftershock sequence and local impact reports."

    if p == "Tropical Cyclone":
        if "category 5" in text or "category 4" in text or s in {"Critical", "Red"}:
            return "Expect destructive wind, storm surge, coastal flooding, heavy rainfall, power outages, transport disruption, and claims from property, marine, agriculture and BI."
        return "Expect track changes, rainfall/flood risk, wind field expansion, coastal impacts, and next-advisory updates."

    if p == "Flood":
        return "Expect river/flash flooding, road and infrastructure disruption, evacuation reports, agriculture impacts, and property/BI claims if urban or industrial zones are affected."
    if p == "Wildfire":
        return "Expect active perimeter change, evacuation orders, smoke impacts, property loss potential, utility disruption, and demand surge after containment improves."
    if p == "Volcano":
        return "Expect ashfall, aviation disruption, lahars/pyroclastic-flow risk depending on volcano behaviour, and official exclusion-zone updates."
    if p == "Tsunami":
        return "Expect rapid official warning changes, coastal inundation risk, port/marine impacts, and post-event confirmation of wave heights."
    if p == "Severe Storm":
        return "Expect wind/hail/tornado damage reports, power outages, auto/property losses, and rapid local news updates."
    return "Monitor official sources, verified news, vendor commentary, and humanitarian impact reporting."


def impact_region_text(peril, location, country, track_available=False):
    if peril == "Tropical Cyclone":
        if track_available:
            return "Track / cone / wind-probability products available from NHC GIS feeds where storm is in NHC basins."
        return "Potential impact area depends on advisory track, cone, wind radii, rainfall and surge zones."
    if peril == "Earthquake":
        return "Impacted area is better represented by USGS ShakeMap intensity, not only epicentre. Link/check ShakeMap when available."
    if peril == "Wildfire":
        return "Impacted area should be mapped using active fire detections/perimeter products where available."
    if peril == "Flood":
        return "Impacted area may need satellite/emergency mapping footprint, river-basin or official flood extent data."
    return f"Primary reported area: {location or country or 'Unknown'}."


def analyst_action(row):
    tier = row.get("Notification_Tier", "P4")
    if tier == "P1":
        return "Create short management update; verify exposure relevance; monitor official/vendor/news changes every 15–30 minutes."
    if tier == "P2":
        return "Keep on analyst watchlist; check escalation, affected population, landfall/impact timing, and public loss commentary."
    return "Monitor for official, vendor, humanitarian, news or loss-related updates."


def next_update_hint(row):
    peril = row.get("Peril", "Other")
    source = row.get("Source_Name", "")
    tier = row.get("Notification_Tier", "P4")
    if peril == "Tropical Cyclone":
        return "Next advisory cycle; more frequently near landfall or rapid intensification."
    if source == "USGS":
        return "15–30 minutes for major earthquakes; then as ShakeMap/impact reports emerge."
    if tier == "P1":
        return "15–30 minutes until alert is stable."
    if tier == "P2":
        return "1–3 hours or when source changes."
    return "Daily or on escalation."


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


# ============================================================
# Live source fetchers
# ============================================================
@st.cache_data(ttl=300)
def fetch_usgs_events():
    rows = []
    try:
        data = requests.get(USGS_URL, timeout=20).json()
        for feature in data.get("features", []):
            props = feature.get("properties", {}) or {}
            geom = feature.get("geometry", {}) or {}
            coords = geom.get("coordinates", [None, None, None])
            mag = props.get("mag")
            place = props.get("place") or "Unknown location"
            event_dt = parse_dt(props.get("time"))
            updated_dt = parse_dt(props.get("updated"))
            sev = eq_severity(mag)
            intensity = f"Magnitude {mag}; depth {coords[2] if len(coords) > 2 else 'Unknown'} km"
            p = "Earthquake"
            tier = notification_tier(sev, p, intensity)
            alert_type = classify_alert_type(event_dt, updated_dt, sev, tier, intensity)

            detail_link = props.get("detail") or ""
            event_url = props.get("url") or ""
            location = place

            rows.append({
                "Event_ID": f"USGS-{feature.get('id', make_id('EQ', place))}",
                "Event_Name": f"M{mag} earthquake - {place}",
                "Peril": p,
                "Event_Status": "Active",
                "Alert_Type": alert_type,
                "Severity": sev,
                "Notification_Tier": tier,
                "Country": extract_country(place),
                "Location_Label": location,
                "Latitude": coords[1] if len(coords) > 1 else None,
                "Longitude": coords[0] if len(coords) > 0 else None,
                "Start_Date": event_dt.strftime("%Y-%m-%d %H:%M UTC") if event_dt else "",
                "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_txt(),
                "Source_Name": "USGS",
                "Source_Link": event_url,
                "Detail_Link": detail_link,
                "Physical_Intensity": intensity,
                "Human_Impact": "Unknown from USGS feed",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "High for hazard parameters; Low for impact/loss",
                "Why_It_Matters": "USGS confirms earthquake hazard parameters rapidly. Casualty, damage, infrastructure, and insured loss require follow-up reporting.",
                "What_To_Expect": expected_impact(p, sev, intensity, extract_country(place)),
                "Impact_Region": impact_region_text(p, location, extract_country(place)),
                "Management_Summary": f"USGS reports a magnitude {mag} earthquake near {place}. Initial hazard information is available; impact and loss remain uncertain.",
                "Track_Info": "Earthquake point shown. Use USGS ShakeMap for shaking footprint where available.",
                "Map_Mode": "Point + ShakeMap link",
            })
    except Exception as exc:
        st.warning(f"USGS fetch failed: {exc}")
    return rows


@st.cache_data(ttl=300)
def fetch_gdacs_events():
    rows = []
    try:
        feed = feedparser.parse(GDACS_RSS_URL)
        for entry in feed.entries[:50]:
            title = getattr(entry, "title", "GDACS event")
            summary = clean(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            event_dt = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
            updated_dt = parse_dt(getattr(entry, "updated", None))
            sev = gdacs_severity(title, summary)
            p = infer_peril(title + " " + summary)
            tier = notification_tier(sev, p, summary)
            alert_type = classify_alert_type(event_dt, updated_dt, sev, tier, f"{title} {summary}")

            lat, lon = None, None
            if hasattr(entry, "where"):
                try:
                    point = entry.where.get("coordinates", [None, None])
                    lon, lat = point[0], point[1]
                except Exception:
                    pass
            if hasattr(entry, "georss_point"):
                try:
                    parts = str(entry.georss_point).split()
                    lat, lon = float(parts[0]), float(parts[1])
                except Exception:
                    pass

            location = title
            country_name = extract_country(title)
            rows.append({
                "Event_ID": make_id("GDACS", title + link),
                "Event_Name": title,
                "Peril": p,
                "Event_Status": "Active",
                "Alert_Type": alert_type,
                "Severity": sev,
                "Notification_Tier": tier,
                "Country": country_name,
                "Location_Label": location,
                "Latitude": lat,
                "Longitude": lon,
                "Start_Date": event_dt.strftime("%Y-%m-%d %H:%M UTC") if event_dt else "",
                "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_txt(),
                "Source_Name": "GDACS",
                "Source_Link": link,
                "Detail_Link": "",
                "Physical_Intensity": short(summary, 260) or "See GDACS source for alert details.",
                "Human_Impact": "Check GDACS, official and humanitarian follow-up reports",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "Medium/High for alert status; Low for impact/loss",
                "Why_It_Matters": "GDACS flags potentially significant sudden-onset disasters and alert changes. Cat analyst review is needed for exposure and loss relevance.",
                "What_To_Expect": expected_impact(p, sev, summary, country_name),
                "Impact_Region": impact_region_text(p, location, country_name),
                "Management_Summary": f"GDACS alert: {title}. Monitor for affected population, escalation/de-escalation, impact reports, and public economic or insured loss estimates.",
                "Track_Info": "Map point shown where coordinates are present. Use NHC GIS tab for NHC tropical cyclone track/cone products when relevant.",
                "Map_Mode": "Point / alert feed",
            })
    except Exception as exc:
        st.warning(f"GDACS fetch failed: {exc}")
    return rows


def get_entry_attr(entry, *names):
    for name in names:
        if hasattr(entry, name):
            value = getattr(entry, name)
            if value:
                return value
        # feedparser sometimes stores namespaced keys in dict style
        try:
            value = entry.get(name)
            if value:
                return value
        except Exception:
            pass
    return ""


def parse_nhc_center(center_text):
    try:
        parts = re.split(r"[,\s]+", str(center_text).strip())
        nums = [p for p in parts if p]
        if len(nums) >= 2:
            return float(nums[0]), float(nums[1])
    except Exception:
        pass
    return None, None


@st.cache_data(ttl=300)
def fetch_nhc_products():
    """Return NHC GIS RSS products from Atlantic/East Pacific/Central Pacific."""
    rows = []
    for basin, url in NHC_GIS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = getattr(entry, "title", "")
                link = getattr(entry, "link", "")
                published = getattr(entry, "published", "") or getattr(entry, "updated", "")
                guid = getattr(entry, "id", "") or getattr(entry, "guid", "")
                clean_title = clean(title)
                lower = clean_title.lower()

                product = "Other"
                if "summary" in lower:
                    product = "Summary"
                elif "forecast track" in lower:
                    product = "Forecast Track"
                elif "cone" in lower:
                    product = "Cone"
                elif "watch" in lower or "warning" in lower:
                    product = "Watches / Warnings"
                elif "wind speed probabilities" in lower or "wsp" in lower:
                    product = "Wind Speed Probability"
                elif "best track" in lower:
                    product = "Preliminary Best Track"
                elif "wind field" in lower:
                    product = "Wind Field"

                atcf = ""
                m = re.search(r"\(([A-Za-z0-9]+/[A-Za-z0-9]+)\)", clean_title)
                if m:
                    atcf = m.group(1)
                m2 = re.search(r"\(([A-Za-z]{2}\d{2}\d{4})\)", clean_title)
                if m2:
                    atcf = m2.group(1)

                storm_name = ""
                # Product [format] - Storm Type NAME (wallet/atcfID)
                if " - " in clean_title:
                    right = clean_title.split(" - ", 1)[1]
                    storm_name = re.sub(r"\([^)]*\)", "", right).strip()
                    storm_name = re.sub(r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)\s+", "", storm_name, flags=re.I).strip()

                rows.append({
                    "Basin": basin,
                    "Title": clean_title,
                    "Product": product,
                    "Storm_Name": storm_name,
                    "ATCF": atcf,
                    "Published": published,
                    "Link": link,
                    "GUID": guid,
                })
        except Exception as exc:
            # Do not break the whole app for one basin
            rows.append({
                "Basin": basin,
                "Title": f"NHC feed fetch failed: {exc}",
                "Product": "Error",
                "Storm_Name": "",
                "ATCF": "",
                "Published": "",
                "Link": url,
                "GUID": "",
            })
    return pd.DataFrame(rows)


@st.cache_data(ttl=300)
def fetch_nhc_events():
    products = fetch_nhc_products()
    rows = []
    if products.empty:
        return rows

    summary_products = products[products["Product"] == "Summary"].copy()
    if summary_products.empty:
        return rows

    # Re-parse raw feeds to read namespaced summary fields where available.
    for basin, url in NHC_GIS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = clean(getattr(entry, "title", ""))
                if "summary" not in title.lower():
                    continue

                summary = clean(getattr(entry, "summary", ""))
                link = getattr(entry, "link", "")
                published_dt = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
                updated_dt = parse_dt(getattr(entry, "updated", None))

                storm_type = get_entry_attr(entry, "nhc_type", "type")
                name = get_entry_attr(entry, "nhc_name", "name")
                atcf = get_entry_attr(entry, "nhc_atcf", "atcf")
                center = get_entry_attr(entry, "nhc_center", "center")
                movement = get_entry_attr(entry, "nhc_movement", "movement")
                pressure = get_entry_attr(entry, "nhc_pressure", "pressure")
                headline = get_entry_attr(entry, "nhc_headline", "headline")
                wind = get_entry_attr(entry, "nhc_wind", "wind")

                # Fallback parsing from title:
                # Summary - Hurricane NAME (wallet/atcfID)
                if not name and " - " in title:
                    right = title.split(" - ", 1)[1]
                    right = re.sub(r"\([^)]*\)", "", right).strip()
                    name = re.sub(r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)\s+", "", right, flags=re.I).strip()
                    if not storm_type:
                        m = re.match(r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)", right, flags=re.I)
                        storm_type = m.group(1) if m else "Tropical Cyclone"

                lat, lon = parse_nhc_center(center)
                cat = category_from_wind(wind) or storm_type or "Tropical Cyclone"
                intensity = "; ".join([x for x in [cat, f"Wind {wind}" if wind else "", f"Pressure {pressure}" if pressure else "", f"Movement {movement}" if movement else ""] if x])
                if not intensity:
                    intensity = summary or "NHC tropical cyclone summary"

                sev = "Red" if "category 4" in intensity.lower() or "category 5" in intensity.lower() else "Orange" if "hurricane" in intensity.lower() else "Amber"
                p = "Tropical Cyclone"
                tier = notification_tier(sev, p, intensity)
                alert_type = classify_alert_type(published_dt, updated_dt, sev, tier, f"{headline} {summary} {intensity}")

                storm_display = " ".join([str(storm_type or "Tropical Cyclone").strip(), str(name or "").strip()]).strip()
                if not storm_display:
                    storm_display = title

                track_available = not products[
                    (products["Product"].isin(["Forecast Track", "Cone", "Wind Speed Probability", "Watches / Warnings"])) &
                    (
                        products["Storm_Name"].str.lower().str.contains(str(name or "").lower(), na=False) |
                        products["Title"].str.lower().str.contains(str(name or "").lower(), na=False) |
                        products["Title"].str.lower().str.contains(str(atcf or "").lower(), na=False)
                    )
                ].empty if name or atcf else False

                rows.append({
                    "Event_ID": make_id("NHC", f"{basin}-{storm_display}-{atcf}-{title}"),
                    "Event_Name": storm_display,
                    "Peril": p,
                    "Event_Status": "Active",
                    "Alert_Type": alert_type,
                    "Severity": sev,
                    "Notification_Tier": tier,
                    "Country": "NHC Basin",
                    "Location_Label": basin,
                    "Latitude": lat,
                    "Longitude": lon,
                    "Start_Date": published_dt.strftime("%Y-%m-%d %H:%M UTC") if published_dt else "",
                    "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_txt(),
                    "Source_Name": "NOAA/NHC",
                    "Source_Link": link or url,
                    "Detail_Link": link or url,
                    "Physical_Intensity": intensity,
                    "Human_Impact": "Check NHC advisories, local warnings, rainfall/surge products, and verified news",
                    "Economic_Loss": "Unknown",
                    "Insured_Loss": "Unknown",
                    "Industry_Loss_Status": "Not yet reported",
                    "Confidence_Level": "High for advisory/status; Low for impact/loss",
                    "Why_It_Matters": "NHC active products provide forecast track, cone, warnings and wind-probability products when available in NHC basins.",
                    "What_To_Expect": expected_impact(p, sev, intensity, "NHC Basin"),
                    "Impact_Region": impact_region_text(p, basin, "NHC Basin", track_available=track_available),
                    "Management_Summary": f"NHC active tropical cyclone product: {storm_display}. Monitor advisory track, cone, wind radii/probabilities, watches/warnings, rainfall and surge risks.",
                    "Track_Info": "NHC GIS product links available in Cyclone Map tab where products exist.",
                    "Map_Mode": "NHC track/cone/products",
                    "NHC_Storm_Name": str(name or storm_display),
                    "NHC_ATCF": str(atcf or ""),
                    "NHC_Basin": basin,
                })
        except Exception:
            continue

    return rows


@st.cache_data(ttl=600)
def fetch_usgs_shakemap_status(detail_url):
    if not detail_url:
        return {"available": False, "url": "", "note": "No USGS detail URL available."}
    try:
        data = requests.get(detail_url, timeout=15).json()
        products = data.get("properties", {}).get("products", {})
        shakemaps = products.get("shakemap", [])
        if not shakemaps:
            return {"available": False, "url": detail_url, "note": "No ShakeMap product listed yet in USGS detail feed."}
        preferred_url = shakemaps[0].get("preferredWeight", "")
        product_url = shakemaps[0].get("source", "")
        contents = shakemaps[0].get("contents", {}) or {}
        link = ""
        for key, val in contents.items():
            if "download/intensity.jpg" in key or "download/intensity.pdf" in key or "download/grid.xml" in key:
                link = val.get("url", "")
                break
        return {
            "available": True,
            "url": link or detail_url,
            "note": "ShakeMap product is listed by USGS. Open the link/source for shaking intensity footprint.",
        }
    except Exception as exc:
        return {"available": False, "url": detail_url, "note": f"Could not read ShakeMap detail yet: {exc}"}


@st.cache_data(ttl=300)
def load_events():
    rows = []
    rows.extend(fetch_usgs_events())
    rows.extend(fetch_gdacs_events())
    rows.extend(fetch_nhc_events())

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Start_Date_UTC"] = pd.to_datetime(df["Start_Date"], errors="coerce", utc=True)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30)
    df = df[df["Start_Date_UTC"].isna() | (df["Start_Date_UTC"] >= cutoff)].copy()

    df["Severity_Rank"] = df["Severity"].apply(severity_rank)
    df["Tier_Rank"] = df["Notification_Tier"].map({"P1": 4, "P2": 3, "P3": 2, "P4": 1}).fillna(0)
    df["Alert_Rank"] = df["Alert_Type"].map({"Escalation": 5, "New Event": 4, "Event Update": 3, "Active Watch": 2, "Monitoring": 1}).fillna(0)
    df["Map_Color"] = df["Severity"].apply(severity_color)
    df["Analyst_Action"] = df.apply(analyst_action, axis=1)
    df["Next_Update"] = df.apply(next_update_hint, axis=1)
    return df.sort_values(["Alert_Rank", "Tier_Rank", "Severity_Rank", "Start_Date_UTC"], ascending=[False, False, False, False])


# ============================================================
# News and history
# ============================================================
@st.cache_data(ttl=900)
def fetch_news(event_name, country_name, peril_name):
    q = f'"{event_name}" OR "{country_name}" {peril_name} disaster loss casualties damage'
    url = "https://news.google.com/rss/search?q=" + quote_plus(q) + "&hl=en-US&gl=US&ceid=US:en"
    rows = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:50]:
            title = clean(getattr(entry, "title", ""))
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")
            source = ""
            try:
                source = entry.source.title
            except Exception:
                if " - " in title:
                    source = title.split(" - ")[-1].strip()

            if not any(v.lower() in source.lower() for v in VERIFIED_NEWS):
                continue

            rows.append({
                "Title": title,
                "Source": source or "Verified news",
                "Published": published,
                "Link": link,
            })
            if len(rows) >= 12:
                break
    except Exception as exc:
        st.warning(f"News fetch failed: {exc}")
    return pd.DataFrame(rows)


def today_value(value, year, annual_rate=0.03):
    try:
        return round(float(value) * ((1 + annual_rate) ** max(0, CURRENT_YEAR - int(year))), 1)
    except Exception:
        return None


@st.cache_data
def load_history():
    records = [
        ("HIST-001", "Hurricane Andrew", 1992, "United States", "Florida / Louisiana", "Tropical Cyclone", 27.3, 15.5, 15.5, 65, 25.3, -80.5, "Track available through NOAA historical hurricane sources"),
        ("HIST-002", "Northridge Earthquake", 1994, "United States", "California", "Earthquake", 44.0, 15.3, 15.3, 57, 34.2, -118.5, "Epicentre shown; ShakeMap/hazard footprint requires USGS historical products"),
        ("HIST-003", "Kobe / Great Hanshin Earthquake", 1995, "Japan", "Kobe", "Earthquake", 100.0, 3.0, 3.0, 6434, 34.6, 135.0, "High economic loss with relatively lower insured penetration"),
        ("HIST-004", "Hurricane Katrina", 2005, "United States", "Louisiana / Mississippi", "Tropical Cyclone", 125.0, 65.0, 65.0, 1833, 29.9, -89.9, "Track available through NOAA historical hurricane sources"),
        ("HIST-005", "Wenchuan / Sichuan Earthquake", 2008, "China", "Sichuan", "Earthquake", 150.0, 1.0, 1.0, 87587, 31.0, 103.4, "High humanitarian/economic impact"),
        ("HIST-006", "Chile Maule Earthquake", 2010, "Chile", "Maule / Concepción", "Earthquake", 30.0, 8.0, 8.0, 525, -35.9, -72.7, "Large Latin America earthquake benchmark"),
        ("HIST-007", "Tohoku Earthquake & Tsunami", 2011, "Japan", "Tohoku", "Earthquake / Tsunami", 235.0, 35.0, 35.0, 19759, 38.3, 142.4, "Large earthquake/tsunami/supply-chain event"),
        ("HIST-008", "Thailand Floods", 2011, "Thailand", "Central Thailand", "Flood", 46.5, 16.0, 16.0, 815, 14.0, 100.6, "Industrial estate and supply-chain insured loss"),
        ("HIST-009", "Christchurch Earthquakes", 2010, "New Zealand", "Canterbury", "Earthquake", 40.0, 30.0, 30.0, 185, -43.5, 172.6, "Large insured earthquake loss relative to economy"),
        ("HIST-010", "Hurricane Sandy", 2012, "United States", "Northeast U.S.", "Tropical Cyclone / Storm Surge", 70.0, 30.0, 30.0, 233, 40.7, -74.0, "Track available through NOAA historical hurricane sources"),
        ("HIST-011", "Central Europe Floods", 2013, "Germany / Central Europe", "Germany / Austria / Czechia", "Flood", 16.0, 4.0, 4.0, 25, 48.2, 12.7, "European flood benchmark"),
        ("HIST-012", "Hurricane Harvey", 2017, "United States", "Texas", "Tropical Cyclone / Flood", 125.0, 30.0, 30.0, 107, 29.8, -95.4, "Flood-dominated hurricane benchmark"),
        ("HIST-013", "Hurricane Irma", 2017, "Caribbean / United States", "Caribbean / Florida", "Tropical Cyclone", 77.0, 32.0, 32.0, 134, 25.8, -80.2, "Large Caribbean/Florida wind loss"),
        ("HIST-014", "Hurricane Maria", 2017, "Puerto Rico / Caribbean", "Puerto Rico", "Tropical Cyclone", 90.0, 32.0, 32.0, 3059, 18.2, -66.5, "Major Caribbean humanitarian/insured loss"),
        ("HIST-015", "Camp Fire", 2018, "United States", "California", "Wildfire", 16.5, 12.0, 12.0, 85, 39.8, -121.4, "Urban-conflagration wildfire benchmark"),
        ("HIST-016", "Typhoon Jebi", 2018, "Japan", "Kansai", "Tropical Cyclone", 13.0, 12.0, 12.0, 17, 34.7, 135.5, "Large Japan typhoon insured loss"),
        ("HIST-017", "Australia Black Summer Bushfires", 2019, "Australia", "NSW / Victoria", "Wildfire", 100.0, 2.0, 2.0, 34, -36.5, 148.0, "Large wildfire/smoke/economic impacts"),
        ("HIST-018", "Europe Floods", 2021, "Germany / Belgium", "Ahr Valley / Belgium", "Flood", 54.0, 13.0, 13.0, 243, 50.5, 6.5, "Major European flood benchmark"),
        ("HIST-019", "Hurricane Ida", 2021, "United States", "Louisiana / Northeast U.S.", "Tropical Cyclone / Flood", 75.0, 36.0, 36.0, 107, 29.9, -90.1, "Wind + inland flood benchmark"),
        ("HIST-020", "Hurricane Ian", 2022, "United States", "Florida", "Tropical Cyclone / Storm Surge", 113.0, 60.0, 60.0, 161, 26.6, -82.0, "Major Florida surge/wind loss"),
        ("HIST-021", "Türkiye–Syria Earthquakes", 2023, "Türkiye / Syria", "Kahramanmaraş", "Earthquake", 100.0, 5.0, 5.0, 59000, 37.2, 37.0, "High humanitarian/economic impact"),
        ("HIST-022", "Hurricane Otis", 2023, "Mexico", "Acapulco", "Tropical Cyclone", 15.0, 2.0, 2.0, 52, 16.9, -99.8, "Rapid-intensification event"),
        ("HIST-023", "Noto Peninsula Earthquake", 2024, "Japan", "Ishikawa", "Earthquake", 17.0, 3.0, 3.0, 240, 37.5, 137.2, "Recent Japan earthquake benchmark"),
        ("HIST-024", "Hurricane Beryl", 2024, "Caribbean / United States", "Caribbean / Texas", "Tropical Cyclone", 7.0, 3.0, 3.0, 70, 29.3, -94.8, "Early-season major hurricane"),
        ("HIST-025", "Los Angeles Wildfires", 2025, "United States", "California", "Wildfire", 100.0, 40.0, 40.0, None, 34.1, -118.3, "Preliminary recent wildfire benchmark"),
    ]
    cols = [
        "Event_ID", "Event_Name", "Year", "Country", "Region", "Peril",
        "Economic_Loss_USD_Bn_Reported", "Insured_Loss_USD_Bn_Reported",
        "Industry_Loss_USD_Bn_Reported", "Fatalities", "Latitude", "Longitude", "Footprint_Note"
    ]
    df = pd.DataFrame(records, columns=cols)
    for col in ["Economic_Loss_USD_Bn_Reported", "Insured_Loss_USD_Bn_Reported", "Industry_Loss_USD_Bn_Reported"]:
        df[col.replace("_Reported", "_Today_Approx")] = df.apply(lambda r: today_value(r[col], r["Year"]), axis=1)
    df["Inflation_Method"] = "Approximate 3% annual USD compounding; replace with official CPI/licensed loss tables."
    df["Source_Status"] = "Starter dataset; verify before formal use."
    return df


# ============================================================
# Map / footprint helpers
# ============================================================
def kml_bytes_from_url(url):
    if not url:
        return None
    try:
        content = requests.get(url, timeout=20).content
        if url.lower().endswith(".kmz"):
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".kml"):
                        return zf.read(name)
            return None
        return content
    except Exception:
        return None


def parse_kml_geometries(kml_bytes):
    """Return line paths and polygons from KML/KMZ as lists of [lon,lat]."""
    lines, polygons, points = [], [], []
    if not kml_bytes:
        return lines, polygons, points
    try:
        root = ET.fromstring(kml_bytes)
        ns = {"kml": "http://www.opengis.net/kml/2.2"}

        def coords_to_pairs(text):
            pairs = []
            for chunk in re.split(r"\s+", str(text or "").strip()):
                parts = chunk.split(",")
                if len(parts) >= 2:
                    lon = safe_float(parts[0])
                    lat = safe_float(parts[1])
                    if lon is not None and lat is not None:
                        pairs.append([lon, lat])
            return pairs

        for elem in root.findall(".//kml:LineString/kml:coordinates", ns):
            arr = coords_to_pairs(elem.text)
            if len(arr) >= 2:
                lines.append(arr)

        for elem in root.findall(".//kml:Polygon//kml:coordinates", ns):
            arr = coords_to_pairs(elem.text)
            if len(arr) >= 3:
                polygons.append(arr)

        for elem in root.findall(".//kml:Point/kml:coordinates", ns):
            arr = coords_to_pairs(elem.text)
            if arr:
                points.append(arr[0])

        # Some KMLs omit namespace; fallback by local name
        if not lines and not polygons and not points:
            for elem in root.iter():
                tag = elem.tag.split("}")[-1]
                if tag == "coordinates":
                    arr = coords_to_pairs(elem.text)
                    if len(arr) >= 3:
                        polygons.append(arr)
                    elif len(arr) >= 2:
                        lines.append(arr)
                    elif len(arr) == 1:
                        points.append(arr[0])
    except Exception:
        pass
    return lines, polygons, points


def match_nhc_products_for_event(event):
    products = fetch_nhc_products()
    if products.empty:
        return products

    name = str(event.get("NHC_Storm_Name") or event.get("Event_Name") or "").lower()
    atcf = str(event.get("NHC_ATCF") or "").lower()
    basin = str(event.get("NHC_Basin") or "").lower()

    # Handle event names like "Hurricane Melissa"
    name_simple = re.sub(r"^(hurricane|tropical storm|tropical depression|potential tropical cyclone|post-tropical cyclone|subtropical storm)\s+", "", name).strip()

    mask = pd.Series([False] * len(products))
    if name_simple:
        mask = mask | products["Storm_Name"].str.lower().str.contains(re.escape(name_simple), na=False)
        mask = mask | products["Title"].str.lower().str.contains(re.escape(name_simple), na=False)
    if atcf:
        mask = mask | products["Title"].str.lower().str.contains(re.escape(atcf), na=False)
        mask = mask | products["ATCF"].str.lower().str.contains(re.escape(atcf), na=False)
    if basin and not mask.any():
        mask = products["Basin"].str.lower().str.contains(re.escape(basin), na=False)

    return products[mask].copy()


def live_event_map(event_df):
    m = event_df.dropna(subset=["Latitude", "Longitude"]).copy()
    if m.empty:
        st.info("No point coordinates available for the selected events.")
        return
    m["lat"] = pd.to_numeric(m["Latitude"], errors="coerce")
    m["lon"] = pd.to_numeric(m["Longitude"], errors="coerce")
    m = m.dropna(subset=["lat", "lon"])
    if m.empty:
        st.info("No valid coordinates available.")
        return

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=m,
        get_position="[lon, lat]",
        get_radius=80000,
        get_fill_color="Map_Color",
        pickable=True,
        auto_highlight=True,
    )
    view = pdk.ViewState(latitude=m["lat"].mean(), longitude=m["lon"].mean(), zoom=1, pitch=0)
    tooltip = {
        "html": "<b>{Event_Name}</b><br/>Type: {Alert_Type}<br/>Severity: {Severity}<br/>Priority: {Notification_Tier}<br/>Source: {Source_Name}",
        "style": {"backgroundColor": "#0f172a", "color": "white"},
    }
    st.pydeck_chart(pdk.Deck(layers=[point_layer], initial_view_state=view, tooltip=tooltip), use_container_width=True)


def nhc_footprint_map(event):
    products = match_nhc_products_for_event(event)
    if products.empty:
        st.info("No matching NHC GIS products are available for this event right now.")
        return

    track_rows, cone_rows, point_rows = [], [], []
    product_notes = []

    # Prefer latest/most relevant products
    for _, prod in products.iterrows():
        ptype = prod["Product"]
        link = prod["Link"]
        if ptype not in ["Forecast Track", "Cone", "Preliminary Best Track", "Wind Speed Probability", "Watches / Warnings"]:
            continue
        if not str(link).lower().endswith((".kmz", ".kml")):
            product_notes.append(f"{ptype}: product link available but not KML/KMZ in app parser.")
            continue

        kml = kml_bytes_from_url(link)
        lines, polygons, points = parse_kml_geometries(kml)

        if ptype in ["Forecast Track", "Preliminary Best Track"]:
            for line in lines[:3]:
                track_rows.append({"path": line, "product": ptype, "title": prod["Title"]})
            for pt in points[:80]:
                point_rows.append({"lon": pt[0], "lat": pt[1], "product": ptype, "title": prod["Title"]})

        elif ptype in ["Cone", "Wind Speed Probability", "Watches / Warnings"]:
            for poly in polygons[:8]:
                cone_rows.append({"polygon": poly, "product": ptype, "title": prod["Title"]})
            for line in lines[:5]:
                track_rows.append({"path": line, "product": ptype, "title": prod["Title"]})
            for pt in points[:40]:
                point_rows.append({"lon": pt[0], "lat": pt[1], "product": ptype, "title": prod["Title"]})

    layers = []

    if cone_rows:
        layers.append(
            pdk.Layer(
                "PolygonLayer",
                data=pd.DataFrame(cone_rows),
                get_polygon="polygon",
                get_fill_color=[249, 115, 22, 70],
                get_line_color=[249, 115, 22, 220],
                line_width_min_pixels=1,
                pickable=True,
            )
        )

    if track_rows:
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=pd.DataFrame(track_rows),
                get_path="path",
                get_color=[37, 99, 235, 230],
                width_min_pixels=4,
                pickable=True,
            )
        )

    if point_rows:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=pd.DataFrame(point_rows),
                get_position="[lon, lat]",
                get_radius=45000,
                get_fill_color=[220, 38, 38, 210],
                pickable=True,
            )
        )

    # Add current point if available
    lat = safe_float(event.get("Latitude"))
    lon = safe_float(event.get("Longitude"))
    if lat is not None and lon is not None:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=pd.DataFrame([{"lat": lat, "lon": lon, "Event_Name": event.get("Event_Name")}]),
                get_position="[lon, lat]",
                get_radius=95000,
                get_fill_color=[127, 29, 29, 230],
                pickable=True,
            )
        )

    if not layers:
        st.info("NHC products were found, but no track/cone geometry could be parsed in this app yet. Use the product links below.")
    else:
        # Determine map center
        all_lats, all_lons = [], []
        for row in track_rows:
            for lon2, lat2 in row["path"]:
                all_lons.append(lon2); all_lats.append(lat2)
        for row in cone_rows:
            for lon2, lat2 in row["polygon"]:
                all_lons.append(lon2); all_lats.append(lat2)
        for row in point_rows:
            all_lons.append(row["lon"]); all_lats.append(row["lat"])
        if lat is not None and lon is not None:
            all_lats.append(lat); all_lons.append(lon)

        view = pdk.ViewState(
            latitude=sum(all_lats) / len(all_lats) if all_lats else 20,
            longitude=sum(all_lons) / len(all_lons) if all_lons else -60,
            zoom=3 if all_lats else 1,
            pitch=0,
        )
        tooltip = {
            "html": "<b>{product}</b><br/>{title}",
            "style": {"backgroundColor": "#0f172a", "color": "white"},
        }
        st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip=tooltip), use_container_width=True)

    st.markdown("**NHC product links**")
    for _, row in products[products["Product"].isin(["Forecast Track", "Cone", "Wind Speed Probability", "Watches / Warnings", "Preliminary Best Track", "Summary"])].head(12).iterrows():
        st.markdown(f"- **{row['Product']}** — [{short(row['Title'], 90)}]({row['Link']})")


def history_map(hist_df):
    m = hist_df.dropna(subset=["Latitude", "Longitude"]).copy()
    if m.empty:
        st.info("No historical coordinates for selected events.")
        return
    m["lat"] = pd.to_numeric(m["Latitude"], errors="coerce")
    m["lon"] = pd.to_numeric(m["Longitude"], errors="coerce")
    m = m.dropna(subset=["lat", "lon"])

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=m,
        get_position="[lon, lat]",
        get_radius=90000,
        get_fill_color=[37, 99, 235, 190],
        pickable=True,
        auto_highlight=True,
    )
    view = pdk.ViewState(latitude=m["lat"].mean(), longitude=m["lon"].mean(), zoom=1, pitch=0)
    tooltip = {
        "html": "<b>{Event_Name}</b><br/>Year: {Year}<br/>Peril: {Peril}<br/>Insured: USD {Insured_Loss_USD_Bn_Reported}bn<br/>{Footprint_Note}",
        "style": {"backgroundColor": "#0f172a", "color": "white"},
    }
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip=tooltip), use_container_width=True)


# ============================================================
# Rendering
# ============================================================
def badges(row):
    sev = row.get("Severity", "Unknown")
    tier = row.get("Notification_Tier", "P4")
    p = row.get("Peril", "Other")
    typ = row.get("Alert_Type", "Monitoring")
    return (
        f"<span class='badge {alert_type_class(typ)}'>{typ}</span>"
        f"<span class='badge tier-{tier}'>{tier_label(tier)}</span>"
        f"<span class='badge sev-{sev}'>{sev}</span>"
        f"<span class='pill'>{emoji(p)} {p}</span>"
        f"<span class='chip'>{row.get('Source_Name', 'Source')}</span>"
    )


def event_card(row):
    sev = row.get("Severity", "Unknown")
    headline = f"{row.get('Alert_Type', 'Monitoring').upper()} • {row.get('Country', 'Unknown')} • {row.get('Physical_Intensity', '')}"
    st.markdown(
        f"""
        <div class="card event b-{sev}">
            {badges(row)}
            <div class="headline">{short(headline, 105)}</div>
            <div class="et">{row.get('Event_Name', 'Unnamed event')}</div>
            <div class="meta">
                <b>Region:</b> {row.get('Location_Label', 'Unknown')}<br>
                <b>What to expect:</b> {short(row.get('What_To_Expect', ''), 165)}<br>
                <b>Impact area:</b> {short(row.get('Impact_Region', ''), 145)}<br>
                <b>Next:</b> {row.get('Next_Update', 'Unknown')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def news_card(row):
    st.markdown(
        f"""
        <div class="card">
            <span class="chip">{row.get('Source', 'News')}</span>
            <div class="et">{row.get('Title', 'Untitled')}</div>
            <div class="meta">
                <b>Published:</b> {row.get('Published', 'Unknown')}<br>
                <a href="{row.get('Link')}" target="_blank">Open verified news item</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def history_card(row):
    st.markdown(
        f"""
        <div class="card">
            <span class="badge sev-Unknown">{row.get('Year')}</span>
            <span class="pill">{emoji(row.get('Peril'))} {row.get('Peril')}</span>
            <div class="et">{row.get('Event_Name')}</div>
            <div class="meta">
                <b>Country:</b> {row.get('Country')}<br>
                <b>Region:</b> {row.get('Region')}<br>
                <b>Economic:</b> USD {row.get('Economic_Loss_USD_Bn_Reported')}bn reported / ~USD {row.get('Economic_Loss_USD_Bn_Today_Approx')}bn today<br>
                <b>Insured:</b> USD {row.get('Insured_Loss_USD_Bn_Reported')}bn reported / ~USD {row.get('Insured_Loss_USD_Bn_Today_Approx')}bn today<br>
                <b>Map note:</b> {row.get('Footprint_Note')}<br>
                <b>Status:</b> Starter estimate; verify before formal use.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def vendor_df(event):
    vendors = [
        ("Moody's RMS", "Model vendor", "Event response, modeled insured loss, hazard footprint", "Public + licensed", "High"),
        ("Verisk Extreme Event Solutions / PCS", "Model vendor / industry loss", "Modeled insured loss estimate, PCS catastrophe info", "Public + licensed", "High"),
        ("KCC", "Model vendor", "Flash estimate, modeled insured loss, event commentary", "Often public summary", "High"),
        ("CoreLogic / Cotality", "Property analytics", "Property impact, exposure, hazard insights", "Public + platform", "Medium"),
        ("PERILS", "Industry loss authority", "Industry loss index / loss updates", "Mostly licensed", "High"),
        ("Aon", "Broker / market report", "Cat recap, loss commentary", "Public reports", "Medium"),
        ("Gallagher Re", "Broker / market report", "Event commentary, loss ranges", "Public reports", "Medium"),
        ("Swiss Re", "Reinsurer", "Insured/economic loss commentary", "Public summaries", "Medium"),
        ("Munich Re", "Reinsurer / NatCat", "NatCat commentary and historical comparison", "Public summaries", "Medium"),
    ]
    rows = []
    for source, category, check, access, priority in vendors:
        rows.append({
            "Priority": priority,
            "Source": source,
            "Category": category,
            "Check": check,
            "Access": access,
            "Link": "https://www.google.com/search?q=" + quote_plus(f'"{event.get("Event_Name")}" {source} insured loss catastrophe model estimate event response'),
        })
    return pd.DataFrame(rows)


def management_text(event):
    return f"""MANAGEMENT UPDATE – {event.get('Event_Name')}

Alert: {event.get('Alert_Type')}
Priority: {tier_label(event.get('Notification_Tier'))}
Peril: {event.get('Peril')}
Severity: {event.get('Severity')}
Country / area: {event.get('Country')}
Region: {event.get('Location_Label')}
Latest update: {event.get('Latest_Update_Date')}
Source: {event.get('Source_Name')}

What happened:
{event.get('Management_Summary')}

Intensity:
{event.get('Physical_Intensity')}

What to expect:
{event.get('What_To_Expect')}

Impact area / footprint:
{event.get('Impact_Region')}

Why it matters:
{event.get('Why_It_Matters')}

Human impact:
{event.get('Human_Impact')}

Economic / insured / industry loss:
Economic loss: {event.get('Economic_Loss')}
Insured loss: {event.get('Insured_Loss')}
Industry loss status: {event.get('Industry_Loss_Status')}

Analyst action:
{event.get('Analyst_Action')}

Next expected update:
{event.get('Next_Update')}

Source link:
{event.get('Source_Link')}
""".strip()


def filtered_events(df):
    st.markdown('<div class="section">Filters</div>', unsafe_allow_html=True)
    with st.expander("Tap to change filters", expanded=False):
        alert_type = st.selectbox("Alert type", ["All"] + sorted(df["Alert_Type"].dropna().unique().tolist()))
        tiers = st.multiselect("Priority", ["P1", "P2", "P3", "P4"], default=["P1", "P2", "P3", "P4"])
        peril = st.selectbox("Peril", ["All"] + sorted(df["Peril"].dropna().unique().tolist()))
        country_opts = ["All"] + df["Country"].fillna("Unknown").astype(str).value_counts().index.tolist()
        country = st.selectbox("Country / area", country_opts)
        search = st.text_input("Search", placeholder="Search event, region, source...")

    out = df.copy()
    if alert_type != "All":
        out = out[out["Alert_Type"] == alert_type]
    if tiers:
        out = out[out["Notification_Tier"].isin(tiers)]
    if peril != "All":
        out = out[out["Peril"] == peril]
    if country != "All":
        out = out[out["Country"] == country]
    if search.strip():
        needle = search.lower().strip()
        out = out[out.apply(lambda r: needle in " ".join(r.astype(str)).lower(), axis=1)]
    return out


# ============================================================
# App
# ============================================================
def main():
    inject_css()
    refresh_count = st_autorefresh(interval=5 * 60 * 1000, key="catwatch_v6_refresh")

    st.markdown(
        """
        <div class="hero">
            <div class="title">🌍 CatWatch Alert Cockpit</div>
            <div class="sub">
            First-to-know catastrophe alerting: new events, event updates, escalation, severity, intensity,
            impacted region, what to expect, verified news, vendor/loss watch and event footprint mapping.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    df = load_events()
    if df.empty:
        st.error("No live event data loaded. Check source availability.")
        return

    filt = filtered_events(df)

    m1, m2, m3 = st.columns(3)
    m1.metric("Live", len(filt))
    m2.metric("New/Upd", int(filt["Alert_Type"].isin(["New Event", "Event Update", "Escalation"]).sum()) if not filt.empty else 0)
    m3.metric("P1/P2", int(filt["Notification_Tier"].isin(["P1", "P2"]).sum()) if not filt.empty else 0)

    if st.button("Refresh now"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Live window: last 30 days where source dates are available. Auto-refresh: 5 minutes while open. Refresh count: {refresh_count}")

    if not filt.empty:
        selected = st.selectbox("Open event", filt["Event_Name"].tolist())
        event = filt[filt["Event_Name"] == selected].iloc[0]
    else:
        event = None

    tabs = st.tabs(["Alerts", "Detail", "Footprint", "Cyclone", "News", "Vendor", "Loss", "History", "Mgmt"])

    with tabs[0]:
        st.markdown('<div class="section">First-to-know queue</div>', unsafe_allow_html=True)
        if filt.empty:
            st.info("No events match the selected filters.")
        else:
            top = filt.copy()
            for _, row in top.head(15).iterrows():
                event_card(row)

    with tabs[1]:
        st.markdown('<div class="section">Event intelligence</div>', unsafe_allow_html=True)
        if event is not None:
            st.markdown(badges(event), unsafe_allow_html=True)
            st.markdown(f"### {event.get('Event_Name')}")
            c1, c2 = st.columns(2)
            c1.metric("Alert", event.get("Alert_Type"))
            c2.metric("Severity", event.get("Severity"))

            st.markdown(f"<div class='summary'>{event.get('Management_Summary')}</div>", unsafe_allow_html=True)
            st.markdown("**What to expect**")
            st.write(event.get("What_To_Expect"))
            st.markdown("**Impacted region / footprint view**")
            st.write(event.get("Impact_Region"))
            st.markdown("**Key facts**")
            st.write(f"**Intensity:** {event.get('Physical_Intensity')}")
            st.write(f"**Region:** {event.get('Location_Label')}")
            st.write(f"**Country / area:** {event.get('Country')}")
            st.write(f"**Human impact:** {event.get('Human_Impact')}")
            st.write(f"**Loss status:** {event.get('Industry_Loss_Status')}")
            st.write(f"**Confidence:** {event.get('Confidence_Level')}")
            st.write(f"**Next update:** {event.get('Next_Update')}")
            st.write(f"**Source:** [{event.get('Source_Name')}]({event.get('Source_Link')})")

            if event.get("Peril") == "Earthquake":
                status = fetch_usgs_shakemap_status(event.get("Detail_Link", ""))
                box_class = "okbox" if status["available"] else "warn"
                st.markdown(f"<div class='{box_class}'><b>USGS ShakeMap:</b> {status['note']}</div>", unsafe_allow_html=True)
                if status.get("url"):
                    st.markdown(f"[Open USGS detail / ShakeMap product]({status['url']})")

    with tabs[2]:
        st.markdown('<div class="section">Footprint map</div>', unsafe_allow_html=True)
        if event is not None:
            st.markdown(f"<div class='summary'><b>Map mode:</b> {event.get('Map_Mode')}<br><b>Footprint note:</b> {event.get('Impact_Region')}</div>", unsafe_allow_html=True)

            if event.get("Source_Name") == "NOAA/NHC" or event.get("Peril") == "Tropical Cyclone":
                nhc_footprint_map(event)
            else:
                live_event_map(pd.DataFrame([event]))
                if event.get("Peril") == "Earthquake":
                    st.info("For earthquakes, the epicentre is not the full impacted area. Open USGS ShakeMap in the Detail tab for shaking footprint where available.")

    with tabs[3]:
        st.markdown('<div class="section">NHC cyclone products</div>', unsafe_allow_html=True)
        products = fetch_nhc_products()
        nhc_events = df[df["Source_Name"] == "NOAA/NHC"].copy()

        if nhc_events.empty:
            st.info("No active NHC tropical cyclone summary events are currently found in the Atlantic, Eastern Pacific, or Central Pacific GIS feeds.")
        else:
            st.markdown("**Active NHC storms**")
            for _, row in nhc_events.iterrows():
                event_card(row)

        if products.empty:
            st.info("No NHC GIS product feed records loaded.")
        else:
            st.markdown("**Latest NHC GIS products**")
            show_cols = ["Basin", "Product", "Storm_Name", "Published", "Title", "Link"]
            st.dataframe(products[show_cols].head(40), use_container_width=True, hide_index=True)

        st.markdown(
            "<div class='warn'>NHC KML/KMZ products can change format and may not always be available. CatWatch shows available product links and attempts to map track/cone geometry when the feed exposes parseable KML/KMZ.</div>",
            unsafe_allow_html=True,
        )

    with tabs[4]:
        st.markdown('<div class="section">Verified news</div>', unsafe_allow_html=True)
        if event is not None:
            st.caption("News is used for context and situational awareness. Verify figures against official/vendor/industry loss sources before formal use.")
            news = fetch_news(event.get("Event_Name"), event.get("Country"), event.get("Peril"))
            if news.empty:
                st.info("No verified news items found yet for this event.")
            else:
                for _, row in news.iterrows():
                    news_card(row)

    with tabs[5]:
        st.markdown('<div class="section">Vendor model watch</div>', unsafe_allow_html=True)
        if event is not None:
            st.markdown(
                "<div class='summary'>Check public vendor/model and industry-loss commentary. Do not scrape or redistribute licensed reports. Record source, date, estimate range, access type and confidence.</div>",
                unsafe_allow_html=True,
            )
            vdf = vendor_df(event)
            for _, row in vdf.iterrows():
                st.markdown(
                    f"""
                    <div class="card">
                        <span class="badge tier-P3">{row['Priority']}</span>
                        <div class="et">{row['Source']}</div>
                        <div class="meta">
                            <b>Category:</b> {row['Category']}<br>
                            <b>Check:</b> {row['Check']}<br>
                            <b>Access:</b> {row['Access']}<br>
                            <a href="{row['Link']}" target="_blank">Search public update</a>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with tabs[6]:
        st.markdown('<div class="section">Loss watch</div>', unsafe_allow_html=True)
        st.markdown("<div class='warn'>Separate hazard facts from loss estimates. Early numbers can be preliminary, restricted, incomplete or wrong.</div>", unsafe_allow_html=True)
        cols = ["Alert_Type", "Notification_Tier", "Severity", "Peril", "Country", "Event_Name", "Economic_Loss", "Insured_Loss", "Industry_Loss_Status", "Confidence_Level", "Source_Name"]
        st.dataframe(filt[cols], use_container_width=True, hide_index=True)

    with tabs[7]:
        st.markdown('<div class="section">Historical events</div>', unsafe_allow_html=True)
        hist = load_history()
        with st.expander("Historical filters", expanded=True):
            h_country = st.selectbox("Country", ["All"] + sorted(hist["Country"].dropna().unique().tolist()), key="h_country")
            h_peril = st.selectbox("Peril", ["All"] + sorted(hist["Peril"].dropna().unique().tolist()), key="h_peril")
            h_search = st.text_input("Search by event name", placeholder="Katrina, Ian, Tohoku...", key="h_search")

        h = hist.copy()
        if h_country != "All":
            h = h[h["Country"] == h_country]
        if h_peril != "All":
            h = h[h["Peril"] == h_peril]
        if h_search.strip():
            h = h[h["Event_Name"].str.lower().str.contains(h_search.lower().strip(), na=False)]

        st.caption("Starter historical dataset: approximate USD bn, not audited. Map points are indicative; full cyclone tracks should be sourced from NOAA Historical Hurricane Tracks / IBTrACS.")
        history_map(h)
        for _, row in h.sort_values("Year", ascending=False).head(50).iterrows():
            history_card(row)

        st.download_button(
            "Download historical starter table",
            hist.to_csv(index=False).encode("utf-8"),
            "catwatch_historical_events_starter.csv",
            "text/csv",
        )

    with tabs[8]:
        st.markdown('<div class="section">Ad-hoc management overview</div>', unsafe_allow_html=True)
        if event is not None:
            summary = management_text(event)
            st.text_area("Management update draft", summary, height=430)
            st.download_button(
                "Download management update",
                summary.encode("utf-8"),
                "catwatch_management_update.txt",
                "text/plain",
            )


if __name__ == "__main__":
    main()
