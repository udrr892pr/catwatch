
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
# CatWatch v7 — polished mobile cat management cockpit
# ============================================================

st.set_page_config(
    page_title="CatWatch",
    page_icon="🌍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson"
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
NHC_GIS_FEEDS = {
    "Atlantic": "https://www.nhc.noaa.gov/gis-at.xml",
    "Eastern Pacific": "https://www.nhc.noaa.gov/gis-ep.xml",
    "Central Pacific": "https://www.nhc.noaa.gov/gis-cp.xml",
}
NHC_ACTIVE_KMZ = "https://www.nhc.noaa.gov/gis/kml/nhc.kmz"

CURRENT_YEAR = datetime.now(timezone.utc).year
VERIFIED_NEWS = [
    "Reuters", "Associated Press", "AP News", "BBC", "The Guardian",
    "Financial Times", "Bloomberg", "Al Jazeera", "CNN", "NHK", "NPR",
    "ABC News", "CBS News", "NBC News", "New York Times", "Washington Post",
    "DW", "France 24",
]


# ============================================================
# Styling
# ============================================================
def inject_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

        html, body, [class*="css"] {
            font-family: "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
            color: #0f172a !important;
        }

        .stApp {
            background: #f4f7fb !important;
            color: #0f172a !important;
        }

        .main .block-container {
            max-width: 760px;
            padding-top: 0.8rem;
            padding-right: 0.85rem;
            padding-left: 0.85rem;
            padding-bottom: 3rem;
        }

        h1,h2,h3,h4,p,span,div,label {
            color: #0f172a;
        }

        .hero {
            background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0ea5e9 100%);
            color: white !important;
            border-radius: 24px;
            padding: 1.1rem 1rem;
            box-shadow: 0 18px 38px rgba(15,23,42,0.18);
            margin-bottom: 0.85rem;
        }
        .hero * { color: white !important; }
        .hero-title {
            font-size: 1.55rem;
            font-weight: 900;
            line-height: 1.05;
            letter-spacing: -0.03em;
            margin-bottom: 0.35rem;
        }
        .hero-sub {
            font-size: 0.93rem;
            line-height: 1.45;
            opacity: 0.98;
        }

        .status-band {
            background: #eef4ff;
            border: 1px solid #c7dbff;
            border-radius: 18px;
            padding: .85rem;
            margin-bottom: .85rem;
        }

        .section-title {
            font-size: 1.03rem;
            font-weight: 900;
            color: #0f172a;
            margin: 0.85rem 0 0.45rem 0;
        }

        .card {
            background: #ffffff;
            border: 1px solid #dde7f3;
            border-radius: 22px;
            padding: 0.95rem;
            box-shadow: 0 8px 26px rgba(15,23,42,0.06);
            margin-bottom: 0.8rem;
        }

        .event-card {
            border-left: 6px solid #94a3b8;
        }
        .sev-border-Critical { border-left-color:#7f1d1d; }
        .sev-border-Red { border-left-color:#dc2626; }
        .sev-border-Orange { border-left-color:#f97316; }
        .sev-border-Amber { border-left-color:#f59e0b; }
        .sev-border-Yellow { border-left-color:#eab308; }
        .sev-border-Green { border-left-color:#22c55e; }
        .sev-border-Unknown { border-left-color:#94a3b8; }

        .eyebrow {
            color: #3b82f6;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 0.15rem;
        }
        .event-title {
            font-size: 1.05rem;
            font-weight: 900;
            color: #0f172a !important;
            line-height: 1.25;
            margin-bottom: 0.35rem;
        }
        .event-meta {
            color: #475569 !important;
            font-size: 0.90rem;
            line-height: 1.5;
        }

        .badge {
            display: inline-block;
            border-radius: 999px;
            padding: 0.22rem 0.58rem;
            font-size: 0.72rem;
            font-weight: 800;
            margin-right: 0.25rem;
            margin-bottom: 0.32rem;
            border: 1px solid transparent;
        }
        .b-sev-Critical { background:#fee2e2; color:#7f1d1d; border-color:#fecaca; }
        .b-sev-Red { background:#fee2e2; color:#b91c1c; border-color:#fecaca; }
        .b-sev-Orange { background:#ffedd5; color:#c2410c; border-color:#fed7aa; }
        .b-sev-Amber { background:#fef3c7; color:#92400e; border-color:#fde68a; }
        .b-sev-Yellow { background:#fef9c3; color:#854d0e; border-color:#fde047; }
        .b-sev-Green { background:#dcfce7; color:#166534; border-color:#bbf7d0; }
        .b-sev-Unknown { background:#e2e8f0; color:#334155; border-color:#cbd5e1; }

        .b-tier-P1 { background:#dbeafe; color:#1d4ed8; border-color:#bfdbfe; }
        .b-tier-P2 { background:#e0f2fe; color:#0369a1; border-color:#bae6fd; }
        .b-tier-P3 { background:#f1f5f9; color:#475569; border-color:#e2e8f0; }
        .b-tier-P4 { background:#f8fafc; color:#64748b; border-color:#e2e8f0; }

        .b-type-New { background:#ecfeff; color:#155e75; border-color:#a5f3fc; }
        .b-type-Update { background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe; }
        .b-type-Escalation { background:#fff1f2; color:#be123c; border-color:#fecdd3; }
        .b-type-Watch { background:#eef2ff; color:#4338ca; border-color:#c7d2fe; }
        .b-type-Monitoring { background:#f8fafc; color:#475569; border-color:#cbd5e1; }

        .b-peril {
            background:#f8fafc;
            color:#334155;
            border-color:#e2e8f0;
        }

        .summary-box {
            background: #ffffff;
            border: 1px solid #dde7f3;
            border-radius: 18px;
            padding: .95rem;
            margin-bottom: .8rem;
            box-shadow: 0 8px 24px rgba(15,23,42,.05);
        }
        .info-box {
            background:#eff6ff;
            border-left:5px solid #2563eb;
            border-radius:16px;
            padding:.9rem;
            margin-bottom:.8rem;
        }
        .warn-box {
            background:#fff7ed;
            border-left:5px solid #ea580c;
            border-radius:16px;
            padding:.9rem;
            margin-bottom:.8rem;
        }
        .ok-box {
            background:#ecfdf5;
            border-left:5px solid #16a34a;
            border-radius:16px;
            padding:.9rem;
            margin-bottom:.8rem;
        }

        div[data-testid="stMetric"] {
            background: #ffffff !important;
            border: 1px solid #dde7f3 !important;
            border-radius: 20px !important;
            padding: 0.6rem 0.75rem !important;
            box-shadow: 0 8px 24px rgba(15,23,42,0.05);
        }
        div[data-testid="stMetricLabel"] p {
            color: #64748b !important;
            font-size: 0.76rem !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-size: 1.1rem !important;
            font-weight: 900 !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
            overflow-x: auto;
            white-space: nowrap;
            padding-bottom: 0.45rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            background: #edf3fb;
            color: #334155 !important;
            border: 1px solid #dbe7f5;
            padding: 0.38rem 0.78rem;
            font-size: 0.84rem;
            height: auto;
        }
        .stTabs [aria-selected="true"] {
            background: #1d4ed8 !important;
            color: #ffffff !important;
            border-color: #1d4ed8 !important;
        }
        .stTabs [aria-selected="true"] p {
            color: #ffffff !important;
            font-weight: 800;
        }

        div[data-baseweb="select"] > div,
        .stTextInput input,
        .stTextArea textarea {
            border-radius: 16px !important;
            border-color: #d6e1ee !important;
            background: #ffffff !important;
            color: #0f172a !important;
        }

        .stButton > button {
            border-radius: 16px;
            border: 1px solid #cbdcf2;
            background: white;
            color: #0f172a;
            font-weight: 700;
            padding: .45rem .9rem;
        }
        .stButton > button:hover {
            border-color: #1d4ed8;
            color: #1d4ed8;
        }

        .small-note {
            color: #64748b;
            font-size: .82rem;
        }

        a {
            color: #1d4ed8 !important;
            text-decoration: none;
        }

        .mobile-divider {
            height: 1px;
            background: #e2e8f0;
            margin: .55rem 0 .85rem 0;
            border-radius: 999px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Helpers
# ============================================================
def utc_now():
    return datetime.now(timezone.utc)


def now_text():
    return utc_now().strftime("%Y-%m-%d %H:%M UTC")


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text or ""))).strip()


def short(text, n=180):
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


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


def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def make_id(prefix, text):
    return f"{prefix}-{hashlib.md5(str(text).encode()).hexdigest()[:10].upper()}"


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
    for key, val in pairs:
        if key in t:
            return val
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


def severity_rank(sev):
    return {
        "Critical": 6,
        "Red": 5,
        "Orange": 4,
        "Amber": 3,
        "Yellow": 2,
        "Green": 1,
        "Unknown": 0,
    }.get(str(sev), 0)


def severity_color(sev):
    return {
        "Critical": [127, 29, 29, 220],
        "Red": [220, 38, 38, 210],
        "Orange": [249, 115, 22, 210],
        "Amber": [245, 158, 11, 205],
        "Yellow": [234, 179, 8, 195],
        "Green": [34, 197, 94, 190],
        "Unknown": [100, 116, 139, 180],
    }.get(str(sev), [100, 116, 139, 180])


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
    text = f"{title} {summary}".lower()
    if " red " in f" {text} ":
        return "Red"
    if " orange " in f" {text} ":
        return "Orange"
    if " yellow " in f" {text} ":
        return "Yellow"
    if " green " in f" {text} ":
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
    return {
        "P1": "P1 Executive",
        "P2": "P2 Analyst Watch",
        "P3": "P3 Monitor",
        "P4": "P4 Info",
    }.get(str(tier), "P4 Info")


def classify_alert_type(event_time, update_time=None, severity="Unknown", tier="P4", source_text=""):
    now = utc_now()
    source_low = str(source_text or "").lower()
    if any(k in source_low for k in ["upgraded", "rapid intensification", "red alert", "escalat"]):
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
    if severity in {"Critical", "Red", "Orange"} or tier in {"P1", "P2"}:
        return "Active Watch"
    return "Monitoring"


def alert_css_type(label):
    if label == "New Event":
        return "New"
    if label == "Event Update":
        return "Update"
    if label == "Escalation":
        return "Escalation"
    if label == "Active Watch":
        return "Watch"
    return "Monitoring"


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


def expected_impact(peril, severity, intensity="", country=""):
    p = str(peril)
    s = str(severity)
    text = str(intensity or "").lower()
    if p == "Earthquake":
        if s in {"Critical", "Red"}:
            return "Expect aftershocks, building-damage reports, possible casualties, infrastructure disruption, and business interruption. Check ShakeMap for impacted footprint."
        return "Monitor aftershocks, local damage reports, casualty updates, and utility or transport disruption near the epicentre."
    if p == "Tropical Cyclone":
        if any(k in text for k in ["category 4", "category 5"]) or s in {"Critical", "Red"}:
            return "Expect destructive wind, surge, heavy rainfall, inland flooding, prolonged outages, transport disruption, and fast-changing insured loss relevance."
        return "Expect track changes, rainfall/flood risk, coastal impacts, warnings, and hazard expansion beyond the center track."
    if p == "Flood":
        return "Expect river or flash-flood impacts, road closures, evacuation activity, industrial and property damage, and later loss updates."
    if p == "Wildfire":
        return "Expect active perimeter change, evacuation orders, smoke impacts, property loss potential, and later insured loss development."
    if p == "Volcano":
        return "Expect ashfall, aviation disruption, official exclusion zones, and secondary hazards such as lahars or lava flow depending on the volcano."
    if p == "Severe Storm":
        return "Expect wind, hail, tornado, or convective-flood damage reports with rapid local escalation or de-escalation."
    return "Monitor official source updates, verified news, casualty reports, and any public loss commentary."


def impact_region_text(peril, location, country, track_available=False):
    if peril == "Tropical Cyclone":
        if track_available:
            return "Track/cone and related products are available. Impact area is wider than the storm center and may include wind, surge, and rainfall zones."
        return "Potential impact area depends on advisory track, cone, wind field, rainfall, and surge zones."
    if peril == "Earthquake":
        return "Epicentre shown on map; true impacted area is better represented by the ShakeMap shaking-intensity footprint."
    if peril == "Wildfire":
        return "Map point indicates event location; full impact should be interpreted with perimeter or active-fire extent data."
    if peril == "Flood":
        return "Flood impact often extends across a broader river basin or urban footprint than the map point alone."
    return f"Primary reported area: {location or country or 'Unknown'}."


def analyst_action(row):
    tier = row.get("Notification_Tier", "P4")
    if tier == "P1":
        return "Notify management quickly, check exposure relevance, and monitor official/vendor updates every 15–30 minutes."
    if tier == "P2":
        return "Keep on analyst watchlist, verify escalation, exposed geographies, and any public casualty or loss commentary."
    return "Monitor for meaningful updates, escalation, or public loss relevance."


def next_update_hint(row):
    peril = row.get("Peril", "Other")
    source = row.get("Source_Name", "")
    if peril == "Tropical Cyclone":
        return "Next advisory cycle or sooner if rapid intensification / landfall threat develops."
    if source == "USGS":
        return "Watch for ShakeMap / impact updates over the next 15–60 minutes."
    return "Monitor source changes and verified follow-up reporting."


def today_value(value, year, annual_rate=0.03):
    try:
        return round(float(value) * ((1 + annual_rate) ** max(0, CURRENT_YEAR - int(year))), 1)
    except Exception:
        return None


# ============================================================
# Source fetchers
# ============================================================
@st.cache_data(ttl=300)
def fetch_usgs_events():
    rows = []
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
            sev = eq_severity(mag)
            peril = "Earthquake"
            intensity = f"Magnitude {mag}; depth {coords[2] if len(coords) > 2 else 'Unknown'} km"
            tier = notification_tier(sev, peril, intensity)
            alert_type = classify_alert_type(event_dt, updated_dt, sev, tier, intensity)

            rows.append({
                "Event_ID": f"USGS-{feature.get('id', make_id('EQ', place))}",
                "Event_Name": f"M{mag} earthquake – {place}",
                "Peril": peril,
                "Event_Status": "Active",
                "Alert_Type": alert_type,
                "Severity": sev,
                "Notification_Tier": tier,
                "Country": extract_country(place),
                "Location_Label": place,
                "Latitude": coords[1] if len(coords) > 1 else None,
                "Longitude": coords[0] if len(coords) > 0 else None,
                "Start_Date": event_dt.strftime("%Y-%m-%d %H:%M UTC") if event_dt else "",
                "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_text(),
                "Source_Name": "USGS",
                "Source_Link": props.get("url", ""),
                "Detail_Link": props.get("detail", ""),
                "Physical_Intensity": intensity,
                "Human_Impact": "Not yet confirmed in source feed",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "High for hazard; Low for damage/loss",
                "Why_It_Matters": "USGS provides rapid earthquake hazard parameters. Human and insurance impacts require follow-up reporting.",
                "What_To_Expect": expected_impact(peril, sev, intensity, extract_country(place)),
                "Impact_Region": impact_region_text(peril, place, extract_country(place)),
                "Management_Summary": f"USGS reports a magnitude {mag} earthquake near {place}. Hazard parameters are available; impact and loss remain uncertain.",
                "Track_Info": "Use USGS ShakeMap for shaking footprint where available.",
                "Map_Mode": "Point + ShakeMap",
            })
    except Exception as exc:
        st.warning(f"USGS fetch failed: {exc}")
    return rows


@st.cache_data(ttl=300)
def fetch_gdacs_events():
    rows = []
    try:
        feed = feedparser.parse(GDACS_RSS_URL)
        for entry in feed.entries[:60]:
            title = getattr(entry, "title", "GDACS event")
            summary = clean(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            event_dt = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
            updated_dt = parse_dt(getattr(entry, "updated", None))
            sev = gdacs_severity(title, summary)
            peril = infer_peril(title + " " + summary)
            tier = notification_tier(sev, peril, summary)
            alert_type = classify_alert_type(event_dt, updated_dt, sev, tier, summary)

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

            rows.append({
                "Event_ID": make_id("GDACS", title + link),
                "Event_Name": title,
                "Peril": peril,
                "Event_Status": "Active",
                "Alert_Type": alert_type,
                "Severity": sev,
                "Notification_Tier": tier,
                "Country": extract_country(title),
                "Location_Label": title,
                "Latitude": lat,
                "Longitude": lon,
                "Start_Date": event_dt.strftime("%Y-%m-%d %H:%M UTC") if event_dt else "",
                "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_text(),
                "Source_Name": "GDACS",
                "Source_Link": link,
                "Detail_Link": "",
                "Physical_Intensity": short(summary, 220) or "See GDACS alert details",
                "Human_Impact": "Check humanitarian / official follow-up sources",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "Medium/High for alert state; Low for loss",
                "Why_It_Matters": "GDACS highlights potentially significant sudden-onset disasters and alert changes.",
                "What_To_Expect": expected_impact(peril, sev, summary, extract_country(title)),
                "Impact_Region": impact_region_text(peril, title, extract_country(title)),
                "Management_Summary": f"GDACS alert: {title}. Follow impact, escalation/de-escalation, and any public economic or insured loss commentary.",
                "Track_Info": "Map point shown when feed coordinates are available.",
                "Map_Mode": "Point / alert feed",
            })
    except Exception as exc:
        st.warning(f"GDACS fetch failed: {exc}")
    return rows


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
def fetch_nhc_products_rss():
    rows = []
    for basin, url in NHC_GIS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = clean(getattr(entry, "title", ""))
                if not title:
                    continue
                link = getattr(entry, "link", "")
                published = getattr(entry, "published", "") or getattr(entry, "updated", "")
                storm_name = ""
                if " - " in title:
                    right = title.split(" - ", 1)[1]
                    storm_name = re.sub(r"\([^)]*\)", "", right).strip()
                    storm_name = re.sub(
                        r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)\s+",
                        "", storm_name,
                        flags=re.I,
                    ).strip()

                product = "Other"
                low = title.lower()
                if "summary" in low:
                    product = "Summary"
                elif "forecast track" in low:
                    product = "Forecast Track"
                elif "cone" in low:
                    product = "Cone"
                elif "watch" in low or "warning" in low:
                    product = "Watches / Warnings"
                elif "wind speed probabilities" in low or "wsp" in low:
                    product = "Wind Speed Probability"
                elif "best track" in low:
                    product = "Preliminary Best Track"
                elif "wind field" in low:
                    product = "Wind Field"

                rows.append({
                    "Basin": basin,
                    "Title": title,
                    "Product": product,
                    "Storm_Name": storm_name,
                    "Published": published,
                    "Link": link,
                    "Raw": entry,
                })
        except Exception:
            continue
    return rows


@st.cache_data(ttl=300)
def fetch_nhc_products_kmz_fallback():
    rows = []
    try:
        content = requests.get(NHC_ACTIVE_KMZ, timeout=25).content
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            kml_name = next((n for n in zf.namelist() if n.lower().endswith(".kml")), None)
            if not kml_name:
                return rows
            root = ET.fromstring(zf.read(kml_name))
            for elem in root.iter():
                tag = elem.tag.split("}")[-1]
                if tag != "NetworkLink":
                    continue
                name = ""
                href = ""
                for child in elem.iter():
                    ctag = child.tag.split("}")[-1]
                    if ctag == "name" and not name:
                        name = clean(child.text or "")
                    if ctag == "href" and not href:
                        href = clean(child.text or "")
                if not href:
                    continue
                low = name.lower()
                product = "Other"
                if "forecast track" in low:
                    product = "Forecast Track"
                elif "cone" in low:
                    product = "Cone"
                elif "watch" in low or "warning" in low:
                    product = "Watches / Warnings"
                elif "wind speed probabilities" in low:
                    product = "Wind Speed Probability"
                elif "best track" in low:
                    product = "Preliminary Best Track"
                elif "wind field" in low:
                    product = "Wind Field"
                elif "summary" in low:
                    product = "Summary"

                rows.append({
                    "Basin": "NHC Active",
                    "Title": name or href,
                    "Product": product,
                    "Storm_Name": "",
                    "Published": "",
                    "Link": href,
                    "Raw": None,
                })
    except Exception:
        pass
    return rows


@st.cache_data(ttl=300)
def fetch_nhc_products():
    rows = fetch_nhc_products_rss()
    if rows:
        return pd.DataFrame(rows)
    fallback = fetch_nhc_products_kmz_fallback()
    return pd.DataFrame(fallback)


@st.cache_data(ttl=300)
def fetch_nhc_events():
    rows = []
    products = fetch_nhc_products()
    if products.empty:
        return rows

    summary_products = products[products["Product"] == "Summary"].copy()

    # Preferred: rich RSS products with raw entry fields
    for _, prod in summary_products.iterrows():
        entry = prod.get("Raw", None)
        if entry is None:
            continue

        title = prod["Title"]
        link = prod["Link"]
        published_dt = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
        updated_dt = parse_dt(getattr(entry, "updated", None))
        summary = clean(getattr(entry, "summary", ""))

        storm_type = get_entry_attr(entry, "nhc_type", "type")
        name = get_entry_attr(entry, "nhc_name", "name")
        atcf = get_entry_attr(entry, "nhc_atcf", "atcf")
        center = get_entry_attr(entry, "nhc_center", "center")
        movement = get_entry_attr(entry, "nhc_movement", "movement")
        pressure = get_entry_attr(entry, "nhc_pressure", "pressure")
        headline = get_entry_attr(entry, "nhc_headline", "headline")
        wind = get_entry_attr(entry, "nhc_wind", "wind")

        if not name and " - " in title:
            right = title.split(" - ", 1)[1]
            right = re.sub(r"\([^)]*\)", "", right).strip()
            name = re.sub(
                r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)\s+",
                "", right,
                flags=re.I,
            ).strip()
            if not storm_type:
                m = re.match(
                    r"^(Hurricane|Tropical Storm|Tropical Depression|Potential Tropical Cyclone|Post-Tropical Cyclone|Subtropical Storm)",
                    right,
                    flags=re.I,
                )
                storm_type = m.group(1) if m else "Tropical Cyclone"

        lat, lon = parse_nhc_center(center)
        cat = category_from_wind(wind) or storm_type or "Tropical Cyclone"
        intensity = "; ".join([
            x for x in [
                cat,
                f"Wind {wind}" if wind else "",
                f"Pressure {pressure}" if pressure else "",
                f"Movement {movement}" if movement else "",
            ] if x
        ]) or summary or "NHC tropical cyclone summary"

        sev = "Red" if "category 4" in intensity.lower() or "category 5" in intensity.lower() else "Orange" if "hurricane" in intensity.lower() else "Amber"
        peril = "Tropical Cyclone"
        tier = notification_tier(sev, peril, intensity)
        alert_type = classify_alert_type(published_dt, updated_dt, sev, tier, f"{headline} {summary} {intensity}")

        storm_display = " ".join([str(storm_type or "Tropical Cyclone").strip(), str(name or "").strip()]).strip()
        if not storm_display:
            storm_display = title

        name_simple = str(name or storm_display).lower()
        atcf_simple = str(atcf or "").lower()
        sub = products[
            products["Title"].str.lower().str.contains(re.escape(name_simple), na=False) |
            products["Title"].str.lower().str.contains(re.escape(atcf_simple), na=False)
        ] if (name_simple or atcf_simple) else pd.DataFrame()
        track_available = not sub[sub["Product"].isin(["Forecast Track", "Cone", "Preliminary Best Track", "Wind Speed Probability", "Watches / Warnings"])].empty

        rows.append({
            "Event_ID": make_id("NHC", f"{prod['Basin']}-{storm_display}-{title}"),
            "Event_Name": storm_display,
            "Peril": peril,
            "Event_Status": "Active",
            "Alert_Type": alert_type,
            "Severity": sev,
            "Notification_Tier": tier,
            "Country": prod["Basin"],
            "Location_Label": prod["Basin"],
            "Latitude": lat,
            "Longitude": lon,
            "Start_Date": published_dt.strftime("%Y-%m-%d %H:%M UTC") if published_dt else "",
            "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_text(),
            "Source_Name": "NOAA/NHC",
            "Source_Link": link,
            "Detail_Link": link,
            "Physical_Intensity": intensity,
            "Human_Impact": "Check local warnings, NHC products, and verified news",
            "Economic_Loss": "Unknown",
            "Insured_Loss": "Unknown",
            "Industry_Loss_Status": "Not yet reported",
            "Confidence_Level": "High for advisory / track context; Low for loss",
            "Why_It_Matters": "NHC provides official track, cone, warning and wind-probability products for active storms in its basins.",
            "What_To_Expect": expected_impact(peril, sev, intensity, prod["Basin"]),
            "Impact_Region": impact_region_text(peril, prod["Basin"], prod["Basin"], track_available=track_available),
            "Management_Summary": f"NHC active tropical cyclone advisory product: {storm_display}. Monitor forecast track, cone, warnings, rainfall, surge, and wind footprint.",
            "Track_Info": "Use Cyclone tab or Footprint tab to open mapped NHC track/cone products when available.",
            "Map_Mode": "Track / cone / active products",
            "NHC_Storm_Name": str(name or storm_display),
            "NHC_Basin": prod["Basin"],
        })

    return rows


@st.cache_data(ttl=300)
def load_live_events():
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


@st.cache_data(ttl=600)
def fetch_usgs_shakemap_status(detail_url):
    if not detail_url:
        return {"available": False, "url": "", "note": "No USGS detail URL is available for this event."}
    try:
        data = requests.get(detail_url, timeout=18).json()
        products = data.get("properties", {}).get("products", {})
        shakemaps = products.get("shakemap", [])
        if not shakemaps:
            return {"available": False, "url": detail_url, "note": "No ShakeMap product is listed yet."}
        contents = shakemaps[0].get("contents", {}) or {}
        link = ""
        for key, val in contents.items():
            if "download/intensity.jpg" in key or "download/intensity.pdf" in key or "download/grid.xml" in key:
                link = val.get("url", "")
                break
        return {
            "available": True,
            "url": link or detail_url,
            "note": "USGS ShakeMap product is available. Use it for the shaking-intensity footprint rather than the epicentre alone."
        }
    except Exception as exc:
        return {"available": False, "url": detail_url, "note": f"Could not read ShakeMap detail yet: {exc}"}


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
            if len(rows) >= 10:
                break
    except Exception:
        pass
    return pd.DataFrame(rows)


@st.cache_data
def load_history():
    records = [
        ("HIST-001", "Hurricane Andrew", 1992, "United States", "Florida / Louisiana", "Tropical Cyclone", 27.3, 15.5, 15.5, 65, 25.3, -80.5, "Historical hurricane track should come from NOAA historical hurricane track tools / IBTrACS."),
        ("HIST-002", "Northridge Earthquake", 1994, "United States", "California", "Earthquake", 44.0, 15.3, 15.3, 57, 34.2, -118.5, "Earthquake footprint should be interpreted with ShakeMap / intensity footprint, not point only."),
        ("HIST-003", "Kobe / Great Hanshin Earthquake", 1995, "Japan", "Kobe", "Earthquake", 100.0, 3.0, 3.0, 6434, 34.6, 135.0, "Earthquake footprint should be interpreted with ShakeMap / intensity footprint, not point only."),
        ("HIST-004", "Hurricane Katrina", 2005, "United States", "Louisiana / Mississippi", "Tropical Cyclone", 125.0, 65.0, 65.0, 1833, 29.9, -89.9, "Historical hurricane track should come from NOAA historical hurricane track tools / IBTrACS."),
        ("HIST-005", "Wenchuan / Sichuan Earthquake", 2008, "China", "Sichuan", "Earthquake", 150.0, 1.0, 1.0, 87587, 31.0, 103.4, "Impacted area extends beyond epicentre."),
        ("HIST-006", "Chile Maule Earthquake", 2010, "Chile", "Maule / Concepción", "Earthquake", 30.0, 8.0, 8.0, 525, -35.9, -72.7, "Impacted area extends beyond epicentre."),
        ("HIST-007", "Tohoku Earthquake & Tsunami", 2011, "Japan", "Tohoku", "Earthquake / Tsunami", 235.0, 35.0, 35.0, 19759, 38.3, 142.4, "Coastal tsunami impact extends well beyond epicentre."),
        ("HIST-008", "Thailand Floods", 2011, "Thailand", "Central Thailand", "Flood", 46.5, 16.0, 16.0, 815, 14.0, 100.6, "Flood footprint should be treated as a wider basin / regional extent."),
        ("HIST-009", "Christchurch Earthquakes", 2010, "New Zealand", "Canterbury", "Earthquake", 40.0, 30.0, 30.0, 185, -43.5, 172.6, "Earthquake footprint should be interpreted with intensity footprint."),
        ("HIST-010", "Hurricane Sandy", 2012, "United States", "Northeast U.S.", "Tropical Cyclone / Storm Surge", 70.0, 30.0, 30.0, 233, 40.7, -74.0, "Track and surge footprint should come from NOAA historical tools."),
        ("HIST-011", "Central Europe Floods", 2013, "Germany / Central Europe", "Germany / Austria / Czechia", "Flood", 16.0, 4.0, 4.0, 25, 48.2, 12.7, "Flood impact extends across multiple countries and river basins."),
        ("HIST-012", "Hurricane Harvey", 2017, "United States", "Texas", "Tropical Cyclone / Flood", 125.0, 30.0, 30.0, 107, 29.8, -95.4, "Track should be treated together with rainfall/flood footprint."),
        ("HIST-013", "Hurricane Irma", 2017, "Caribbean / United States", "Caribbean / Florida", "Tropical Cyclone", 77.0, 32.0, 32.0, 134, 25.8, -80.2, "Historical hurricane track should come from NOAA historical hurricane track tools / IBTrACS."),
        ("HIST-014", "Hurricane Maria", 2017, "Puerto Rico / Caribbean", "Puerto Rico", "Tropical Cyclone", 90.0, 32.0, 32.0, 3059, 18.2, -66.5, "Historical hurricane track should come from NOAA historical hurricane track tools / IBTrACS."),
        ("HIST-015", "Camp Fire", 2018, "United States", "California", "Wildfire", 16.5, 12.0, 12.0, 85, 39.8, -121.4, "Wildfire perimeter is more informative than a point."),
        ("HIST-016", "Typhoon Jebi", 2018, "Japan", "Kansai", "Tropical Cyclone", 13.0, 12.0, 12.0, 17, 34.7, 135.5, "Historical tropical-cyclone track should come from IBTrACS or agency track archive."),
        ("HIST-017", "Australia Black Summer Bushfires", 2019, "Australia", "NSW / Victoria", "Wildfire", 100.0, 2.0, 2.0, 34, -36.5, 148.0, "Wildfire perimeter should be used for footprint."),
        ("HIST-018", "Europe Floods", 2021, "Germany / Belgium", "Ahr Valley / Belgium", "Flood", 54.0, 13.0, 13.0, 243, 50.5, 6.5, "Regional flood footprint is larger than a point."),
        ("HIST-019", "Hurricane Ida", 2021, "United States", "Louisiana / Northeast U.S.", "Tropical Cyclone / Flood", 75.0, 36.0, 36.0, 107, 29.9, -90.1, "Track and inland flood footprint should both be considered."),
        ("HIST-020", "Hurricane Ian", 2022, "United States", "Florida", "Tropical Cyclone / Storm Surge", 113.0, 60.0, 60.0, 161, 26.6, -82.0, "Track and surge footprint should both be considered."),
        ("HIST-021", "Türkiye–Syria Earthquakes", 2023, "Türkiye / Syria", "Kahramanmaraş", "Earthquake", 100.0, 5.0, 5.0, 59000, 37.2, 37.0, "Impacted area extends beyond epicentre."),
        ("HIST-022", "Hurricane Otis", 2023, "Mexico", "Acapulco", "Tropical Cyclone", 15.0, 2.0, 2.0, 52, 16.9, -99.8, "Historical hurricane track should come from NOAA / IBTrACS."),
        ("HIST-023", "Noto Peninsula Earthquake", 2024, "Japan", "Ishikawa", "Earthquake", 17.0, 3.0, 3.0, 240, 37.5, 137.2, "Impacted area extends beyond epicentre."),
        ("HIST-024", "Hurricane Beryl", 2024, "Caribbean / United States", "Caribbean / Texas", "Tropical Cyclone", 7.0, 3.0, 3.0, 70, 29.3, -94.8, "Track should be shown from agency historical track data."),
        ("HIST-025", "Los Angeles Wildfires", 2025, "United States", "California", "Wildfire", 100.0, 40.0, 40.0, None, 34.1, -118.3, "Wildfire perimeter should be used for footprint."),
    ]
    cols = ["Event_ID", "Event_Name", "Year", "Country", "Region", "Peril",
            "Economic_Loss_USD_Bn_Reported", "Insured_Loss_USD_Bn_Reported",
            "Industry_Loss_USD_Bn_Reported", "Fatalities", "Latitude", "Longitude", "Footprint_Note"]
    df = pd.DataFrame(records, columns=cols)
    for col in ["Economic_Loss_USD_Bn_Reported", "Insured_Loss_USD_Bn_Reported", "Industry_Loss_USD_Bn_Reported"]:
        df[col.replace("_Reported", "_Today_Approx")] = df.apply(lambda r: today_value(r[col], r["Year"]), axis=1)
    df["Inflation_Method"] = "Approximate 3% annual USD compounding; replace with official CPI/licensed loss tables for production use."
    return df


# ============================================================
# Map helpers
# ============================================================
def kml_bytes_from_url(url):
    if not url:
        return None
    try:
        content = requests.get(url, timeout=25).content
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
    lines, polygons, points = [], [], []
    if not kml_bytes:
        return lines, polygons, points
    try:
        root = ET.fromstring(kml_bytes)

        def coords_to_pairs(text):
            arr = []
            for chunk in re.split(r"\s+", str(text or "").strip()):
                parts = chunk.split(",")
                if len(parts) >= 2:
                    lon = safe_float(parts[0])
                    lat = safe_float(parts[1])
                    if lon is not None and lat is not None:
                        arr.append([lon, lat])
            return arr

        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "LineString":
                for child in elem.iter():
                    if child.tag.split("}")[-1] == "coordinates":
                        arr = coords_to_pairs(child.text)
                        if len(arr) >= 2:
                            lines.append(arr)
            elif tag == "Polygon":
                for child in elem.iter():
                    if child.tag.split("}")[-1] == "coordinates":
                        arr = coords_to_pairs(child.text)
                        if len(arr) >= 3:
                            polygons.append(arr)
            elif tag == "Point":
                for child in elem.iter():
                    if child.tag.split("}")[-1] == "coordinates":
                        arr = coords_to_pairs(child.text)
                        if arr:
                            points.append(arr[0])
    except Exception:
        pass
    return lines, polygons, points


def live_points_map(df):
    m = df.dropna(subset=["Latitude", "Longitude"]).copy()
    if m.empty:
        st.info("No coordinates are available for this selection.")
        return
    m["lat"] = pd.to_numeric(m["Latitude"], errors="coerce")
    m["lon"] = pd.to_numeric(m["Longitude"], errors="coerce")
    m = m.dropna(subset=["lat", "lon"])
    if m.empty:
        st.info("No valid coordinates are available.")
        return

    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=m,
            get_position="[lon, lat]",
            get_fill_color="Map_Color",
            get_radius=85000,
            pickable=True,
            auto_highlight=True,
        )
    ]
    view = pdk.ViewState(latitude=m["lat"].mean(), longitude=m["lon"].mean(), zoom=1.2, pitch=0)
    tooltip = {
        "html": "<b>{Event_Name}</b><br/>Alert: {Alert_Type}<br/>Severity: {Severity}<br/>Priority: {Notification_Tier}<br/>Source: {Source_Name}",
        "style": {"backgroundColor": "#0f172a", "color": "white"},
    }
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip=tooltip), use_container_width=True)


def match_nhc_products_for_event(event, products):
    name = str(event.get("NHC_Storm_Name") or event.get("Event_Name") or "").lower()
    basin = str(event.get("NHC_Basin") or "").lower()
    if products.empty:
        return products

    name_simple = re.sub(r"^(hurricane|tropical storm|tropical depression|potential tropical cyclone|post-tropical cyclone|subtropical storm)\s+", "", name).strip()
    mask = pd.Series([False] * len(products))
    if name_simple:
        mask = mask | products["Storm_Name"].fillna("").str.lower().str.contains(re.escape(name_simple), regex=True)
        mask = mask | products["Title"].fillna("").str.lower().str.contains(re.escape(name_simple), regex=True)
    if basin and not mask.any():
        mask = products["Basin"].fillna("").str.lower().str.contains(re.escape(basin), regex=True)
    return products[mask].copy()


def nhc_footprint_map(event):
    products = fetch_nhc_products()
    if products.empty:
        st.info("No NHC product list is available right now.")
        return

    subset = match_nhc_products_for_event(event, products)
    if subset.empty:
        st.info("No matching NHC GIS products are available for this storm right now.")
        return

    line_rows, poly_rows, point_rows = [], [], []

    for _, prod in subset.iterrows():
        if prod["Product"] not in ["Forecast Track", "Cone", "Watches / Warnings", "Wind Speed Probability", "Preliminary Best Track"]:
            continue
        link = str(prod["Link"] or "")
        if not link.lower().endswith((".kml", ".kmz")):
            continue
        raw = kml_bytes_from_url(link)
        lines, polys, points = parse_kml_geometries(raw)

        for path in lines[:8]:
            line_rows.append({"path": path, "title": prod["Title"], "product": prod["Product"]})
        for poly in polys[:8]:
            poly_rows.append({"polygon": poly, "title": prod["Title"], "product": prod["Product"]})
        for pt in points[:80]:
            point_rows.append({"lon": pt[0], "lat": pt[1], "title": prod["Title"], "product": prod["Product"]})

    layers = []
    if poly_rows:
        layers.append(
            pdk.Layer(
                "PolygonLayer",
                data=pd.DataFrame(poly_rows),
                get_polygon="polygon",
                get_fill_color=[59, 130, 246, 50],
                get_line_color=[37, 99, 235, 220],
                line_width_min_pixels=1,
                pickable=True,
            )
        )
    if line_rows:
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=pd.DataFrame(line_rows),
                get_path="path",
                get_color=[14, 116, 144, 230],
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
                get_fill_color=[29, 78, 216, 200],
                pickable=True,
            )
        )

    lat = safe_float(event.get("Latitude"))
    lon = safe_float(event.get("Longitude"))
    if lat is not None and lon is not None:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=pd.DataFrame([{"lat": lat, "lon": lon, "title": event.get("Event_Name"), "product": "Current position"}]),
                get_position="[lon, lat]",
                get_radius=90000,
                get_fill_color=[15, 23, 42, 220],
                pickable=True,
            )
        )

    if not layers:
        st.info("Product links are available, but no parseable track or cone geometry could be drawn inside the app.")
    else:
        all_lats, all_lons = [], []
        for row in line_rows:
            for lon2, lat2 in row["path"]:
                all_lons.append(lon2)
                all_lats.append(lat2)
        for row in poly_rows:
            for lon2, lat2 in row["polygon"]:
                all_lons.append(lon2)
                all_lats.append(lat2)
        for row in point_rows:
            all_lons.append(row["lon"])
            all_lats.append(row["lat"])
        if lat is not None and lon is not None:
            all_lats.append(lat)
            all_lons.append(lon)

        view = pdk.ViewState(
            latitude=sum(all_lats) / len(all_lats) if all_lats else 15,
            longitude=sum(all_lons) / len(all_lons) if all_lons else -60,
            zoom=3 if all_lats else 1,
            pitch=0,
        )
        tooltip = {
            "html": "<b>{product}</b><br/>{title}",
            "style": {"backgroundColor": "#0f172a", "color": "white"},
        }
        st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip=tooltip), use_container_width=True)

    st.markdown("**Available NHC product links**")
    for _, row in subset.head(10).iterrows():
        st.markdown(f"- **{row['Product']}** — [{short(row['Title'], 90)}]({row['Link']})")


def history_map(hist_df):
    m = hist_df.dropna(subset=["Latitude", "Longitude"]).copy()
    if m.empty:
        st.info("No historical coordinates are available for this selection.")
        return
    m["lat"] = pd.to_numeric(m["Latitude"], errors="coerce")
    m["lon"] = pd.to_numeric(m["Longitude"], errors="coerce")
    m = m.dropna(subset=["lat", "lon"])
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=m,
        get_position="[lon, lat]",
        get_fill_color=[37, 99, 235, 180],
        get_radius=90000,
        pickable=True,
        auto_highlight=True,
    )
    view = pdk.ViewState(latitude=m["lat"].mean(), longitude=m["lon"].mean(), zoom=1.1, pitch=0)
    tooltip = {
        "html": "<b>{Event_Name}</b><br/>Year: {Year}<br/>Peril: {Peril}<br/>Reported insured loss: USD {Insured_Loss_USD_Bn_Reported}bn<br/>{Footprint_Note}",
        "style": {"backgroundColor": "#0f172a", "color": "white"},
    }
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip=tooltip), use_container_width=True)


# ============================================================
# Render helpers
# ============================================================
def event_badges(row):
    sev = row.get("Severity", "Unknown")
    tier = row.get("Notification_Tier", "P4")
    peril = row.get("Peril", "Other")
    alert_type = row.get("Alert_Type", "Monitoring")
    return (
        f"<span class='badge b-type-{alert_css_type(alert_type)}'>{alert_type}</span>"
        f"<span class='badge b-tier-{tier}'>{tier_label(tier)}</span>"
        f"<span class='badge b-sev-{sev}'>{sev}</span>"
        f"<span class='badge b-peril'>{emoji(peril)} {peril}</span>"
    )


def render_event_card(row):
    sev = row.get("Severity", "Unknown")
    eyebrow = f"{row.get('Country', 'Unknown')} • {row.get('Source_Name', 'Source')} • {row.get('Latest_Update_Date', '')}"
    st.markdown(
        f"""
        <div class="card event-card sev-border-{sev}">
            {event_badges(row)}
            <div class="eyebrow">{short(eyebrow, 90)}</div>
            <div class="event-title">{row.get('Event_Name', 'Unnamed event')}</div>
            <div class="event-meta">
                <b>Intensity:</b> {short(row.get('Physical_Intensity', 'Unknown'), 125)}<br>
                <b>Impact area:</b> {short(row.get('Impact_Region', ''), 120)}<br>
                <b>What to expect:</b> {short(row.get('What_To_Expect', ''), 140)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_news_card(row):
    st.markdown(
        f"""
        <div class="card">
            <div class="eyebrow">{row.get('Source', 'News')}</div>
            <div class="event-title">{row.get('Title', 'Untitled')}</div>
            <div class="event-meta">
                <b>Published:</b> {row.get('Published', 'Unknown')}<br>
                <a href="{row.get('Link')}" target="_blank">Open article</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_history_card(row):
    st.markdown(
        f"""
        <div class="card">
            <span class="badge b-tier-P3">{row.get('Year')}</span>
            <span class="badge b-peril">{emoji(row.get('Peril'))} {row.get('Peril')}</span>
            <div class="event-title">{row.get('Event_Name')}</div>
            <div class="event-meta">
                <b>Country:</b> {row.get('Country')}<br>
                <b>Region:</b> {row.get('Region')}<br>
                <b>Economic loss:</b> USD {row.get('Economic_Loss_USD_Bn_Reported')}bn reported / ~USD {row.get('Economic_Loss_USD_Bn_Today_Approx')}bn today<br>
                <b>Insured loss:</b> USD {row.get('Insured_Loss_USD_Bn_Reported')}bn reported / ~USD {row.get('Insured_Loss_USD_Bn_Today_Approx')}bn today<br>
                <b>Footprint note:</b> {row.get('Footprint_Note')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def management_text(event):
    return f"""MANAGEMENT OVERVIEW – {event.get('Event_Name')}

Alert type: {event.get('Alert_Type')}
Priority: {tier_label(event.get('Notification_Tier'))}
Peril: {event.get('Peril')}
Severity: {event.get('Severity')}
Country / basin: {event.get('Country')}
Location: {event.get('Location_Label')}
Latest update: {event.get('Latest_Update_Date')}
Source: {event.get('Source_Name')}

What happened:
{event.get('Management_Summary')}

Physical intensity:
{event.get('Physical_Intensity')}

Expected developments:
{event.get('What_To_Expect')}

Impact area / footprint:
{event.get('Impact_Region')}

Human impact:
{event.get('Human_Impact')}

Economic / insured loss:
Economic loss: {event.get('Economic_Loss')}
Insured loss: {event.get('Insured_Loss')}
Industry loss status: {event.get('Industry_Loss_Status')}

Why it matters:
{event.get('Why_It_Matters')}

Analyst action:
{event.get('Analyst_Action')}

Next expected update:
{event.get('Next_Update')}

Source link:
{event.get('Source_Link')}
""".strip()


def apply_filters(df):
    st.markdown("<div class='section-title'>Filters</div>", unsafe_allow_html=True)
    with st.expander("Tap to change filters", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            alert_type = st.selectbox("Alert type", ["All"] + sorted(df["Alert_Type"].dropna().unique().tolist()))
            peril = st.selectbox("Peril", ["All"] + sorted(df["Peril"].dropna().unique().tolist()))
        with c2:
            priority = st.selectbox("Priority", ["All", "P1", "P2", "P3", "P4"])
            country = st.selectbox("Country / basin", ["All"] + df["Country"].fillna("Unknown").astype(str).value_counts().index.tolist())
        search = st.text_input("Search event / region / source", placeholder="Search here...")

    out = df.copy()
    if alert_type != "All":
        out = out[out["Alert_Type"] == alert_type]
    if peril != "All":
        out = out[out["Peril"] == peril]
    if priority != "All":
        out = out[out["Notification_Tier"] == priority]
    if country != "All":
        out = out[out["Country"] == country]
    if search.strip():
        needle = search.lower().strip()
        out = out[out.apply(lambda r: needle in " ".join(r.astype(str)).lower(), axis=1)]
    return out


def cyclone_status_box(df):
    nhc = df[df["Source_Name"] == "NOAA/NHC"].copy()
    gdacs_tc = df[df["Peril"] == "Tropical Cyclone"].copy()
    if not nhc.empty:
        names = ", ".join(nhc["Event_Name"].head(4).tolist())
        st.markdown(
            f"<div class='status-band'><b>🌀 Tropical cyclone watch:</b> {len(nhc)} active NHC storm(s) found. {short(names, 140)}</div>",
            unsafe_allow_html=True,
        )
    elif not gdacs_tc.empty:
        names = ", ".join(gdacs_tc["Event_Name"].head(4).tolist())
        st.markdown(
            f"<div class='status-band'><b>🌀 Tropical cyclone watch:</b> No active NHC advisory storm is currently loaded, but {len(gdacs_tc)} cyclone-related alert(s) are visible from other live sources. {short(names, 140)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='status-band'><b>🌀 Tropical cyclone watch:</b> No active NHC tropical-cyclone event is currently in the live feed. When NHC/CPHC active products are available, cyclone events and footprints will appear automatically.</div>",
            unsafe_allow_html=True,
        )


# ============================================================
# App
# ============================================================
def main():
    inject_css()
    refresh_count = st_autorefresh(interval=5 * 60 * 1000, key="catwatch_v7_refresh")

    st.markdown(
        """
        <div class="hero">
            <div class="hero-title">🌍 CatWatch</div>
            <div class="hero-sub">
                Mobile catastrophe alert cockpit for first-to-know monitoring:
                new event, event update, escalation, severity, impacted region,
                map footprint, verified news, historical benchmarks, and quick management overview.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    df = load_live_events()
    if df.empty:
        st.error("No live event data loaded. Please try again.")
        return

    cyclone_status_box(df)
    filt = apply_filters(df)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Live alerts", len(filt))
    with c2:
        st.metric("New / update", int(filt["Alert_Type"].isin(["New Event", "Event Update", "Escalation"]).sum()) if not filt.empty else 0)
    with c3:
        st.metric("P1 / P2", int(filt["Notification_Tier"].isin(["P1", "P2"]).sum()) if not filt.empty else 0)

    col_a, col_b = st.columns([1, 2.2])
    with col_a:
        if st.button("Refresh now"):
            st.cache_data.clear()
            st.rerun()
    with col_b:
        st.markdown(f"<div class='small-note'>Auto-refresh every 5 minutes while the page is open • 30-day live window • refresh count: {refresh_count}</div>", unsafe_allow_html=True)

    if filt.empty:
        st.info("No events match the current filters.")
        return

    selected_name = st.selectbox("Selected alert", filt["Event_Name"].tolist(), index=0)
    event = filt[filt["Event_Name"] == selected_name].iloc[0]

    tabs = st.tabs(["Alerts", "Event", "Map", "Cyclones", "News", "History", "Management"])

    with tabs[0]:
        st.markdown("<div class='section-title'>Alert queue</div>", unsafe_allow_html=True)
        for _, row in filt.head(20).iterrows():
            render_event_card(row)

    with tabs[1]:
        st.markdown("<div class='section-title'>Event detail</div>", unsafe_allow_html=True)
        st.markdown(event_badges(event), unsafe_allow_html=True)
        st.markdown(f"### {event.get('Event_Name')}")
        st.markdown(
            f"""
            <div class="summary-box">
                <b>Management summary</b><br>
                {event.get('Management_Summary')}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("**What to expect**")
        st.write(event.get("What_To_Expect"))
        st.markdown("**Impact area / footprint context**")
        st.write(event.get("Impact_Region"))

        d1, d2 = st.columns(2)
        d1.write(f"**Intensity:** {event.get('Physical_Intensity')}")
        d1.write(f"**Country / basin:** {event.get('Country')}")
        d1.write(f"**Location:** {event.get('Location_Label')}")
        d1.write(f"**Human impact:** {event.get('Human_Impact')}")
        d2.write(f"**Loss status:** {event.get('Industry_Loss_Status')}")
        d2.write(f"**Confidence:** {event.get('Confidence_Level')}")
        d2.write(f"**Next update:** {event.get('Next_Update')}")
        d2.write(f"**Source:** [{event.get('Source_Name')}]({event.get('Source_Link')})")

        if event.get("Peril") == "Earthquake":
            shake = fetch_usgs_shakemap_status(event.get("Detail_Link", ""))
            klass = "ok-box" if shake["available"] else "warn-box"
            st.markdown(f"<div class='{klass}'><b>USGS ShakeMap:</b> {shake['note']}</div>", unsafe_allow_html=True)
            if shake.get("url"):
                st.markdown(f"[Open ShakeMap / detail product]({shake['url']})")

        if event.get("Peril") == "Tropical Cyclone":
            st.markdown(
                "<div class='info-box'><b>Cyclone note:</b> The impact area should not be interpreted from the storm center alone. Use the advisory track, cone, and related products in the Map or Cyclones tab.</div>",
                unsafe_allow_html=True,
            )

    with tabs[2]:
        st.markdown("<div class='section-title'>Map & footprint</div>", unsafe_allow_html=True)
        if event.get("Peril") == "Tropical Cyclone" or event.get("Source_Name") == "NOAA/NHC":
            st.markdown(
                f"<div class='info-box'><b>Footprint mode:</b> {event.get('Map_Mode')}<br><b>Impact note:</b> {event.get('Impact_Region')}</div>",
                unsafe_allow_html=True,
            )
            nhc_footprint_map(event)
        else:
            st.markdown(
                f"<div class='info-box'><b>Footprint mode:</b> {event.get('Map_Mode')}<br><b>Impact note:</b> {event.get('Impact_Region')}</div>",
                unsafe_allow_html=True,
            )
            live_points_map(pd.DataFrame([event]))

    with tabs[3]:
        st.markdown("<div class='section-title'>Tropical cyclones</div>", unsafe_allow_html=True)
        nhc_events = df[df["Source_Name"] == "NOAA/NHC"].copy()
        gdacs_tc = df[df["Peril"] == "Tropical Cyclone"].copy()

        if nhc_events.empty:
            st.markdown(
                "<div class='warn-box'><b>No active NHC event is currently loaded.</b><br>If there is no active NOAA/NHC tropical-cyclone advisory in the current feed, you will not see a live hurricane event or official NHC footprint here. The app now states this clearly instead of failing silently.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<div class='info-box'><b>Active NHC storms</b><br>These are the events for which NHC product-based track and cone mapping should appear.</div>", unsafe_allow_html=True)
            for _, row in nhc_events.iterrows():
                render_event_card(row)

        if not gdacs_tc.empty and nhc_events.empty:
            st.markdown("<div class='section-title'>Other live cyclone-related alerts</div>", unsafe_allow_html=True)
            for _, row in gdacs_tc.head(10).iterrows():
                render_event_card(row)

        products = fetch_nhc_products()
        if not products.empty:
            st.markdown("**Latest NHC product list**")
            show = products[["Basin", "Product", "Storm_Name", "Published", "Title", "Link"]].copy()
            st.dataframe(show.head(30), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.markdown("<div class='section-title'>Verified news</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='info-box'><b>Note:</b> This tab is for quick situational awareness. Use official sources and specialist vendor/industry sources for decision-making and loss reporting.</div>",
            unsafe_allow_html=True,
        )
        news = fetch_news(event.get("Event_Name"), event.get("Country"), event.get("Peril"))
        if news.empty:
            st.info("No verified news items were found for the selected event yet.")
        else:
            for _, row in news.iterrows():
                render_news_card(row)

    with tabs[5]:
        st.markdown("<div class='section-title'>Historical events</div>", unsafe_allow_html=True)
        hist = load_history()
        with st.expander("Historical filters", expanded=True):
            h1, h2 = st.columns(2)
            with h1:
                h_country = st.selectbox("Country", ["All"] + sorted(hist["Country"].dropna().unique().tolist()))
            with h2:
                h_peril = st.selectbox("Peril", ["All"] + sorted(hist["Peril"].dropna().unique().tolist()))
            h_search = st.text_input("Search by event name", placeholder="Katrina, Harvey, Tohoku...")

        h = hist.copy()
        if h_country != "All":
            h = h[h["Country"] == h_country]
        if h_peril != "All":
            h = h[h["Peril"] == h_peril]
        if h_search.strip():
            h = h[h["Event_Name"].str.lower().str.contains(h_search.lower().strip(), na=False)]

        st.markdown(
            "<div class='warn-box'><b>Historical note:</b> Loss figures are starter benchmark values. For production use, replace them with verified vendor / market / industry-loss datasets and more accurate inflation adjustments.</div>",
            unsafe_allow_html=True,
        )
        history_map(h)
        for _, row in h.sort_values("Year", ascending=False).head(50).iterrows():
            render_history_card(row)

    with tabs[6]:
        st.markdown("<div class='section-title'>Management overview</div>", unsafe_allow_html=True)
        mgmt = management_text(event)
        st.text_area("Management note draft", mgmt, height=430)
        st.download_button(
            "Download note",
            mgmt.encode("utf-8"),
            "catwatch_management_overview.txt",
            "text/plain",
        )


if __name__ == "__main__":
    main()
