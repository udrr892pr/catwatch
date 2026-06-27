
import hashlib
import json
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
# CatWatch v7.4 — Event Integrity & Decision Workflow
# ============================================================

st.set_page_config(
    page_title="CatWatch",
    page_icon="🌍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson"
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
JMA_QUAKE_URL = "https://www.jma.go.jp/bosai/quake/data/list.json"
EMSC_RSS_URL = "https://www.emsc-csem.org/service/rss/rss.php?typ=emsc&magmin=5"
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


def parse_mag_from_text(text):
    m = re.search(r"M(?:agnitude)?\s*([0-9]+(?:\.[0-9]+)?)", str(text or ""), flags=re.I)
    if not m:
        m = re.search(r"mag(?:nitude)?[=:\s]+([0-9]+(?:\.[0-9]+)?)", str(text or ""), flags=re.I)
    return safe_float(m.group(1)) if m else None


def parse_jma_coordinate(coord_text):
    # JMA coordinate examples: +42.6+143.1-80000/ = lat, lon, depth in metres
    m = re.match(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)([+-]\d+)?/", str(coord_text or ""))
    if not m:
        return None, None, None
    lat = safe_float(m.group(1))
    lon = safe_float(m.group(2))
    depth_m = safe_float(m.group(3)) if m.group(3) else None
    depth_km = abs(depth_m) / 1000 if depth_m is not None else None
    return lat, lon, depth_km


def jma_intensity_rank(maxi):
    s = str(maxi or "").strip()
    mapping = {
        "7": 8, "6+": 7, "6-": 6, "5+": 5,
        "5-": 4, "4": 3, "3": 2, "2": 1, "1": 0,
    }
    return mapping.get(s, -1)


def jma_severity(maxi, mag):
    rank = jma_intensity_rank(maxi)
    mag = safe_float(mag)
    if rank >= 7 or (mag is not None and mag >= 7.5):
        return "Critical"
    if rank >= 5 or (mag is not None and mag >= 6.8):
        return "Red"
    if rank >= 3 or (mag is not None and mag >= 5.8):
        return "Orange"
    if rank >= 2 or (mag is not None and mag >= 5.0):
        return "Yellow"
    if rank >= 0:
        return "Green"
    return eq_severity(mag)


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
    if source == "JMA":
        return "Watch JMA intensity/tsunami updates and cross-check USGS/EMSC/GDACS for global context."
    if source == "EMSC":
        return "Cross-check with USGS/local agency and monitor felt reports or revised magnitude/location."
    return "Monitor source changes and verified follow-up reporting."


def market_region(country, location=""):
    text = f"{country} {location}".lower()
    if any(k in text for k in ["japan", "iwate", "hokkaido", "tohoku", "tokyo", "osaka", "fukushima", "honshu", "kyushu", "shikoku"]):
        return "Japan"
    if any(k in text for k in ["united states", "usa", "california", "florida", "texas", "louisiana", "atlantic", "eastern pacific", "central pacific"]):
        return "United States / NHC basin"
    if any(k in text for k in ["germany", "france", "italy", "spain", "belgium", "netherlands", "switzerland", "austria", "united kingdom", "europe"]):
        return "Europe"
    if any(k in text for k in ["australia", "new zealand"]):
        return "Australia / New Zealand"
    return "Global"


def preferred_source_note(row):
    region = market_region(row.get("Country"), row.get("Location_Label"))
    peril = row.get("Peril", "Other")
    if region == "Japan" and peril in {"Earthquake", "Tsunami", "Earthquake / Tsunami"}:
        return "Japan earthquake hierarchy: JMA first, then USGS / EMSC / GDACS for cross-check."
    if row.get("Source_Name") == "NOAA/NHC" or (peril == "Tropical Cyclone" and region == "United States / NHC basin"):
        return "NHC-basin cyclone hierarchy: NOAA/NHC first, then GDACS and verified news for impacts."
    if peril == "Earthquake":
        return "Global earthquake hierarchy: USGS first, EMSC second, GDACS for humanitarian alert colour, local agency where available."
    if region == "Europe" and peril in {"Flood", "Severe Storm", "Tropical Cyclone"}:
        return "Europe hierarchy: national agencies / Copernicus first, then GDACS, with PERILS / broker/vendor notes for market loss."
    return "Global hierarchy: official hazard source first, then GDACS/verified news, then insurance-market loss commentary."


def source_priority_score(row):
    source = str(row.get("Source_Name", ""))
    peril = row.get("Peril", "Other")
    region = market_region(row.get("Country"), row.get("Location_Label"))

    if region == "Japan" and peril in {"Earthquake", "Tsunami", "Earthquake / Tsunami"}:
        return {"JMA": 100, "USGS": 86, "EMSC": 80, "GDACS": 72}.get(source, 55)
    if source == "NOAA/NHC":
        return 100
    if peril == "Earthquake":
        return {"USGS": 92, "EMSC": 84, "JMA": 82, "GDACS": 76}.get(source, 55)
    if peril == "Tropical Cyclone":
        return {"NOAA/NHC": 100, "GDACS": 74}.get(source, 55)
    if source == "GDACS":
        return 74
    return 55


def insurance_relevance_score(row):
    # A pragmatic early-warning score, not a modelled loss estimate.
    score = 0
    score += severity_rank(row.get("Severity", "Unknown")) * 12
    score += {"P1": 28, "P2": 18, "P3": 8, "P4": 2}.get(str(row.get("Notification_Tier", "P4")), 0)
    score += {"New Event": 8, "Event Update": 6, "Escalation": 14, "Active Watch": 6, "Monitoring": 1}.get(str(row.get("Alert_Type", "Monitoring")), 0)
    region = market_region(row.get("Country"), row.get("Location_Label"))
    if region in {"Japan", "United States / NHC basin", "Europe", "Australia / New Zealand"}:
        score += 8
    if row.get("Peril") in {"Tropical Cyclone", "Earthquake", "Flood", "Wildfire", "Severe Storm"}:
        score += 5
    return min(100, int(score))


def insurance_relevance_label(score):
    try:
        score = int(score)
    except Exception:
        score = 0
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    if score >= 25:
        return "Watch"
    return "Low"


def queue_label(row):
    sev_rank = severity_rank(row.get("Severity", "Unknown"))
    tier = row.get("Notification_Tier", "P4")
    relevance = int(row.get("Insurance_Relevance_Score", 0) or 0)
    if row.get("Alert_Type") == "Escalation" or tier in {"P1", "P2"} or sev_rank >= 4 or relevance >= 65:
        return "Executive Alerts"
    return "Recent Global Events"



def loss_watch_score(row):
    """Early insurance-market loss watch score. This is not a modelled loss estimate."""
    score = int(row.get("Insurance_Relevance_Score", 0) or 0)
    sev = row.get("Severity", "Unknown")
    tier = row.get("Notification_Tier", "P4")
    peril = row.get("Peril", "Other")
    region = market_region(row.get("Country"), row.get("Location_Label"))
    intensity = str(row.get("Physical_Intensity", "")).lower()

    if tier == "P1":
        score += 15
    elif tier == "P2":
        score += 8

    if sev in {"Critical", "Red"}:
        score += 15
    elif sev in {"Orange", "Amber"}:
        score += 8

    if peril in {"Tropical Cyclone", "Flood", "Wildfire", "Severe Storm"}:
        score += 8
    if peril in {"Earthquake", "Earthquake / Tsunami", "Tsunami"}:
        score += 6

    if region in {"United States / NHC basin", "Japan", "Europe", "Australia / New Zealand"}:
        score += 8

    if any(k in intensity for k in ["category 4", "category 5", "magnitude 7.5", "magnitude 8", "max jma seismic intensity 6", "max jma seismic intensity 7"]):
        score += 12

    return min(100, int(score))


def loss_watch_label(score):
    try:
        score = int(score)
    except Exception:
        score = 0
    if score >= 80:
        return "High loss watch"
    if score >= 60:
        return "Loss watch"
    if score >= 40:
        return "Developing watch"
    return "Low / monitor"


def loss_watch_stage(row):
    tier = row.get("Notification_Tier", "P4")
    sev = row.get("Severity", "Unknown")
    alert_type = row.get("Alert_Type", "Monitoring")
    loss = str(row.get("Industry_Loss_Status", "")).lower()
    if any(k in loss for k in ["reported", "estimate", "loss", "vendor"]):
        return "Loss commentary stage"
    if alert_type == "Escalation" or tier == "P1" or sev in {"Critical", "Red"}:
        return "Hazard impact triage"
    if tier == "P2" or sev in {"Orange", "Amber"}:
        return "Exposure watch"
    return "Monitoring"


def pcs_perils_relevance(row):
    region = market_region(row.get("Country"), row.get("Location_Label"))
    peril = row.get("Peril", "Other")
    if region == "United States / NHC basin":
        return "PCS / Verisk likely most relevant if insured industry loss emerges; also monitor NHC/NWS/FEMA and model vendors."
    if region == "Europe":
        return "PERILS likely most relevant for qualifying European windstorm/flood industry-loss context; monitor national agencies and broker/model-vendor notes."
    if region == "Japan":
        return "For Japan, prioritize JMA for hazard, then local insurers/reinsurers, PERILS/PCS/vendor commentary if industry loss becomes material."
    if region == "Australia / New Zealand":
        return "Monitor ICA / local insurance-market commentary, BOM/state agencies, and vendor/broker market notes."
    return "Monitor PCS/PERILS where geography/peril is covered; otherwise rely on local insurance associations, broker reports, and model-vendor commentary."


def market_vendor_note(row):
    peril = row.get("Peril", "Other")
    stage = loss_watch_stage(row)
    if stage == "Hazard impact triage":
        return "Focus first on official footprint and exposure geography; vendor/model notes usually follow once hazard parameters stabilize."
    if stage == "Exposure watch":
        return "Track whether the event intersects dense exposure, commercial/industrial assets, or high-insurance-penetration regions."
    if peril == "Tropical Cyclone":
        return "Vendor/model commentary should focus on track, landfall intensity, surge, rainfall, wind-field size, and inland flood."
    if peril == "Earthquake":
        return "Vendor/model commentary should focus on ShakeMap intensity footprint, construction vulnerability, urban exposure, and aftershocks."
    if peril == "Flood":
        return "Vendor/model commentary should focus on affected basins, flood depth/duration, industrial assets, motor/property portfolios, and business interruption."
    return "Monitor official impact data first, then market commentary once loss potential becomes clearer."

def apply_source_priority_engine(df):
    if df.empty:
        return df
    df = df.copy()
    df["Market_Region"] = df.apply(lambda r: market_region(r.get("Country"), r.get("Location_Label")), axis=1)
    df["Source_Priority_Score"] = df.apply(source_priority_score, axis=1)
    df["Preferred_Source_Note"] = df.apply(preferred_source_note, axis=1)
    df["Insurance_Relevance_Score"] = df.apply(insurance_relevance_score, axis=1)
    df["Insurance_Relevance"] = df["Insurance_Relevance_Score"].apply(insurance_relevance_label)
    df["Loss_Watch_Score"] = df.apply(loss_watch_score, axis=1)
    df["Loss_Watch"] = df["Loss_Watch_Score"].apply(loss_watch_label)
    df["Loss_Watch_Stage"] = df.apply(loss_watch_stage, axis=1)
    df["PCS_PERILS_Relevance"] = df.apply(pcs_perils_relevance, axis=1)
    df["Market_Vendor_Note"] = df.apply(market_vendor_note, axis=1)
    df["Queue"] = df.apply(queue_label, axis=1)
    return df


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
def fetch_jma_events():
    rows = []
    try:
        data = requests.get(JMA_QUAKE_URL, timeout=25).json()
        # JMA list is mostly Japan-region events and can include multiple bulletins for same event.
        seen = set()
        for item in data[:80]:
            title = item.get("en_ttl") or item.get("ttl") or "JMA earthquake information"
            location = item.get("en_anm") or item.get("anm") or "Japan region"
            mag = safe_float(item.get("mag"))
            maxi = item.get("maxi") or item.get("int") or ""
            if mag is None and not maxi:
                continue
            eid = item.get("eid") or item.get("json") or f"{location}-{item.get('at')}"
            key = f"{eid}-{location}-{mag}-{maxi}"
            if key in seen:
                continue
            seen.add(key)

            event_dt = parse_dt(item.get("at") or item.get("ctt"))
            updated_dt = parse_dt(item.get("rdt") or item.get("ctt"))
            lat, lon, depth_km = parse_jma_coordinate(item.get("cod"))
            sev = jma_severity(maxi, mag)
            peril = "Earthquake"
            intensity_parts = []
            if mag is not None:
                intensity_parts.append(f"Magnitude {mag}")
            if maxi:
                intensity_parts.append(f"Max JMA seismic intensity {maxi}")
            if depth_km is not None:
                intensity_parts.append(f"depth {depth_km:g} km")
            intensity = "; ".join(intensity_parts) or "JMA earthquake information"
            tier = notification_tier(sev, peril, intensity)
            alert_type = classify_alert_type(event_dt, updated_dt, sev, tier, intensity)
            detail = f"https://www.jma.go.jp/bosai/map.html#contents=earthquake_map&lang=en"

            rows.append({
                "Event_ID": f"JMA-{eid}",
                "Event_Name": f"M{mag if mag is not None else '?'} earthquake – {location}",
                "Peril": peril,
                "Event_Status": "Active",
                "Alert_Type": alert_type,
                "Severity": sev,
                "Notification_Tier": tier,
                "Country": "Japan",
                "Location_Label": location,
                "Latitude": lat,
                "Longitude": lon,
                "Start_Date": event_dt.strftime("%Y-%m-%d %H:%M UTC") if event_dt else "",
                "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_text(),
                "Source_Name": "JMA",
                "Source_Link": detail,
                "Detail_Link": detail,
                "Physical_Intensity": intensity,
                "Human_Impact": "Check JMA / local Japan government updates, NHK/AP/Reuters and infrastructure reports",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "High for Japan hazard/intensity; Low for damage/loss",
                "Why_It_Matters": "JMA is the priority local source for Japan earthquake intensity and tsunami context; cross-check USGS, EMSC and GDACS for global comparison.",
                "What_To_Expect": expected_impact(peril, sev, intensity, "Japan"),
                "Impact_Region": "Japan local intensity footprint matters more than the epicentre alone. Use JMA intensity information and USGS ShakeMap where available.",
                "Management_Summary": f"JMA reports earthquake information for {location}. The key insurance-market trigger is whether local intensity, infrastructure disruption, or damage reports escalate.",
                "Track_Info": "Use JMA seismic-intensity information and cross-check with USGS ShakeMap/EMSC/GDACS.",
                "Map_Mode": "Point + local intensity context",
            })
    except Exception as exc:
        st.warning(f"JMA fetch failed: {exc}")
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


@st.cache_data(ttl=300)
def fetch_emsc_events():
    rows = []
    try:
        feed = feedparser.parse(EMSC_RSS_URL)
        for entry in feed.entries[:50]:
            title = clean(getattr(entry, "title", "EMSC earthquake"))
            summary = clean(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            event_dt = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))
            updated_dt = parse_dt(getattr(entry, "updated", None))
            mag = parse_mag_from_text(title + " " + summary)
            sev = eq_severity(mag)
            peril = "Earthquake"

            lat, lon = None, None
            if hasattr(entry, "georss_point"):
                try:
                    parts = str(entry.georss_point).split()
                    lat, lon = float(parts[0]), float(parts[1])
                except Exception:
                    pass
            if lat is None and hasattr(entry, "where"):
                try:
                    point = entry.where.get("coordinates", [None, None])
                    lon, lat = point[0], point[1]
                except Exception:
                    pass

            # Try to isolate location from common EMSC titles: "M 5.5 - REGION"
            location = title
            if " - " in title:
                location = title.split(" - ", 1)[1].strip()
            tier = notification_tier(sev, peril, summary)
            alert_type = classify_alert_type(event_dt, updated_dt, sev, tier, summary)
            intensity = f"Magnitude {mag}" if mag is not None else short(summary, 160) or "EMSC earthquake update"

            rows.append({
                "Event_ID": make_id("EMSC", title + link),
                "Event_Name": f"M{mag if mag is not None else '?'} earthquake – {location}",
                "Peril": peril,
                "Event_Status": "Active",
                "Alert_Type": alert_type,
                "Severity": sev,
                "Notification_Tier": tier,
                "Country": extract_country(location),
                "Location_Label": location,
                "Latitude": lat,
                "Longitude": lon,
                "Start_Date": event_dt.strftime("%Y-%m-%d %H:%M UTC") if event_dt else "",
                "Latest_Update_Date": updated_dt.strftime("%Y-%m-%d %H:%M UTC") if updated_dt else now_text(),
                "Source_Name": "EMSC",
                "Source_Link": link,
                "Detail_Link": link,
                "Physical_Intensity": intensity,
                "Human_Impact": "Check official local source, USGS, GDACS and verified news",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "Medium/High for rapid earthquake cross-check; Low for loss",
                "Why_It_Matters": "EMSC provides fast independent earthquake cross-check and can surface events/felt reports not yet prominent in other views.",
                "What_To_Expect": expected_impact(peril, sev, intensity, extract_country(location)),
                "Impact_Region": impact_region_text(peril, location, extract_country(location)),
                "Management_Summary": f"EMSC reports an earthquake near {location}. Use this as a cross-check with official local agency, USGS and GDACS.",
                "Track_Info": "Use official local agency and USGS ShakeMap where available for impact footprint.",
                "Map_Mode": "Point / cross-check feed",
            })
    except Exception as exc:
        st.warning(f"EMSC fetch failed: {exc}")
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
    rows.extend(fetch_jma_events())
    rows.extend(fetch_emsc_events())
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
    df = apply_source_priority_engine(df)
    return df.sort_values(["Queue", "Alert_Rank", "Tier_Rank", "Severity_Rank", "Insurance_Relevance_Score", "Source_Priority_Score", "Start_Date_UTC"], ascending=[True, False, False, False, False, False, False])


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
    df["Loss_Data_Status"] = "Indicative starter benchmark"
    df["Loss_Source_Status"] = "Needs validation before management use"
    df["Comparable_Use"] = "Context only; do not treat as modelled or verified loss"
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
        f"<span class='badge b-peril'>{row.get('Queue', 'Recent')}</span>"
    )


def render_event_card(row):
    sev = row.get("Severity", "Unknown")
    eyebrow = f"{row.get('Country', 'Unknown')} • {row.get('Primary_Source_Name', row.get('Source_Name', 'Source'))} • {row.get('Latest_Update_Date', '')}"
    st.markdown(
        f"""
        <div class="card event-card sev-border-{sev}">
            {event_badges(row)}
            <div class="eyebrow">{short(eyebrow, 90)}</div>
            <div class="event-title">{row.get('Event_Name', 'Unnamed event')}</div>
            <div class="event-meta">
                <b>Latest material signal:</b> {short(row.get('What_Changed', 'No material change summary available.'), 140)}<br>
                <b>Intensity:</b> {short(row.get('Physical_Intensity', 'Unknown'), 110)}<br>
                <b>Footprint status:</b> {short(row.get('Map_Mode', 'Point / source feed'), 95)}<br>
                <b>Insurance:</b> {row.get('Insurance_Relevance', '')} • <b>Loss watch:</b> {row.get('Loss_Watch', 'Monitor')} ({row.get('Loss_Watch_Score', 0)}/100)<br>
                <b>Next action:</b> {short(row.get('Analyst_Action', ''), 115)}
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
            <span class="badge b-sev-Unknown">{row.get('Loss_Data_Status', 'Indicative')}</span>
            <div class="event-title">{row.get('Event_Name')}</div>
            <div class="event-meta">
                <b>Country:</b> {row.get('Country')}<br>
                <b>Region:</b> {row.get('Region')}<br>
                <b>Economic loss:</b> USD {row.get('Economic_Loss_USD_Bn_Reported')}bn reported / ~USD {row.get('Economic_Loss_USD_Bn_Today_Approx')}bn today<br>
                <b>Insured loss:</b> USD {row.get('Insured_Loss_USD_Bn_Reported')}bn reported / ~USD {row.get('Insured_Loss_USD_Bn_Today_Approx')}bn today<br>
                <b>Validation:</b> {row.get('Loss_Source_Status', 'Needs validation')} • {row.get('Comparable_Use', 'Context only')}<br>
                <b>Footprint note:</b> {row.get('Footprint_Note')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_source_engine_panel(event, df):
    st.markdown("<div class='section-title'>Source priority engine</div>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="info-box">
            <b>Selected event source logic</b><br>
            Market region: <b>{event.get('Market_Region', 'Global')}</b><br>
            Source priority: <b>{event.get('Source_Priority_Score', '')}/100</b><br>
            Insurance relevance: <b>{event.get('Insurance_Relevance', '')}</b> ({event.get('Insurance_Relevance_Score', '')}/100)<br>
            {event.get('Preferred_Source_Note', '')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    matrix = pd.DataFrame([
        {"Region / peril": "Japan earthquake / tsunami", "Preferred official source": "JMA", "Cross-checks": "USGS, EMSC, GDACS", "Insurance layer": "PERILS / PCS / vendor notes if loss-relevant"},
        {"Region / peril": "Global earthquake", "Preferred official source": "USGS", "Cross-checks": "EMSC, GDACS, local agency", "Insurance layer": "PCS, PERILS, KCC, Moody's RMS, Verisk, CoreLogic/Cotality"},
        {"Region / peril": "Atlantic / E. Pacific cyclone", "Preferred official source": "NOAA/NHC", "Cross-checks": "GDACS, NWS, local agencies", "Insurance layer": "PCS, Moody's RMS, Verisk, KCC, Aon, Gallagher Re"},
        {"Region / peril": "Europe windstorm / flood", "Preferred official source": "National agencies / Copernicus", "Cross-checks": "GDACS, EFAS/GloFAS", "Insurance layer": "PERILS, Aon, Gallagher Re, Swiss Re, Munich Re"},
        {"Region / peril": "Australia flood / cyclone / wildfire", "Preferred official source": "BOM / state agencies", "Cross-checks": "GDACS, Copernicus, NASA FIRMS", "Insurance layer": "ICA, PCS, vendor / broker notes"},
    ])
    st.dataframe(matrix, use_container_width=True, hide_index=True)

    st.markdown("**Current live source coverage**")
    source_summary = (
        df.groupby(["Source_Name", "Market_Region", "Peril"], dropna=False)
          .size()
          .reset_index(name="Events")
          .sort_values(["Source_Name", "Events"], ascending=[True, False])
    )
    st.dataframe(source_summary.head(40), use_container_width=True, hide_index=True)

    st.markdown(
        "<div class='warn-box'><b>Telegram policy:</b> This wider app coverage does not mean noisier Telegram. Telegram should remain strict: important fresh new event, meaningful update, or escalation only.</div>",
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
Market region: {event.get('Market_Region')}
Source priority: {event.get('Source_Priority_Score')}/100
Insurance relevance: {event.get('Insurance_Relevance')} ({event.get('Insurance_Relevance_Score')}/100)
Loss watch: {event.get('Loss_Watch')} ({event.get('Loss_Watch_Score')}/100)
Loss stage: {event.get('Loss_Watch_Stage')}
PCS / PERILS relevance: {event.get('PCS_PERILS_Relevance')}
Market vendor note: {event.get('Market_Vendor_Note')}

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



def vendor_search_links(event):
    """Curated insurance-market sources and searches for the selected event."""
    name = str(event.get("Event_Name", "")).strip()
    country = str(event.get("Country", "")).strip()
    peril = str(event.get("Peril", "")).strip()
    q = quote_plus(f'"{name}" {country} {peril} insured loss catastrophe model')
    q_short = quote_plus(f'{country} {peril} insured loss catastrophe')

    links = [
        {"Layer": "Industry loss", "Source": "PCS / Verisk", "Use": "US/global catastrophe loss designation and insured-loss commentary where available", "Link": "https://www.verisk.com/insurance/brands/pcs/"},
        {"Layer": "Industry loss", "Source": "PERILS", "Use": "European and selected international industry-loss reporting", "Link": "https://www.perils.org/"},
        {"Layer": "Model vendor", "Source": "Moody's RMS", "Use": "Model/vendor event response and loss commentary", "Link": "https://www.rms.com/events"},
        {"Layer": "Model vendor", "Source": "KCC", "Use": "Catastrophe response and model commentary", "Link": "https://www.karenclarkandco.com/"},
        {"Layer": "Model vendor", "Source": "CoreLogic / Cotality", "Use": "Property, hazard and loss intelligence where published", "Link": "https://www.corelogic.com/intelligence/"},
        {"Layer": "Broker / reinsurer", "Source": "Aon", "Use": "Event response and market commentary", "Link": "https://www.aon.com/reinsurance/insights"},
        {"Layer": "Broker / reinsurer", "Source": "Gallagher Re", "Use": "Event summaries and market loss perspective", "Link": "https://www.ajg.com/gallagherre/news-and-insights/"},
        {"Layer": "Broker / reinsurer", "Source": "Swiss Re", "Use": "Sigma / risk commentary and reinsurer perspective", "Link": "https://www.swissre.com/institute/"},
        {"Layer": "Broker / reinsurer", "Source": "Munich Re", "Use": "NatCatSERVICE / market commentary", "Link": "https://www.munichre.com/en/risks/natural-disasters.html"},
        {"Layer": "Search", "Source": "Google News", "Use": "Search this selected event for insured-loss and model commentary", "Link": f"https://news.google.com/search?q={q}"},
        {"Layer": "Search", "Source": "Web search", "Use": "Broad public web search for insurance-market references", "Link": f"https://www.google.com/search?q={q_short}"},
    ]
    for item in links:
        item["Event-specific status"] = "Not checked in-app" if item["Layer"] != "Search" else "Use to confirm event-specific update"
        item["Decision use"] = "Do not treat as event-specific unless the opened source mentions this event."
    return links


def insurance_trigger_list(event):
    peril = event.get("Peril", "Other")
    region = event.get("Market_Region", "Global")
    sev = event.get("Severity", "Unknown")
    items = []
    items.append(f"Severity / priority: {sev} / {tier_label(event.get('Notification_Tier'))}")
    items.append(f"Market region: {region}")
    items.append(f"Loss-watch stage: {event.get('Loss_Watch_Stage', 'Monitoring')}")
    items.append(f"Source reliability: {event.get('Source_Name')} priority {event.get('Source_Priority_Score')}/100")
    if peril == "Tropical Cyclone":
        items.extend([
            "Track, cone, wind field, storm surge and rainfall footprint",
            "Landfall intensity and exposure density along coastal/inland path",
            "Business interruption, flood leakage, demand surge and accumulation risk",
        ])
    elif peril in {"Earthquake", "Earthquake / Tsunami", "Tsunami"}:
        items.extend([
            "ShakeMap / local intensity footprint rather than epicentre only",
            "Urban exposure, construction vulnerability, industrial interruption and aftershock sequence",
            "Tsunami or liquefaction potential where relevant",
        ])
    elif peril == "Flood":
        items.extend([
            "Affected river basin / urban flood depth and duration",
            "Commercial/industrial exposure, motor/property mix and BI potential",
            "Government emergency declarations and reported inundation footprint",
        ])
    elif peril == "Wildfire":
        items.extend([
            "Perimeter growth, structure count, evacuation orders and containment",
            "Smoke/utility interruption and high-value residential exposure",
        ])
    elif peril == "Severe Storm":
        items.extend([
            "Hail/wind/tornado swath, property and motor exposure, and reports density",
            "Whether PCS or local market bodies classify the event as an industry loss event",
        ])
    else:
        items.append("Confirmed damage, casualties, evacuation, infrastructure disruption and market commentary")
    return items


def comparable_score(event, hist_row):
    score = 0
    if str(hist_row.get("Peril", "")).split(" /")[0] in str(event.get("Peril", "")) or str(event.get("Peril", "")).split(" /")[0] in str(hist_row.get("Peril", "")):
        score += 45
    if str(hist_row.get("Country", "")).lower() in str(event.get("Country", "")).lower() or str(event.get("Country", "")).lower() in str(hist_row.get("Country", "")).lower():
        score += 35
    if market_region(hist_row.get("Country"), hist_row.get("Region")) == event.get("Market_Region"):
        score += 20
    return score


def historical_comparables(event, n=6):
    hist = load_history().copy()
    if hist.empty:
        return hist
    hist["Comparable_Score"] = hist.apply(lambda r: comparable_score(event, r), axis=1)
    hist = hist[hist["Comparable_Score"] > 0].copy()
    if hist.empty:
        return load_history().sort_values("Insured_Loss_USD_Bn_Today_Approx", ascending=False).head(n)
    return hist.sort_values(["Comparable_Score", "Insured_Loss_USD_Bn_Today_Approx"], ascending=[False, False]).head(n)


def render_insurance_intelligence(event, df):
    st.markdown("<div class='section-title'>Insurance intelligence</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='info-box'><b>Purpose:</b> turn hazard monitoring into insurance-market situational awareness. This is an early-warning view, not a modelled loss estimate.</div>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Loss watch", event.get("Loss_Watch", "Monitor"), f"{event.get('Loss_Watch_Score', 0)}/100")
    with c2:
        st.metric("Insurance relevance", event.get("Insurance_Relevance", "Low"), f"{event.get('Insurance_Relevance_Score', 0)}/100")

    st.markdown(
        f"""
        <div class="summary-box">
            <b>Market read-through</b><br>
            <b>Stage:</b> {event.get('Loss_Watch_Stage', 'Monitoring')}<br>
            <b>PCS / PERILS relevance:</b> {event.get('PCS_PERILS_Relevance', '')}<br>
            <b>Vendor/model note:</b> {event.get('Market_Vendor_Note', '')}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("**Why the insurance score is what it is**")
    st.dataframe(insurance_score_breakdown(event), use_container_width=True, hide_index=True)

    st.markdown("**Why this could matter for insured loss**")
    for item in insurance_trigger_list(event):
        st.markdown(f"- {item}")

    st.markdown("**Vendor / market watch links**")
    links = pd.DataFrame(vendor_search_links(event))
    st.dataframe(links, use_container_width=True, hide_index=True, column_config={"Link": st.column_config.LinkColumn("Open")})

    st.markdown("**Historical comparables**")
    comps = historical_comparables(event)
    show_cols = [
        "Event_Name", "Year", "Country", "Peril",
        "Economic_Loss_USD_Bn_Today_Approx", "Insured_Loss_USD_Bn_Today_Approx", "Footprint_Note"
    ]
    st.dataframe(comps[show_cols], use_container_width=True, hide_index=True)

    st.markdown("**Analyst checklist**")
    checklist = [
        "Confirm official footprint / impact area, not just point location.",
        "Check whether exposed territories have high insurance penetration or major commercial/industrial exposure.",
        "Look for casualty/damage/infrastructure reports from official agencies and verified news.",
        "Check PCS/PERILS/local insurance body relevance for this geography/peril.",
        "Monitor Moody's RMS, Verisk, KCC, CoreLogic/Cotality, broker and reinsurer commentary.",
        "Update management note only when there is a material change or credible loss commentary.",
    ]
    for item in checklist:
        st.markdown(f"- {item}")

    st.markdown("**Manual loss-note capture**")
    st.caption("Temporary scratchpad only; it is not saved to a database.")
    template = pd.DataFrame([
        {"Field": "Current loss view", "Entry": event.get("Industry_Loss_Status", "Not yet reported")},
        {"Field": "Public economic loss", "Entry": event.get("Economic_Loss", "Unknown")},
        {"Field": "Public insured loss", "Entry": event.get("Insured_Loss", "Unknown")},
        {"Field": "Vendor / market note", "Entry": ""},
        {"Field": "Analyst conclusion", "Entry": ""},
    ])
    st.data_editor(template, use_container_width=True, hide_index=True, key=f"loss_capture_{event.get('Event_ID', 'event')}")

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
# v7.3 Event Response Workbench helpers
# ============================================================

def slugify_event_text(text, n=42):
    txt = clean(text).lower()
    txt = re.sub(r"\b(m\??\d+(?:\.\d+)?)\b", "", txt)
    txt = re.sub(r"\b(earthquake|hurricane|tropical storm|tropical cyclone|typhoon|cyclone|flood|wildfire|fire|volcano|tsunami|near|km|of|the|updated|alert)\b", " ", txt)
    txt = re.sub(r"[^a-z0-9]+", "-", txt).strip("-")
    return txt[:n] or "event"


def event_datetime_for_matching(row):
    d = pd.to_datetime(row.get("Start_Date_UTC"), errors="coerce", utc=True)
    if pd.isna(d):
        d = pd.to_datetime(row.get("Start_Date"), errors="coerce", utc=True)
    if pd.isna(d):
        d = pd.to_datetime(row.get("Latest_Update_Date"), errors="coerce", utc=True)
    return None if pd.isna(d) else d


def event_magnitude_for_matching(row):
    return parse_mag_from_text(str(row.get("Event_Name", "")) + " " + str(row.get("Physical_Intensity", "")))


def peril_family(peril):
    p = str(peril or "Other")
    if p in {"Earthquake", "Earthquake / Tsunami", "Tsunami"}:
        return "Earthquake"
    if "Cyclone" in p or "Hurricane" in p or "Typhoon" in p:
        return "Tropical Cyclone"
    if "Flood" in p:
        return "Flood"
    if "Wildfire" in p or "Fire" in p:
        return "Wildfire"
    if "Storm" in p or "Hail" in p or "Tornado" in p:
        return "Severe Storm"
    return p


def event_signature(row):
    """Stable-ish master-event ID seed. The clustering engine below assigns events first; this creates a readable ID for the group representative."""
    peril = peril_family(row.get("Peril", "Other"))
    start = event_datetime_for_matching(row)
    day = start.strftime("%Y%m%d") if start is not None else "NODATE"
    country = slugify_event_text(row.get("Country", "global"), 18)
    location = slugify_event_text(row.get("Location_Label") or row.get("Event_Name"), 34)
    lat = safe_float(row.get("Latitude"))
    lon = safe_float(row.get("Longitude"))

    if peril == "Tropical Cyclone":
        name = slugify_event_text(row.get("NHC_Storm_Name") or row.get("Event_Name") or row.get("Location_Label"), 32)
        basin = slugify_event_text(row.get("NHC_Basin") or row.get("Country") or "basin", 20)
        return f"TC-{day}-{basin}-{name}".upper()

    if peril == "Earthquake":
        mag = event_magnitude_for_matching(row)
        mag_bucket = f"M{round(mag * 2) / 2:.1f}" if mag is not None else "MUNK"
        if lat is not None and lon is not None:
            # Coarser buckets reduce source-split risk; clustering still validates distance/time/magnitude.
            return f"EQ-{day}-{round(lat * 2) / 2:.1f}-{round(lon * 2) / 2:.1f}-{mag_bucket}".upper()
        return f"EQ-{day}-{country}-{location}-{mag_bucket}".upper()

    if lat is not None and lon is not None:
        return f"{peril[:3].upper()}-{day}-{round(lat,1):.1f}-{round(lon,1):.1f}-{country}".upper()
    return f"{peril[:3].upper()}-{day}-{country}-{location}".upper()


def event_match_score(row, rep):
    """Transparent matching score for merging source observations into one master event."""
    reasons = []
    score = 0
    family = peril_family(row.get("Peril"))
    rep_family = peril_family(rep.get("Peril"))
    if family != rep_family:
        return 0, ["Different peril family"]
    score += 25
    reasons.append("Same peril family")

    t1 = event_datetime_for_matching(row)
    t2 = event_datetime_for_matching(rep)
    hours = None
    if t1 is not None and t2 is not None:
        hours = abs((t1 - t2).total_seconds()) / 3600
        if family == "Earthquake":
            if hours <= 2:
                score += 30; reasons.append("Event time within ±2h")
            elif hours <= 6:
                score += 12; reasons.append("Event time within ±6h")
            else:
                return 0, ["Earthquake event time too far apart"]
        elif family == "Tropical Cyclone":
            if hours <= 24 * 14:
                score += 15; reasons.append("Same cyclone time window")
        else:
            if hours <= 24 * 7:
                score += 15; reasons.append("Same weekly event window")

    rname = slugify_event_text(row.get("Event_Name", ""), 32)
    pname = slugify_event_text(rep.get("Event_Name", ""), 32)
    rloc = slugify_event_text(row.get("Location_Label", ""), 28)
    ploc = slugify_event_text(rep.get("Location_Label", ""), 28)
    rcountry = slugify_event_text(row.get("Country", ""), 18)
    pcountry = slugify_event_text(rep.get("Country", ""), 18)

    if rcountry and pcountry and rcountry == pcountry:
        score += 10; reasons.append("Same country/basin")
    if rloc and ploc and (rloc in ploc or ploc in rloc or rloc[:12] == ploc[:12]):
        score += 15; reasons.append("Similar location text")

    lat1, lon1 = safe_float(row.get("Latitude")), safe_float(row.get("Longitude"))
    lat2, lon2 = safe_float(rep.get("Latitude")), safe_float(rep.get("Longitude"))
    if lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None:
        try:
            dist = haversine_km(lat1, lon1, lat2, lon2)
            if family == "Earthquake":
                if dist <= 250:
                    score += 35; reasons.append(f"Epicentres within {dist:.0f} km")
                elif dist <= 500:
                    score += 16; reasons.append(f"Epicentres within {dist:.0f} km")
                else:
                    return 0, [f"Epicentres too far apart ({dist:.0f} km)"]
            elif family == "Tropical Cyclone":
                if dist <= 800:
                    score += 10; reasons.append(f"Cyclone positions within {dist:.0f} km")
            else:
                if dist <= 300:
                    score += 18; reasons.append(f"Locations within {dist:.0f} km")
        except Exception:
            pass

    if family == "Earthquake":
        m1, m2 = event_magnitude_for_matching(row), event_magnitude_for_matching(rep)
        if m1 is not None and m2 is not None:
            mdiff = abs(m1 - m2)
            if mdiff <= 0.8:
                score += 20; reasons.append(f"Magnitude difference {mdiff:.1f}")
            elif mdiff <= 1.2:
                score += 8; reasons.append(f"Magnitude difference {mdiff:.1f}")
            else:
                score -= 15; reasons.append(f"Magnitude disagreement {mdiff:.1f}")
    elif family == "Tropical Cyclone":
        name1 = slugify_event_text(row.get("NHC_Storm_Name") or row.get("Event_Name"), 30)
        name2 = slugify_event_text(rep.get("NHC_Storm_Name") or rep.get("Event_Name"), 30)
        if name1 and name2 and (name1 == name2 or name1 in name2 or name2 in name1):
            score += 45; reasons.append("Same storm name")

    return max(0, score), reasons


def match_threshold(row):
    fam = peril_family(row.get("Peril"))
    if fam == "Earthquake":
        return 75
    if fam == "Tropical Cyclone":
        return 70
    return 65


def add_master_event_fields(df):
    if df.empty:
        return df
    out = df.copy()
    out["_match_time"] = out.apply(event_datetime_for_matching, axis=1)
    out["_sort_time"] = pd.to_datetime(out["_match_time"], errors="coerce", utc=True)

    groups = []
    assigned = {}
    match_score_map = {}
    match_reason_map = {}

    order = out.sort_values(["_sort_time", "Source_Priority_Score"], ascending=[True, False], na_position="last").index.tolist()
    for idx in order:
        row = out.loc[idx]
        best = None
        best_score = 0
        best_reasons = []
        for group in groups:
            score, reasons = event_match_score(row, group["rep"])
            if score > best_score:
                best = group
                best_score = score
                best_reasons = reasons
        if best is not None and best_score >= match_threshold(row):
            assigned[idx] = best["mid"]
            match_score_map[idx] = best_score
            match_reason_map[idx] = "; ".join(best_reasons[:4])
            # Promote the representative when a better official/priority source arrives.
            try:
                if safe_float(row.get("Source_Priority_Score")) > safe_float(best["rep"].get("Source_Priority_Score")):
                    best["rep"] = row
            except Exception:
                pass
        else:
            mid = event_signature(row)
            # Avoid accidental duplicate IDs when two unrelated events land in the same coarse bucket.
            existing = {g["mid"] for g in groups}
            if mid in existing:
                mid = f"{mid}-{len(groups)+1}"
            groups.append({"mid": mid, "rep": row})
            assigned[idx] = mid
            match_score_map[idx] = 100
            match_reason_map[idx] = "Seed observation for master event"

    out["Master_Event_ID"] = pd.Series(assigned)
    out["Master_Match_Score"] = pd.Series(match_score_map)
    out["Master_Match_Note"] = pd.Series(match_reason_map)
    out["Master_Match_Confidence"] = out["Master_Match_Score"].apply(lambda x: "High" if safe_float(x) and safe_float(x) >= 90 else "Medium" if safe_float(x) and safe_float(x) >= 75 else "Review")

    out["Observation_Rank"] = (
        pd.to_numeric(out.get("Source_Priority_Score"), errors="coerce").fillna(0) * 100
        + pd.to_numeric(out.get("Severity_Rank"), errors="coerce").fillna(0) * 20
        + pd.to_numeric(out.get("Insurance_Relevance_Score"), errors="coerce").fillna(0)
        + pd.to_numeric(out.get("Alert_Rank"), errors="coerce").fillna(0) * 5
    )

    source_names = out.groupby("Master_Event_ID")["Source_Name"].transform(lambda s: " / ".join(pd.Series(s).dropna().astype(str).drop_duplicates().tolist()))
    source_counts = out.groupby("Master_Event_ID")["Source_Name"].transform(lambda s: len(pd.Series(s).dropna().astype(str).drop_duplicates()))
    obs_counts = out.groupby("Master_Event_ID")["Source_Name"].transform("count")
    out["Source_Names"] = source_names
    out["Master_Source_Count"] = source_counts
    out["Master_Observation_Count"] = obs_counts

    primary_idx = out.sort_values(["Master_Event_ID", "Observation_Rank", "Start_Date_UTC"], ascending=[True, False, False]).groupby("Master_Event_ID").head(1).index
    out["Is_Master_Primary"] = out.index.isin(primary_idx)
    primary_source_map = out.loc[primary_idx].set_index("Master_Event_ID")["Source_Name"].to_dict()
    out["Primary_Source_Name"] = out["Master_Event_ID"].map(primary_source_map).fillna(out["Source_Name"])
    out["Cross_Check_Sources"] = out.apply(lambda r: " / ".join([s for s in str(r.get("Source_Names", "")).split(" / ") if s and s != r.get("Primary_Source_Name")]) or "None yet", axis=1)
    out["Event_Integrity_Flag"] = out.apply(lambda r: "Cross-checked" if int(r.get("Master_Source_Count", 1) or 1) >= 2 else "Single-source / monitor", axis=1)
    return out.drop(columns=["_match_time", "_sort_time"], errors="ignore")


def master_event_view(df):
    df = add_master_event_fields(df)
    if df.empty:
        return df
    primary = df.sort_values(
        ["Observation_Rank", "Start_Date_UTC", "Latest_Update_Date"],
        ascending=[False, False, False]
    ).drop_duplicates("Master_Event_ID", keep="first").copy()
    primary = primary.sort_values(
        ["Queue", "Alert_Rank", "Tier_Rank", "Severity_Rank", "Insurance_Relevance_Score", "Source_Priority_Score", "Start_Date_UTC"],
        ascending=[True, False, False, False, False, False, False]
    )
    return primary


def material_snapshot(row):
    return {
        "Severity": str(row.get("Severity", "")),
        "Priority": str(row.get("Notification_Tier", "")),
        "Alert type": str(row.get("Alert_Type", "")),
        "Intensity": short(row.get("Physical_Intensity", ""), 180),
        "Insurance relevance": str(row.get("Insurance_Relevance", "")),
        "Loss watch": str(row.get("Loss_Watch", "")),
        "Sources": str(row.get("Source_Names", row.get("Source_Name", ""))),
        "Footprint mode": str(row.get("Map_Mode", "")),
        "Source count": str(row.get("Master_Source_Count", "")),
    }


def compute_session_change_text(master_df):
    old = st.session_state.get("catwatch_v74_material_state", {})
    new = {}
    changes = {}
    history = st.session_state.get("catwatch_v74_change_history", {})
    current_run = now_text()

    for _, row in master_df.iterrows():
        mid = row.get("Master_Event_ID", row.get("Event_ID"))
        snap = material_snapshot(row)
        new[mid] = snap
        prev = old.get(mid)
        if prev is None:
            msg = "First seen in this app session. Not treated as a material update until a tracked field changes."
            changes[mid] = msg
            history.setdefault(mid, []).append({"time": current_run, "change": "First seen in app session", "snapshot": snap})
        else:
            diffs = []
            for key, val in snap.items():
                old_val = prev.get(key)
                if str(old_val) != str(val):
                    diffs.append(f"{key}: {old_val or 'Unknown'} → {val or 'Unknown'}")
            if diffs:
                msg = "; ".join(diffs[:6])
                changes[mid] = msg
                history.setdefault(mid, []).append({"time": current_run, "change": msg, "snapshot": snap})
            else:
                changes[mid] = "No material field changed since the previous app refresh."
    st.session_state["catwatch_v74_material_state"] = new
    st.session_state["catwatch_v74_change_history"] = history
    return changes


def source_health_table(df):
    expected = [
        {"Source": "USGS", "Expected role": "Global earthquake hazard / products"},
        {"Source": "JMA", "Expected role": "Japan earthquake / tsunami context"},
        {"Source": "EMSC", "Expected role": "Earthquake cross-check"},
        {"Source": "GDACS", "Expected role": "Humanitarian alert colour / multi-peril"},
        {"Source": "NOAA/NHC", "Expected role": "Atlantic/East/Central Pacific cyclone products"},
    ]
    rows = []
    now = pd.Timestamp.now(tz="UTC")
    for item in expected:
        src = item["Source"]
        sub = df[df["Source_Name"] == src].copy() if not df.empty and "Source_Name" in df.columns else pd.DataFrame()
        if sub.empty:
            status = "No active/recent events loaded"
            latest = ""
            age = ""
            count = 0
            perils = ""
        else:
            count = len(sub)
            perils = ", ".join(sub["Peril"].dropna().astype(str).drop_duplicates().head(5).tolist())
            times = pd.to_datetime(sub["Latest_Update_Date"], errors="coerce", utc=True)
            latest_ts = times.max()
            latest = latest_ts.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(latest_ts) else "Unknown"
            age = f"{((now - latest_ts).total_seconds()/3600):.1f}h" if pd.notna(latest_ts) else "Unknown"
            status = "OK" if count > 0 else "No data"
        rows.append({
            "Source": src,
            "Status": status,
            "Events loaded": count,
            "Latest source update": latest,
            "Age": age,
            "Perils seen": perils,
            "Expected role": item["Expected role"],
            "Action": "Review if unexpectedly empty or stale; absence can also mean no active/recent events."
        })
    return pd.DataFrame(rows)


def insurance_score_breakdown(event):
    severity_points = severity_rank(event.get("Severity", "Unknown")) * 12
    priority_points = {"P1": 28, "P2": 18, "P3": 8, "P4": 2}.get(str(event.get("Notification_Tier", "P4")), 0)
    alert_points = {"New Event": 8, "Event Update": 6, "Escalation": 14, "Active Watch": 6, "Monitoring": 1}.get(str(event.get("Alert_Type", "Monitoring")), 0)
    market_points = 8 if event.get("Market_Region") in {"Japan", "United States / NHC basin", "Europe", "Australia / New Zealand"} else 0
    peril_points = 5 if event.get("Peril") in {"Tropical Cyclone", "Earthquake", "Flood", "Wildfire", "Severe Storm"} else 0
    rows = [
        {"Component": "Hazard severity", "Points": severity_points, "Reason": event.get("Severity", "Unknown")},
        {"Component": "Priority tier", "Points": priority_points, "Reason": tier_label(event.get("Notification_Tier", "P4"))},
        {"Component": "Alert status", "Points": alert_points, "Reason": event.get("Alert_Type", "Monitoring")},
        {"Component": "Insurance market region", "Points": market_points, "Reason": event.get("Market_Region", "Global")},
        {"Component": "Modelled peril relevance", "Points": peril_points, "Reason": event.get("Peril", "Other")},
    ]
    raw = sum(r["Points"] for r in rows)
    rows.append({"Component": "Cap / final score", "Points": min(100, raw), "Reason": f"Raw {raw}; displayed score capped at 100"})
    return pd.DataFrame(rows)


def render_event_integrity_panel(event, all_df):
    st.markdown("**Event integrity / de-duplication**")
    obs = event_observation_table(event, all_df)
    source_count = int(event.get("Master_Source_Count", 1) or 1)
    flag_class = "ok-box" if source_count >= 2 else "warn-box"
    st.markdown(
        f"""
        <div class='{flag_class}'>
            <b>Integrity flag:</b> {event.get('Event_Integrity_Flag', 'Single-source / monitor')}<br>
            <b>Master match confidence:</b> {event.get('Master_Match_Confidence', 'Review')}<br>
            <b>Match evidence:</b> {event.get('Master_Match_Note', 'Seed observation')}<br>
            <b>Observation count:</b> {event.get('Master_Observation_Count', 1)} observation(s) from {source_count} source(s)
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not obs.empty and len(obs) > 1:
        st.caption("Use this table to spot source disagreement before acting on the event.")
        cols = [c for c in ["Source_Name", "Severity", "Notification_Tier", "Physical_Intensity", "Latest_Update_Date", "Source_Link"] if c in obs.columns]
        st.dataframe(obs[cols], use_container_width=True, hide_index=True, column_config={"Source_Link": st.column_config.LinkColumn("Open")})

def field_confidence_table(event):
    src = event.get("Source_Name", "Source")
    peril = event.get("Peril", "Other")
    rows = [
        {"Field": "Hazard identity", "Current value": event.get("Event_Name"), "Primary source": src, "Confidence": "High", "Type": "Official / feed observation"},
        {"Field": "Physical intensity", "Current value": event.get("Physical_Intensity"), "Primary source": src, "Confidence": "High" if src in {"USGS", "JMA", "NOAA/NHC"} else "Medium", "Type": "Observed / advisory"},
        {"Field": "Location", "Current value": event.get("Location_Label"), "Primary source": src, "Confidence": "High" if event.get("Latitude") not in [None, ""] else "Medium", "Type": "Point location"},
        {"Field": "Footprint", "Current value": event.get("Map_Mode"), "Primary source": src, "Confidence": "Medium" if peril in {"Earthquake", "Tropical Cyclone"} else "Low", "Type": "Point / product status"},
        {"Field": "Human impact", "Current value": event.get("Human_Impact"), "Primary source": "Official / verified news required", "Confidence": "Low until confirmed", "Type": "Reported"},
        {"Field": "Insured loss", "Current value": event.get("Insured_Loss"), "Primary source": "PCS / PERILS / vendor / market", "Confidence": "Low until market source appears", "Type": "Market estimate"},
    ]
    return pd.DataFrame(rows)


def event_observation_table(event, df):
    mid = event.get("Master_Event_ID")
    if not mid:
        return pd.DataFrame()
    obs = df[df["Master_Event_ID"] == mid].copy()
    cols = ["Source_Name", "Event_Name", "Alert_Type", "Severity", "Notification_Tier", "Physical_Intensity", "Start_Date", "Latest_Update_Date", "Source_Priority_Score", "Source_Link"]
    cols = [c for c in cols if c in obs.columns]
    return obs[cols].sort_values(["Source_Priority_Score", "Latest_Update_Date"], ascending=[False, False])


def event_timeline(event, df):
    obs = event_observation_table(event, df)
    rows = []
    if obs.empty:
        return pd.DataFrame(rows)
    for _, r in obs.iterrows():
        if r.get("Start_Date"):
            rows.append({"Time": r.get("Start_Date"), "Milestone": "Event detected / reported", "Source": r.get("Source_Name"), "Detail": short(r.get("Physical_Intensity"), 160)})
        if r.get("Latest_Update_Date") and r.get("Latest_Update_Date") != r.get("Start_Date"):
            rows.append({"Time": r.get("Latest_Update_Date"), "Milestone": "Latest source update", "Source": r.get("Source_Name"), "Detail": f"{r.get('Severity')} / {r.get('Notification_Tier')}"})
    rows.append({"Time": now_text(), "Milestone": "CatWatch workbench assessment", "Source": "CatWatch", "Detail": f"{event.get('Loss_Watch')} • {event.get('Insurance_Relevance')} insurance relevance"})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["SortTime"] = pd.to_datetime(out["Time"], errors="coerce", utc=True)
    return out.sort_values("SortTime", ascending=False).drop(columns=["SortTime"])


def footprint_status_table(event):
    peril = event.get("Peril", "Other")
    rows = []
    has_point = event.get("Latitude") not in [None, ""] and event.get("Longitude") not in [None, ""]
    rows.append({"Layer": "Event point", "Status": "Available" if has_point else "Not available", "Type": "Point", "Confidence": "High for location; not a footprint", "Action": "Use only as anchor, not exposure footprint"})
    if peril in {"Earthquake", "Earthquake / Tsunami", "Tsunami"}:
        rows.append({"Layer": "ShakeMap / intensity footprint", "Status": "Check USGS detail / JMA intensity", "Type": "Modelled/observed intensity", "Confidence": "Medium to high when product available", "Action": "Use MMI/intensity zones for exposure screening"})
        rows.append({"Layer": "PAGER / impact estimate", "Status": "Check official earthquake products", "Type": "Impact model", "Confidence": "Medium", "Action": "Use for humanitarian/economic impact triage only"})
    elif peril == "Tropical Cyclone":
        rows.append({"Layer": "Track / cone", "Status": "Available for NHC basin when product listed", "Type": "Forecast", "Confidence": "High for advisory; uncertainty remains", "Action": "Do not treat cone as damage footprint"})
        rows.append({"Layer": "Wind / surge / rainfall", "Status": "Product-dependent", "Type": "Hazard footprint", "Confidence": "Medium", "Action": "Use for portfolio accumulation and loss-watch"})
    elif peril == "Flood":
        rows.append({"Layer": "Flood extent", "Status": "Not yet integrated", "Type": "Observed/satellite/modelled", "Confidence": "Depends on Copernicus/GloFAS/agency", "Action": "Add GloFAS/EFAS/Copernicus EMS in next source patch"})
    elif peril == "Wildfire":
        rows.append({"Layer": "Active fire / perimeter", "Status": "Not yet integrated", "Type": "Satellite/perimeter", "Confidence": "Depends on FIRMS/local agency", "Action": "Add NASA FIRMS and local fire perimeters"})
    else:
        rows.append({"Layer": "Official footprint", "Status": "Peril/source dependent", "Type": "TBD", "Confidence": "Unknown", "Action": "Use official hazard product where available"})
    return pd.DataFrame(rows)


def model_trigger_table(event):
    peril = event.get("Peril", "Other")
    score = int(event.get("Loss_Watch_Score", 0) or 0)
    tier = event.get("Notification_Tier", "P4")
    sev = event.get("Severity", "Unknown")
    rows = [
        {"Question": "Should R&D/modeling review this event?", "Status": "Yes" if tier in {"P1", "P2"} or score >= 50 else "Monitor", "Reason": f"{tier_label(tier)} • loss watch {score}/100"},
        {"Question": "Is an official footprint available?", "Status": "Check", "Reason": event.get("Map_Mode", "Unknown")},
        {"Question": "Are hazard parameters stable?", "Status": "Watch", "Reason": event.get("What_Changed", "No persisted change history yet")},
        {"Question": "Is portfolio exposure likely material?", "Status": "Unknown until exposure overlay", "Reason": "Use the Portfolio placeholder/upload section below"},
        {"Question": "Is insurance-market commentary available?", "Status": "Not yet" if event.get("Industry_Loss_Status") == "Not yet reported" else "Check", "Reason": event.get("PCS_PERILS_Relevance", "")},
    ]
    if peril == "Tropical Cyclone":
        rows.append({"Question": "Relevant model view", "Status": "Cyclone", "Reason": "Track, landfall intensity, wind radii, surge, rainfall and inland flood"})
    elif peril in {"Earthquake", "Earthquake / Tsunami", "Tsunami"}:
        rows.append({"Question": "Relevant model view", "Status": "Earthquake", "Reason": "MMI/Shaking intensity, depth, vulnerability, liquefaction/tsunami, aftershocks"})
    else:
        rows.append({"Question": "Relevant model view", "Status": peril, "Reason": "Use peril-specific footprint and exposure checks"})
    return pd.DataFrame(rows)


def haversine_km(lat1, lon1, lat2, lon2):
    import math
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))


def find_column(cols, candidates):
    low_map = {str(c).strip().lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in low_map:
            return low_map[cand.lower()]
    for c in cols:
        cl = str(c).strip().lower()
        if any(cand.lower() in cl for cand in candidates):
            return c
    return None


def render_portfolio_placeholder(event):
    st.markdown("<div class='section-title'>Portfolio impact placeholder</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='warn-box'><b>Preliminary exposure screen — not modelled loss:</b> upload a CSV with latitude, longitude and TIV for triage only. Circular buffers are not official footprints; use ShakeMap, cyclone wind/surge/rain, flood extent, wildfire perimeter or other official layers when available.</div>",
        unsafe_allow_html=True,
    )
    default_buffer = 50 if event.get("Peril") in {"Earthquake", "Earthquake / Tsunami", "Tsunami"} else 150 if event.get("Peril") == "Tropical Cyclone" else 75
    buffer_km = st.number_input("Screening buffer radius (km)", min_value=5, max_value=1000, value=default_buffer, step=5)
    up = st.file_uploader("Upload exposure CSV", type=["csv"], key=f"portfolio_{event.get('Master_Event_ID', event.get('Event_ID'))}")
    if up is None:
        st.caption("Expected columns: latitude/lat, longitude/lon, TIV/total_insured_value/sum_insured. Optional: portfolio, cedant, line_of_business, country.")
        return
    try:
        exp = pd.read_csv(up)
        lat_col = find_column(exp.columns, ["latitude", "lat"])
        lon_col = find_column(exp.columns, ["longitude", "lon", "lng"])
        tiv_col = find_column(exp.columns, ["tiv", "total_insured_value", "sum_insured", "insured_value"])
        if not lat_col or not lon_col or not tiv_col:
            st.error("Could not find latitude, longitude and TIV columns. Please rename columns or upload a different file.")
            st.dataframe(exp.head(5), use_container_width=True)
            return
        elat, elon = safe_float(event.get("Latitude")), safe_float(event.get("Longitude"))
        if elat is None or elon is None:
            st.warning("Selected event has no coordinates, so distance-based portfolio screening is not available.")
            return
        exp = exp.copy()
        exp["_lat"] = pd.to_numeric(exp[lat_col], errors="coerce")
        exp["_lon"] = pd.to_numeric(exp[lon_col], errors="coerce")
        exp["_tiv"] = pd.to_numeric(exp[tiv_col], errors="coerce").fillna(0)
        exp = exp.dropna(subset=["_lat", "_lon"])
        exp["Distance_km"] = exp.apply(lambda r: haversine_km(elat, elon, r["_lat"], r["_lon"]), axis=1)
        affected = exp[exp["Distance_km"] <= buffer_km].copy()
        c1, c2, c3 = st.columns(3)
        c1.metric("Locations in buffer", len(affected))
        c2.metric("TIV in buffer", f"{affected['_tiv'].sum():,.0f}")
        c3.metric("Total file TIV", f"{exp['_tiv'].sum():,.0f}")
        if affected.empty:
            st.info("No uploaded exposure points fall inside the selected buffer.")
        else:
            show_cols = [c for c in exp.columns if not str(c).startswith("_")]
            st.dataframe(affected.sort_values("Distance_km").head(50)[show_cols + ["Distance_km"]], use_container_width=True, hide_index=True)
            st.markdown("**Preliminary aggregation**")
            exp["Distance_Band"] = pd.cut(exp["Distance_km"], bins=[0, 25, 50, 100, 250, 500, 10000], labels=["0–25 km", "25–50 km", "50–100 km", "100–250 km", "250–500 km", ">500 km"], include_lowest=True)
            agg_rows = []
            for label, col_candidates in {
                "Distance band": ["Distance_Band"],
                "Country": ["country", "Country"],
                "Portfolio": ["portfolio", "Portfolio", "book", "Book"],
                "Line of business": ["line_of_business", "lob", "LOB", "Line_of_Business"],
                "Cedant / client": ["cedant", "client", "Cedant", "Client"],
            }.items():
                col = find_column(exp.columns, col_candidates)
                if col:
                    sub = exp.groupby(col, dropna=False)["_tiv"].sum().reset_index().sort_values("_tiv", ascending=False).head(12)
                    sub.columns = ["Group", "TIV"]
                    sub.insert(0, "Aggregation", label)
                    agg_rows.append(sub)
            if agg_rows:
                st.dataframe(pd.concat(agg_rows, ignore_index=True), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Could not read portfolio file: {exc}")


def render_master_event_header(event):
    st.markdown(event_badges(event), unsafe_allow_html=True)
    st.markdown(f"### {event.get('Event_Name')}")
    st.markdown(
        f"""
        <div class="summary-box">
            <b>Master event ID:</b> {event.get('Master_Event_ID', event.get('Event_ID'))}<br>
            <b>Primary source:</b> {event.get('Primary_Source_Name', event.get('Source_Name'))} • <b>Cross-checks:</b> {event.get('Cross_Check_Sources', 'None yet')}<br>
            <b>Source observations:</b> {event.get('Master_Observation_Count', 1)} observation(s) from {event.get('Master_Source_Count', 1)} source(s)<br>
            <b>Integrity:</b> {event.get('Event_Integrity_Flag', 'Single-source / monitor')} • match confidence {event.get('Master_Match_Confidence', 'Review')}<br>
            <b>What changed:</b> {event.get('What_Changed', 'No material change summary available')}
        </div>
        """,
        unsafe_allow_html=True,
    )


def management_text_v73(event, all_df):
    obs = event_observation_table(event, all_df)
    source_line = ", ".join(obs["Source_Name"].dropna().astype(str).drop_duplicates().tolist()) if not obs.empty else event.get("Source_Name")
    return f"""CATWATCH EVENT RESPONSE BRIEF – {event.get('Event_Name')}

Status: {event.get('Alert_Type')} | {tier_label(event.get('Notification_Tier'))} | {event.get('Severity')}
Master event ID: {event.get('Master_Event_ID')}
Primary source: {event.get('Primary_Source_Name', event.get('Source_Name'))}
Cross-check sources: {event.get('Cross_Check_Sources', 'None yet')}
All source observations: {source_line}
Latest material signal: {event.get('What_Changed')}
Event integrity: {event.get('Event_Integrity_Flag')} | match confidence {event.get('Master_Match_Confidence')} | {event.get('Master_Match_Note')}

What happened:
{event.get('Management_Summary')}

Hazard fingerprint:
Peril: {event.get('Peril')}
Region / country: {event.get('Country')} / {event.get('Market_Region')}
Location: {event.get('Location_Label')}
Physical intensity: {event.get('Physical_Intensity')}
Footprint status: {event.get('Map_Mode')} — {event.get('Impact_Region')}

Insurance / portfolio relevance:
Insurance relevance: {event.get('Insurance_Relevance')} ({event.get('Insurance_Relevance_Score')}/100)
Loss watch: {event.get('Loss_Watch')} ({event.get('Loss_Watch_Score')}/100)
Loss stage: {event.get('Loss_Watch_Stage')}
PCS / PERILS relevance: {event.get('PCS_PERILS_Relevance')}
Market/vendor note: {event.get('Market_Vendor_Note')}

Current confidence:
{event.get('Confidence_Level')}

Expected developments:
{event.get('What_To_Expect')}

Analyst next action:
{event.get('Analyst_Action')}

Next expected update:
{event.get('Next_Update')}

Open questions:
- Is an official footprint available and suitable for exposure overlay?
- Is there credible damage / casualty / infrastructure reporting?
- Does the affected area intersect material portfolio exposure?
- Has PCS / PERILS / vendor / broker commentary appeared?
- Does management need a new update now, or only after a material change?

Source link:
{event.get('Source_Link')}
""".strip()


# ============================================================
# App
# ============================================================

# ============================================================
# App
# ============================================================
def main():
    inject_css()
    refresh_count = st_autorefresh(interval=5 * 60 * 1000, key="catwatch_v74_refresh")

    st.markdown(
        """
        <div class="hero">
            <div class="hero-title">🌍 CatWatch v7.4</div>
            <div class="hero-sub">
                Event Response Workbench for Cat Modeling, R&D, GIS, Portfolio Analytics and Management:
                event integrity, stronger source de-duplication, material-change tracking, source health,
                explainable insurance scoring, safer portfolio screening and management-ready decision workflow.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    raw_df = load_live_events()
    if raw_df.empty:
        st.error("No live event data loaded. Please try again.")
        return

    all_df = add_master_event_fields(raw_df)
    master_df = master_event_view(raw_df)
    changes = compute_session_change_text(master_df)
    master_df["What_Changed"] = master_df["Master_Event_ID"].map(changes).fillna("No material change summary available.")
    all_df = all_df.merge(master_df[["Master_Event_ID", "What_Changed"]], on="Master_Event_ID", how="left")

    cyclone_status_box(master_df)
    filt = apply_filters(master_df)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Master events", len(filt))
    with c2:
        st.metric("Executive", int((filt["Queue"] == "Executive Alerts").sum()) if not filt.empty else 0)
    with c3:
        st.metric("Recent global", int((filt["Queue"] == "Recent Global Events").sum()) if not filt.empty else 0)
    with c4:
        st.metric("Loss watch", int((filt["Loss_Watch_Score"] >= 60).sum()) if not filt.empty else 0)

    col_a, col_b = st.columns([1, 2.2])
    with col_a:
        if st.button("Refresh now"):
            st.cache_data.clear()
            st.rerun()
    with col_b:
        st.markdown(f"<div class='small-note'>Auto-refresh every 5 minutes while open • 30-day live window • one master card per event • Telegram remains separate and stricter • refresh count: {refresh_count}</div>", unsafe_allow_html=True)

    if filt.empty:
        st.info("No events match the current filters.")
        return

    selected_label = st.selectbox(
        "Selected master event",
        filt.apply(lambda r: f"{r['Event_Name']} — {r.get('Primary_Source_Name', r.get('Source_Name'))} — {r.get('Severity')}", axis=1).tolist(),
        index=0,
    )
    selected_idx = filt.index[filt.apply(lambda r: f"{r['Event_Name']} — {r.get('Primary_Source_Name', r.get('Source_Name'))} — {r.get('Severity')}", axis=1) == selected_label][0]
    event = filt.loc[selected_idx]
    all_obs = all_df[all_df["Master_Event_ID"] == event.get("Master_Event_ID")].copy()

    tabs = st.tabs(["Monitor", "Event Response", "Footprint / GIS", "Insurance & Portfolio", "Reports"])

    with tabs[0]:
        st.markdown("<div class='section-title'>Monitor</div>", unsafe_allow_html=True)
        st.markdown("<div class='info-box'><b>Purpose:</b> one master card per physical event. Source observations are merged where possible, so the same earthquake/cyclone should not flood the screen as separate cards.</div>", unsafe_allow_html=True)
        with st.expander("Source health & coverage", expanded=False):
            st.dataframe(source_health_table(all_df), use_container_width=True, hide_index=True)

        st.markdown("**Executive Alerts**")
        exec_df = filt[filt["Queue"] == "Executive Alerts"].copy()
        if exec_df.empty:
            st.info("No executive-priority master events match the current filters.")
        else:
            for _, row in exec_df.head(15).iterrows():
                render_event_card(row)

        st.markdown("**Recent Global Events**")
        recent_df = filt[filt["Queue"] == "Recent Global Events"].sort_values(["Start_Date_UTC", "Source_Priority_Score"], ascending=[False, False]).copy()
        if recent_df.empty:
            st.info("No lower-priority recent global events match the current filters.")
        else:
            for _, row in recent_df.head(25).iterrows():
                render_event_card(row)

    with tabs[1]:
        st.markdown("<div class='section-title'>Event Response Workbench</div>", unsafe_allow_html=True)
        render_master_event_header(event)
        render_event_integrity_panel(event, all_df)

        st.markdown("**Management summary**")
        st.markdown(f"<div class='summary-box'>{event.get('Management_Summary')}</div>", unsafe_allow_html=True)

        st.markdown("**Event fingerprint**")
        fingerprint = pd.DataFrame([
            {"Field": "Peril", "Value": event.get("Peril")},
            {"Field": "Region / market", "Value": f"{event.get('Country')} / {event.get('Market_Region')}"},
            {"Field": "Location", "Value": event.get("Location_Label")},
            {"Field": "Physical intensity", "Value": event.get("Physical_Intensity")},
            {"Field": "Footprint mode", "Value": event.get("Map_Mode")},
            {"Field": "Loss stage", "Value": event.get("Loss_Watch_Stage")},
            {"Field": "Next expected update", "Value": event.get("Next_Update")},
        ])
        st.dataframe(fingerprint, use_container_width=True, hide_index=True)

        st.markdown("**What changed / latest material signal**")
        st.markdown(f"<div class='info-box'>{event.get('What_Changed')}</div>", unsafe_allow_html=True)

        st.markdown("**Source observations merged into this master event**")
        obs = event_observation_table(event, all_df)
        if obs.empty:
            st.info("Only one source observation is available for this event.")
        else:
            st.dataframe(obs, use_container_width=True, hide_index=True, column_config={"Source_Link": st.column_config.LinkColumn("Open")})

        st.markdown("**Event timeline**")
        tl = event_timeline(event, all_df)
        if tl.empty:
            st.info("No timeline could be built yet.")
        else:
            st.dataframe(tl, use_container_width=True, hide_index=True)

        st.markdown("**Source confidence by field**")
        st.dataframe(field_confidence_table(event), use_container_width=True, hide_index=True)

        st.markdown("**Model trigger checklist**")
        st.dataframe(model_trigger_table(event), use_container_width=True, hide_index=True)

        st.markdown("**Verified news / confirmation layer**")
        news = fetch_news(event.get("Event_Name"), event.get("Country"), event.get("Peril"))
        if news.empty:
            st.info("No verified news items were found for the selected event yet.")
        else:
            for _, row in news.head(5).iterrows():
                render_news_card(row)

    with tabs[2]:
        st.markdown("<div class='section-title'>Footprint / GIS</div>", unsafe_allow_html=True)
        st.markdown("<div class='warn-box'><b>GIS principle:</b> do not use point location as the exposure footprint. Use official footprint, intensity, track, cone, wind, flood, fire, or satellite layers where available.</div>", unsafe_allow_html=True)
        render_master_event_header(event)

        st.markdown("**Footprint status engine**")
        st.dataframe(footprint_status_table(event), use_container_width=True, hide_index=True)

        if event.get("Peril") == "Earthquake":
            shake = fetch_usgs_shakemap_status(event.get("Detail_Link", ""))
            klass = "ok-box" if shake["available"] else "warn-box"
            st.markdown(f"<div class='{klass}'><b>USGS ShakeMap:</b> {shake['note']}</div>", unsafe_allow_html=True)
            if shake.get("url"):
                st.markdown(f"[Open ShakeMap / detail product]({shake['url']})")

        st.markdown("**Map view**")
        if event.get("Peril") == "Tropical Cyclone" or event.get("Source_Name") == "NOAA/NHC":
            nhc_footprint_map(event)
        else:
            live_points_map(pd.DataFrame([event]))

        st.markdown("**GIS source roadmap**")
        gis_sources = pd.DataFrame([
            {"Peril": "Earthquake", "Preferred GIS layer": "USGS ShakeMap / local intensity", "Status": "Partly linked", "Use": "MMI/intensity exposure screen"},
            {"Peril": "Tropical Cyclone", "Preferred GIS layer": "NHC track/cone/wind products; WMO RSMC/JTWC roadmap", "Status": "NHC partly mapped", "Use": "Track, cone, wind/surge/rain watch"},
            {"Peril": "Flood", "Preferred GIS layer": "GloFAS / EFAS / Copernicus EMS", "Status": "Roadmap", "Use": "Basin/extent overlay"},
            {"Peril": "Wildfire", "Preferred GIS layer": "NASA FIRMS / local fire perimeter", "Status": "Roadmap", "Use": "Active-fire/perimeter overlay"},
        ])
        st.dataframe(gis_sources, use_container_width=True, hide_index=True)

    with tabs[3]:
        st.markdown("<div class='section-title'>Insurance & Portfolio</div>", unsafe_allow_html=True)
        render_insurance_intelligence(event, all_df)
        render_portfolio_placeholder(event)

        st.markdown("**Historical comparable events**")
        comps = historical_comparables(event)
        for _, row in comps.head(6).iterrows():
            render_history_card(row)

    with tabs[4]:
        st.markdown("<div class='section-title'>Reports</div>", unsafe_allow_html=True)
        st.markdown("<div class='info-box'><b>Purpose:</b> one management-ready event response brief built from the selected master event.</div>", unsafe_allow_html=True)
        mgmt = management_text_v73(event, all_df)
        st.text_area("Event response brief", mgmt, height=520)
        st.download_button(
            "Download event response brief",
            mgmt.encode("utf-8"),
            "catwatch_event_response_brief.txt",
            "text/plain",
        )

        st.markdown("**Source health & app material-state snapshot**")
        st.dataframe(source_health_table(all_df), use_container_width=True, hide_index=True)
        state_payload = json.dumps(st.session_state.get("catwatch_v74_material_state", {}), indent=2, ensure_ascii=False)
        st.download_button("Download current app material snapshot", state_payload.encode("utf-8"), "catwatch_app_material_snapshot.json", "application/json")

        st.markdown("**Source priority reference**")
        render_source_engine_panel(event, all_df)

        st.markdown("**Full historical library**")
        with st.expander("Open historical event library", expanded=False):
            hist = load_history()
            history_map(hist)
            st.dataframe(hist, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
