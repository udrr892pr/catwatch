import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
from dateutil import parser as dateparser
from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="CatWatch Operations Centre",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"


# -----------------------------
# Visual design
# -----------------------------
def inject_css():
    st.markdown(
        """
        <style>
        :root {
            --navy: #0f172a;
            --blue: #2563eb;
            --sky: #0284c7;
            --muted: #64748b;
            --line: #e2e8f0;
            --bg: #f8fafc;
            --card: #ffffff;
        }
        .main {
            background: linear-gradient(180deg, #f8fafc 0%, #ffffff 25%);
        }
        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 2.5rem;
            max-width: 1500px;
        }
        .hero {
            background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #0284c7 100%);
            color: white;
            padding: 1.25rem 1.35rem;
            border-radius: 22px;
            margin-bottom: 1rem;
            box-shadow: 0 14px 32px rgba(15, 23, 42, 0.20);
        }
        .hero h1 {
            margin: 0 0 0.25rem 0;
            font-size: 2rem;
            line-height: 1.1;
        }
        .hero p {
            margin: 0;
            opacity: 0.92;
            line-height: 1.45;
            max-width: 1100px;
        }
        .ops-card {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 18px;
            padding: 1rem 1.05rem;
            box-shadow: 0 8px 24px rgba(15,23,42,0.06);
            margin-bottom: 0.85rem;
        }
        .event-card {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 18px;
            padding: 0.95rem;
            box-shadow: 0 8px 22px rgba(15,23,42,0.06);
            margin-bottom: 0.8rem;
        }
        .event-title {
            font-size: 1.05rem;
            font-weight: 800;
            color: #0f172a;
            margin-top: 0.25rem;
            margin-bottom: 0.3rem;
            line-height: 1.35;
        }
        .event-meta {
            color: #475569;
            font-size: 0.92rem;
            line-height: 1.5;
        }
        .badge {
            display: inline-block;
            border-radius: 999px;
            padding: 0.22rem 0.62rem;
            font-size: 0.76rem;
            font-weight: 800;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
            letter-spacing: 0.01em;
        }
        .sev-Critical {background:#7f1d1d;color:white;}
        .sev-Red {background:#dc2626;color:white;}
        .sev-Orange {background:#f97316;color:white;}
        .sev-Amber {background:#f59e0b;color:#111827;}
        .sev-Yellow {background:#fde68a;color:#111827;}
        .sev-Green {background:#22c55e;color:#052e16;}
        .sev-Unknown {background:#cbd5e1;color:#0f172a;}
        .tier-P1 {background:#991b1b;color:white;}
        .tier-P2 {background:#ea580c;color:white;}
        .tier-P3 {background:#2563eb;color:white;}
        .tier-P4 {background:#64748b;color:white;}
        .pill {
            display: inline-block;
            border-radius: 999px;
            padding: 0.22rem 0.6rem;
            font-size: 0.76rem;
            font-weight: 700;
            background: #eff6ff;
            color: #1d4ed8;
            border: 1px solid #bfdbfe;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
        }
        .summary-box {
            background: #f8fafc;
            border-left: 5px solid #2563eb;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            color: #0f172a;
            line-height: 1.55;
            margin-bottom: 0.9rem;
        }
        .action-box {
            background: #fff7ed;
            border-left: 5px solid #f97316;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            color: #0f172a;
            line-height: 1.55;
            margin-bottom: 0.9rem;
        }
        .quiet {
            color: #64748b;
            font-size: 0.9rem;
        }
        .source-chip {
            background: #f1f5f9;
            color: #334155;
            border-radius: 999px;
            padding: 0.2rem 0.55rem;
            font-size: 0.76rem;
            font-weight: 700;
            display: inline-block;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
        }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 18px;
            padding: 0.65rem;
            box-shadow: 0 5px 18px rgba(15,23,42,0.05);
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            background: #eff6ff;
            padding: 0.45rem 0.85rem;
            height: auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# Helpers
# -----------------------------
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_text() -> str:
    return utc_now().strftime("%Y-%m-%d %H:%M UTC")


def make_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.md5(text.encode('utf-8')).hexdigest()[:10].upper()}"


def parse_date(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = dateparser.parse(str(value))
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()


def short_text(text: str, max_len: int = 210) -> str:
    text = str(text or "")
    if len(text) <= max_len:
        return text
    return text[:max_len - 1].rstrip() + "…"


def severity_from_earthquake_mag(mag):
    try:
        mag = float(mag)
    except Exception:
        return "Unknown"
    if mag >= 7.5:
        return "Critical"
    if mag >= 6.5:
        return "Red"
    if mag >= 5.5:
        return "Amber"
    return "Green"


def severity_rank(severity: str) -> int:
    return {
        "Critical": 5,
        "Red": 4,
        "Orange": 3,
        "Amber": 3,
        "Yellow": 2,
        "Green": 1,
        "Unknown": 0,
    }.get(str(severity), 0)


def severity_color(severity: str):
    return {
        "Critical": [127, 29, 29, 220],
        "Red": [220, 38, 38, 210],
        "Orange": [249, 115, 22, 205],
        "Amber": [245, 158, 11, 205],
        "Yellow": [253, 230, 138, 205],
        "Green": [34, 197, 94, 190],
        "Unknown": [100, 116, 139, 180],
    }.get(str(severity), [100, 116, 139, 180])


def infer_gdacs_severity(title: str, summary: str) -> str:
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


def infer_peril(text: str) -> str:
    t = str(text).lower()
    peril_map = [
        ("earthquake", "Earthquake"),
        ("tropical cyclone", "Tropical Cyclone"),
        ("cyclone", "Tropical Cyclone"),
        ("hurricane", "Tropical Cyclone"),
        ("typhoon", "Tropical Cyclone"),
        ("flood", "Flood"),
        ("wildfire", "Wildfire"),
        ("fire", "Wildfire"),
        ("volcano", "Volcano"),
        ("tsunami", "Tsunami"),
        ("drought", "Drought"),
        ("landslide", "Landslide"),
        ("storm", "Severe Storm"),
    ]
    for keyword, peril in peril_map:
        if keyword in t:
            return peril
    return "Other"


def peril_emoji(peril: str) -> str:
    return {
        "Earthquake": "🌎",
        "Tropical Cyclone": "🌀",
        "Flood": "🌊",
        "Wildfire": "🔥",
        "Volcano": "🌋",
        "Tsunami": "🌊",
        "Drought": "☀️",
        "Landslide": "⛰️",
        "Severe Storm": "⛈️",
        "Other": "📍",
    }.get(str(peril), "📍")


def extract_country(location_text: str) -> str:
    text = str(location_text or "").strip()
    if not text:
        return "Unknown"
    if "," in text:
        return text.split(",")[-1].strip()
    lower = text.lower()
    for marker in [" in ", " near ", " of "]:
        if marker in lower:
            return text[lower.rfind(marker) + len(marker):].strip().title()
    return text


def notification_tier(severity: str, peril: str, intensity: str = "") -> str:
    text = f"{severity} {peril} {intensity}".lower()
    if severity in {"Critical", "Red"}:
        return "P1"
    if severity in {"Orange", "Amber"}:
        return "P2"
    if "magnitude 6." in text or "magnitude 7" in text or "magnitude 8" in text:
        return "P1"
    if severity in {"Yellow", "Green"}:
        return "P3"
    return "P4"


def tier_label(tier: str) -> str:
    return {
        "P1": "P1 Executive Alert",
        "P2": "P2 Analyst Watch",
        "P3": "P3 Monitor",
        "P4": "P4 Information",
    }.get(tier, "P4 Information")


def analyst_action(row: pd.Series) -> str:
    tier = row.get("Notification_Tier", "P4")
    peril = row.get("Peril", "Other")
    if tier == "P1":
        return "Prepare short management update, verify exposure/loss relevance, monitor source updates every 15–30 minutes."
    if tier == "P2":
        return "Keep on analyst watchlist, check for escalation, affected population, landfall/impact reports, and public loss commentary."
    if peril == "Tropical Cyclone":
        return "Monitor advisory cycle and track changes. Add NHC/official forecast track connector next for path view."
    return "Monitor for new humanitarian, official, or loss-related updates."


def next_update_hint(row: pd.Series) -> str:
    tier = row.get("Notification_Tier", "P4")
    peril = row.get("Peril", "Other")
    if peril == "Tropical Cyclone":
        return "At next official advisory cycle; more frequently near landfall."
    if row.get("Source_Name") == "USGS":
        return "Within 15–30 minutes for major earthquake; then as impact reports emerge."
    if tier == "P1":
        return "15–30 minutes until stable."
    if tier == "P2":
        return "1–3 hours or when source changes."
    return "Daily or on escalation."


# -----------------------------
# Data fetch
# -----------------------------
@st.cache_data(ttl=300)
def fetch_usgs_events() -> list[dict]:
    events = []
    try:
        r = requests.get(USGS_URL, timeout=20)
        r.raise_for_status()
        data = r.json()

        for feature in data.get("features", []):
            props = feature.get("properties", {}) or {}
            geom = feature.get("geometry", {}) or {}
            coords = geom.get("coordinates", [None, None, None])
            mag = props.get("mag")
            place = props.get("place") or "Unknown location"
            dt = parse_date(props.get("time"))
            url = props.get("url") or ""
            severity = severity_from_earthquake_mag(mag)
            intensity = f"Magnitude {mag}; depth {coords[2] if len(coords) > 2 else 'Unknown'} km"
            tier = notification_tier(severity, "Earthquake", intensity)

            events.append({
                "Event_ID": f"USGS-{feature.get('id', make_id('EQ', place))}",
                "Event_Name": f"M{mag} earthquake - {place}",
                "Peril": "Earthquake",
                "Event_Status": "Active",
                "Severity": severity,
                "Notification_Tier": tier,
                "Country": extract_country(place),
                "Location_Label": place,
                "Latitude": coords[1] if len(coords) > 1 else None,
                "Longitude": coords[0] if len(coords) > 0 else None,
                "Start_Date": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                "Latest_Update_Date": utc_now_text(),
                "Source_Name": "USGS",
                "Source_Link": url,
                "Physical_Intensity": intensity,
                "Human_Impact": "Unknown from USGS feed",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "High for hazard parameters; Low for impact and loss",
                "Why_It_Matters": (
                    "Earthquake hazard parameters are confirmed quickly, but casualties, infrastructure damage, and insured loss potential need follow-up reporting."
                ),
                "Board_Summary": (
                    f"USGS reports a magnitude {mag} earthquake near {place}. "
                    "Initial hazard information is available; loss and human impact remain uncertain pending official and media updates."
                ),
                "Track_Info": "Point location available. Earthquakes do not have a forecast track.",
                "Comparable_Events": "To be assessed when impact/loss information is available.",
            })
    except Exception as e:
        st.warning(f"USGS fetch failed: {e}")
    return events


@st.cache_data(ttl=300)
def fetch_gdacs_events() -> list[dict]:
    events = []
    try:
        feed = feedparser.parse(GDACS_RSS_URL)
        for entry in feed.entries[:50]:
            title = getattr(entry, "title", "GDACS event")
            summary = clean_html(getattr(entry, "summary", ""))
            link = getattr(entry, "link", "")
            dt = parse_date(getattr(entry, "published", None) or getattr(entry, "updated", None))
            severity = infer_gdacs_severity(title, summary)
            peril = infer_peril(title + " " + summary)
            tier = notification_tier(severity, peril, summary)

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

            if peril == "Tropical Cyclone":
                track = "Track connector planned: official NHC/JTWC or basin-specific track feed. Current version shows event point/alert only."
            else:
                track = "Map point available when coordinates are provided by source. No path data connected yet for this peril."

            events.append({
                "Event_ID": make_id("GDACS", title + link),
                "Event_Name": title,
                "Peril": peril,
                "Event_Status": "Active",
                "Severity": severity,
                "Notification_Tier": tier,
                "Country": extract_country(title),
                "Location_Label": title,
                "Latitude": lat,
                "Longitude": lon,
                "Start_Date": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                "Latest_Update_Date": utc_now_text(),
                "Source_Name": "GDACS",
                "Source_Link": link,
                "Physical_Intensity": short_text(summary, 250) or "See GDACS source for alert details.",
                "Human_Impact": "Check GDACS and follow-up official/humanitarian reports",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "Medium to High for alert status; Low for impact and loss",
                "Why_It_Matters": (
                    "GDACS alerts are designed to flag potentially significant sudden-onset disasters. Analyst review is needed to interpret exposure, casualty, and loss relevance."
                ),
                "Board_Summary": (
                    f"GDACS alert: {title}. Monitor for affected population, escalation/de-escalation, landfall/impact reports, and public economic or insured loss estimates."
                ),
                "Track_Info": track,
                "Comparable_Events": "To be assessed when intensity and loss data are available.",
            })
    except Exception as e:
        st.warning(f"GDACS fetch failed: {e}")
    return events


@st.cache_data(ttl=300)
def load_events() -> pd.DataFrame:
    rows = []
    rows.extend(fetch_usgs_events())
    rows.extend(fetch_gdacs_events())

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Severity_Rank"] = df["Severity"].apply(severity_rank)
    df["Tier_Rank"] = df["Notification_Tier"].map({"P1": 4, "P2": 3, "P3": 2, "P4": 1}).fillna(0)
    df["Start_Date_Sort"] = pd.to_datetime(df["Start_Date"], errors="coerce")
    df["Map_Color"] = df["Severity"].apply(severity_color)
    df["Analyst_Action"] = df.apply(analyst_action, axis=1)
    df["Next_Update"] = df.apply(next_update_hint, axis=1)
    df = df.sort_values(["Tier_Rank", "Severity_Rank", "Start_Date_Sort"], ascending=[False, False, False])
    return df


# -----------------------------
# Rendering
# -----------------------------
def badges(row: pd.Series) -> str:
    sev = row.get("Severity", "Unknown")
    tier = row.get("Notification_Tier", "P4")
    peril = row.get("Peril", "Other")
    return (
        f"<span class='badge tier-{tier}'>{tier_label(tier)}</span>"
        f"<span class='badge sev-{sev}'>{sev}</span>"
        f"<span class='pill'>{peril_emoji(peril)} {peril}</span>"
        f"<span class='source-chip'>{row.get('Source_Name', 'Source')}</span>"
    )


def event_card(row: pd.Series):
    st.markdown(
        f"""
        <div class="event-card">
            {badges(row)}
            <div class="event-title">{row.get('Event_Name', 'Unnamed event')}</div>
            <div class="event-meta">
                <b>Country / area:</b> {row.get('Country', 'Unknown')}<br>
                <b>Location:</b> {row.get('Location_Label', 'Unknown')}<br>
                <b>Why it matters:</b> {short_text(row.get('Why_It_Matters', ''), 170)}<br>
                <b>Next update:</b> {row.get('Next_Update', 'Unknown')}<br>
                <b>Loss watch:</b> {row.get('Industry_Loss_Status', 'Unknown')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def make_map(df: pd.DataFrame):
    map_df = df.dropna(subset=["Latitude", "Longitude"]).copy()
    if map_df.empty:
        st.info("No coordinates available for the selected events.")
        return

    map_df["lat"] = pd.to_numeric(map_df["Latitude"], errors="coerce")
    map_df["lon"] = pd.to_numeric(map_df["Longitude"], errors="coerce")
    map_df = map_df.dropna(subset=["lat", "lon"])

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position="[lon, lat]",
        get_radius=70000,
        get_fill_color="Map_Color",
        pickable=True,
        auto_highlight=True,
    )
    view_state = pdk.ViewState(
        latitude=map_df["lat"].mean(),
        longitude=map_df["lon"].mean(),
        zoom=1,
        pitch=0,
    )
    tooltip = {
        "html": "<b>{Event_Name}</b><br/>Severity: {Severity}<br/>Tier: {Notification_Tier}<br/>Country: {Country}<br/>Source: {Source_Name}",
        "style": {"backgroundColor": "#0f172a", "color": "white"},
    }
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip), use_container_width=True)



def public_search_url(event_name: str, source_name: str) -> str:
    query = f'"{event_name}" {source_name} insured loss catastrophe model estimate event response'
    return "https://www.google.com/search?q=" + quote_plus(query)


def vendor_intelligence_table(row: pd.Series) -> pd.DataFrame:
    event_name = row.get("Event_Name", "")
    peril = row.get("Peril", "")
    country = row.get("Country", "")

    vendors = [
        {
            "Source": "Moody's RMS",
            "Category": "Model vendor",
            "What to check": "Event response, modeled insured loss, hazard footprint, market commentary",
            "Access type": "Public + licensed",
            "Priority": "High",
        },
        {
            "Source": "Verisk Extreme Event Solutions / PCS",
            "Category": "Model vendor / industry loss",
            "What to check": "Modeled insured loss estimate, PCS catastrophe information, event commentary",
            "Access type": "Public + licensed",
            "Priority": "High",
        },
        {
            "Source": "KCC",
            "Category": "Model vendor",
            "What to check": "Flash estimate, modeled insured loss, event response commentary",
            "Access type": "Often public summary",
            "Priority": "High",
        },
        {
            "Source": "CoreLogic / Cotality",
            "Category": "Property analytics",
            "What to check": "Property impact, exposure, hazard insights, disaster response articles",
            "Access type": "Public + platform",
            "Priority": "Medium",
        },
        {
            "Source": "PERILS",
            "Category": "Industry loss authority",
            "What to check": "Industry loss index, initial loss estimate, subsequent loss updates",
            "Access type": "Mostly licensed",
            "Priority": "High",
        },
        {
            "Source": "Aon",
            "Category": "Broker / market report",
            "What to check": "Catastrophe recap, market loss commentary, insured/economic loss ranges",
            "Access type": "Public reports",
            "Priority": "Medium",
        },
        {
            "Source": "Gallagher Re",
            "Category": "Broker / market report",
            "What to check": "Natural catastrophe report, event commentary, insured/economic loss ranges",
            "Access type": "Public reports",
            "Priority": "Medium",
        },
        {
            "Source": "Swiss Re",
            "Category": "Reinsurer / sigma",
            "What to check": "Insured/economic loss commentary and later event trend reports",
            "Access type": "Public summaries",
            "Priority": "Medium",
        },
        {
            "Source": "Munich Re",
            "Category": "Reinsurer / NatCat",
            "What to check": "NatCat commentary, economic/insured loss estimates, historical comparison",
            "Access type": "Public summaries",
            "Priority": "Medium",
        },
        {
            "Source": "Official insurance body",
            "Category": "Official claims / market body",
            "What to check": f"Claims count, declared catastrophe status, local insurance market loss updates for {country}",
            "Access type": "Public if available",
            "Priority": "High",
        },
    ]

    rows = []
    for item in vendors:
        rows.append({
            "Source": item["Source"],
            "Category": item["Category"],
            "Priority": item["Priority"],
            "Current app status": "Manual/public check required",
            "What to check": item["What to check"],
            "Access type": item["Access type"],
            "Search link": public_search_url(event_name, item["Source"]),
        })

    return pd.DataFrame(rows)


def vendor_model_status_summary(row: pd.Series) -> str:
    tier = row.get("Notification_Tier", "P4")
    severity = row.get("Severity", "Unknown")
    peril = row.get("Peril", "Unknown")
    event_name = row.get("Event_Name", "selected event")

    if tier == "P1":
        cadence = "Check vendor/model sources immediately and then every 1–3 hours until a public estimate or clear no-update status is established."
    elif tier == "P2":
        cadence = "Check vendor/model sources at least twice daily while the event remains active or escalating."
    else:
        cadence = "Check vendor/model sources daily or only if the event escalates."

    return (
        f"For {event_name}, current hazard severity is {severity} and peril is {peril}. "
        f"CatWatch has not yet captured a verified public vendor model estimate inside the app. {cadence} "
        "If a public vendor estimate is found, record estimate range, geography, peril component, source date, access status, and confidence."
    )


def vendor_loss_board_text(row: pd.Series) -> str:
    return f"""
Vendor model / industry loss view:
No verified public vendor model or industry loss estimate has been captured in CatWatch yet.

Current action:
Check Moody's RMS, Verisk / PCS, KCC, CoreLogic / Cotality, PERILS, Aon, Gallagher Re, Swiss Re, Munich Re, and relevant official insurance bodies for public event response or insured-loss commentary.

Management caveat:
At this stage, hazard information is available from live alert sources, but vendor modeled loss and market loss estimates may be preliminary, delayed, paywalled, or unavailable. Any loss number should be labelled by source, estimate date, confidence level, and whether it is public or licensed.
""".strip()

def management_summary(row: pd.Series) -> str:
    return f"""
MANAGEMENT UPDATE – {row.get('Event_Name', 'Selected event')}

Priority: {tier_label(row.get('Notification_Tier', 'P4'))}
Status: {row.get('Event_Status', 'Unknown')}
Peril: {row.get('Peril', 'Unknown')}
Severity: {row.get('Severity', 'Unknown')}
Country / area: {row.get('Country', 'Unknown')}
Location: {row.get('Location_Label', 'Unknown')}
Latest update: {row.get('Latest_Update_Date', 'Unknown')}
Source: {row.get('Source_Name', 'Unknown')}

Executive view:
{row.get('Board_Summary', 'No summary available')}

Why it matters:
{row.get('Why_It_Matters', 'Unknown')}

Current hazard / physical intensity:
{row.get('Physical_Intensity', 'Unknown')}

Human impact:
{row.get('Human_Impact', 'Unknown')}

Economic / insured / industry loss:
Economic loss: {row.get('Economic_Loss', 'Unknown')}
Insured loss: {row.get('Insured_Loss', 'Unknown')}
Industry loss status: {row.get('Industry_Loss_Status', 'Unknown')}

Analyst action:
{row.get('Analyst_Action', 'Continue monitoring.')}

Next expected update:
{row.get('Next_Update', 'Unknown')}

Source link:
{row.get('Source_Link', '')}
""".strip()


# -----------------------------
# App
# -----------------------------
def main():
    inject_css()

    # Refresh while open. GitHub/Telegram push notifications are handled separately.
    refresh_count = st_autorefresh(interval=5 * 60 * 1000, key="catwatch_ops_refresh")

    st.markdown(
        f"""
        <div class="hero">
            <h1>🌍 CatWatch Operations Centre</h1>
            <p>Live catastrophe monitoring for analyst triage, GIS/R&D follow-up, industry loss watch, and management reporting. Auto-refresh is on every 5 minutes while open.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    df = load_events()
    if df.empty:
        st.error("No live event data loaded. Check source availability.")
        return

    with st.sidebar:
        st.header("Event controls")
        if st.button("Refresh now"):
            st.cache_data.clear()
            st.rerun()

        st.caption(f"Auto-refresh count this session: {refresh_count}")
        selected_tiers = st.multiselect(
            "Notification priority",
            ["P1", "P2", "P3", "P4"],
            default=["P1", "P2", "P3", "P4"],
            help="P1 = management alert; P2 = analyst watch; P3/P4 = monitor/information."
        )
        peril_options = ["All"] + sorted(df["Peril"].dropna().unique().tolist())
        severity_options = ["All"] + sorted(df["Severity"].dropna().unique().tolist(), key=severity_rank, reverse=True)
        country_options = ["All"] + sorted(df["Country"].dropna().astype(str).unique().tolist())

        selected_peril = st.selectbox("Peril", peril_options)
        selected_severity = st.selectbox("Severity", severity_options)
        selected_country = st.selectbox("Country / area", country_options)
        search = st.text_input("Search event or place")

    filtered = df.copy()
    if selected_tiers:
        filtered = filtered[filtered["Notification_Tier"].isin(selected_tiers)]
    if selected_peril != "All":
        filtered = filtered[filtered["Peril"] == selected_peril]
    if selected_severity != "All":
        filtered = filtered[filtered["Severity"] == selected_severity]
    if selected_country != "All":
        filtered = filtered[filtered["Country"] == selected_country]
    if search.strip():
        needle = search.lower().strip()
        filtered = filtered[filtered.apply(lambda row: needle in " ".join(row.astype(str)).lower(), axis=1)]

    p1_count = int((filtered["Notification_Tier"] == "P1").sum())
    p2_count = int((filtered["Notification_Tier"] == "P2").sum())

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Events shown", len(filtered))
    m2.metric("P1 executive alerts", p1_count)
    m3.metric("P2 analyst watch", p2_count)
    m4.metric("Countries / areas", int(filtered["Country"].nunique()) if not filtered.empty else 0)
    m5.metric("Last refresh", utc_now_text().split()[1] + " UTC")

    if not filtered.empty:
        event_names = filtered["Event_Name"].tolist()
        selected_event_name = st.selectbox("Open event detail", event_names)
        event = filtered[filtered["Event_Name"] == selected_event_name].iloc[0]
    else:
        event = None

    tab_ops, tab_detail, tab_map, tab_loss, tab_vendor, tab_board, tab_sources = st.tabs(
        ["Operations Home", "Event Detail", "Map & Path", "Loss Watch", "Vendor Model Watch", "Adhoc Management Overview", "Source Coverage"]
    )

    with tab_ops:
        left, right = st.columns([1.05, 1])
        with left:
            st.subheader("Priority notification queue")
            p1p2 = filtered[filtered["Notification_Tier"].isin(["P1", "P2"])] if not filtered.empty else pd.DataFrame()
            if p1p2.empty:
                st.success("No P1/P2 events in the current filter.")
                for _, row in filtered.head(5).iterrows():
                    event_card(row)
            else:
                for _, row in p1p2.head(8).iterrows():
                    event_card(row)

        with right:
            st.subheader("Global situation map")
            make_map(filtered)
            st.markdown(
                """
                <div class="ops-card">
                <b>How I would use this as a cat analyst:</b><br>
                1. Start with P1/P2 queue.<br>
                2. Open the event detail and map.<br>
                3. Ask GIS/R&D for footprint/path only if the event can materially affect exposure or market loss.<br>
                4. Use Management Overview only after source confidence is acceptable.
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab_detail:
        st.subheader("Event detail")
        if event is None:
            st.info("No event selected.")
        else:
            st.markdown(badges(event), unsafe_allow_html=True)
            st.markdown(f"### {event['Event_Name']}")

            a, b, c, d = st.columns(4)
            a.metric("Priority", tier_label(event["Notification_Tier"]))
            b.metric("Severity", event["Severity"])
            c.metric("Peril", event["Peril"])
            d.metric("Country / Area", event["Country"])

            left, right = st.columns([1.25, 0.9])
            with left:
                st.markdown('<div class="ops-card">', unsafe_allow_html=True)
                st.markdown("#### Executive summary")
                st.markdown(f"<div class='summary-box'>{event['Board_Summary']}</div>", unsafe_allow_html=True)

                st.markdown("#### Analyst interpretation")
                st.write(f"**Why it matters:** {event['Why_It_Matters']}")
                st.write(f"**Recommended action:** {event['Analyst_Action']}")
                st.write(f"**Next expected update:** {event['Next_Update']}")
                st.write(f"**Confidence:** {event['Confidence_Level']}")
                st.markdown("</div>", unsafe_allow_html=True)

            with right:
                st.markdown('<div class="ops-card">', unsafe_allow_html=True)
                st.markdown("#### Key facts")
                st.write(f"**Location:** {event['Location_Label']}")
                st.write(f"**Hazard intensity:** {event['Physical_Intensity']}")
                st.write(f"**Human impact:** {event['Human_Impact']}")
                st.write(f"**Economic loss:** {event['Economic_Loss']}")
                st.write(f"**Insured loss:** {event['Insured_Loss']}")
                st.write(f"**Industry loss:** {event['Industry_Loss_Status']}")
                st.write(f"**Source:** [{event['Source_Name']}]({event['Source_Link']})")
                st.markdown("</div>", unsafe_allow_html=True)

    with tab_map:
        st.subheader("Map and path view")
        if event is not None:
            st.markdown(badges(event), unsafe_allow_html=True)
            st.markdown(f"#### {event['Event_Name']}")
            st.write(f"**Path / footprint status:** {event['Track_Info']}")
            st.write(f"**GIS/R&D next step:** {event['Analyst_Action']}")
            single = pd.DataFrame([event])
            make_map(single)

            if event["Peril"] == "Tropical Cyclone":
                st.warning(
                    "Cyclone path is not fully connected yet. Next build step: connect official tropical cyclone GIS/RSS feed and draw forecast track / cone layers."
                )
            else:
                st.info(
                    "For this peril, the current map shows available event point location. Footprints such as shake maps, flood extents, wildfire perimeters, or Copernicus EMS polygons can be added as source connectors."
                )

    with tab_loss:
        st.subheader("Affected regions and industry loss watch")
        st.info(
            "Open-source feeds usually provide hazard alerts before reliable industry loss estimates. This tab separates confirmed hazard facts from uncertain loss impact."
        )
        cols = [
            "Notification_Tier", "Severity", "Peril", "Country", "Event_Name",
            "Human_Impact", "Economic_Loss", "Insured_Loss", "Industry_Loss_Status",
            "Confidence_Level", "Source_Name"
        ]
        if not filtered.empty:
            st.dataframe(filtered[cols], use_container_width=True, hide_index=True)
            st.download_button(
                "Download current loss watch table",
                filtered[cols].to_csv(index=False).encode("utf-8"),
                "catwatch_loss_watch.csv",
                "text/csv",
            )
        else:
            st.info("No events match the filters.")

    with tab_vendor:
        st.subheader("Vendor model and public industry-loss intelligence")
        if event is None:
            st.info("Select an event to check vendor/model intelligence.")
        else:
            st.markdown(badges(event), unsafe_allow_html=True)
            st.markdown(f"#### {event['Event_Name']}")
            st.markdown(
                f"<div class='summary-box'>{vendor_model_status_summary(event)}</div>",
                unsafe_allow_html=True,
            )

            st.markdown("##### Source checklist")
            vendor_df = vendor_intelligence_table(event)
            st.dataframe(
                vendor_df[["Priority", "Source", "Category", "Current app status", "What to check", "Access type"]],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("##### Quick public search links")
            st.caption("These links help analysts quickly check public vendor/event-response updates. Licensed portals are not scraped.")
            for _, src_row in vendor_df.head(10).iterrows():
                st.markdown(f"- [{src_row['Source']}]({src_row['Search link']}) — {src_row['What to check']}")

            st.markdown("##### Loss estimate capture template")
            capture_cols = [
                "Event_ID", "Source", "Estimate_Type", "Estimate_Low", "Estimate_High",
                "Currency", "Geography", "Publication_Date", "Confidence", "Access_Type", "Source_Link"
            ]
            capture_df = pd.DataFrame(columns=capture_cols)
            st.data_editor(
                capture_df,
                use_container_width=True,
                num_rows="dynamic",
                hide_index=True,
                key="vendor_capture_template",
            )
            st.caption("For now this table is a capture template only. In the next build we can save entries to a file/database.")


    with tab_board:
        st.subheader("Management overview")
        if event is not None:
            st.write("This is an ad-hoc, non-technical management summary that can be copied, edited, and shared when needed.")
            summary = management_summary(event) + "\n\n" + vendor_loss_board_text(event)
            st.text_area("Management update draft", summary, height=500)
            st.download_button(
                "Download management update",
                summary.encode("utf-8"),
                "catwatch_management_update.txt",
                "text/plain",
            )
        else:
            st.info("Select an event to generate management overview.")

    with tab_sources:
        st.subheader("Source coverage and build roadmap")
        st.markdown(
            """
            <div class="ops-card">
            <b>Connected now</b><br>
            <span class="source-chip">USGS earthquakes</span>
            <span class="source-chip">GDACS global disaster alerts</span>
            <br><br>
            <b>Next connectors for a professional catastrophe desk</b><br>
            1. Tropical cyclone forecast track and advisory feed.<br>
            2. Copernicus EMS activations and emergency mapping products.<br>
            3. NASA FIRMS active fire detections.<br>
            4. Vendor model watch: Moody's RMS, Verisk / PCS, KCC, CoreLogic / Cotality.<br>
            5. Public loss/news watch for insured and economic loss estimates.<br>
            6. Historical analogues table for event comparison.
            </div>
            """,
            unsafe_allow_html=True,
        )
        source_table = pd.DataFrame(
            [
                ["USGS", "Earthquake", "Connected", "Hazard location, magnitude, depth"],
                ["GDACS", "Multi-peril", "Connected", "Global disaster alert queue"],
                ["NOAA/NHC", "Tropical cyclone", "Next", "Forecast track, cone, advisory cycles"],
                ["Copernicus EMS", "Multi-peril mapping", "Next", "Activation maps and satellite-derived products"],
                ["NASA FIRMS", "Wildfire", "Next", "Active fire detections"],
                ["Vendor model watch", "Modeled loss", "Added as checklist", "Moody's RMS, Verisk / PCS, KCC, CoreLogic / Cotality"],
                ["Loss/news watch", "Industry loss", "Next", "Public economic / insured loss estimates"],
            ],
            columns=["Source", "Coverage", "Status", "Purpose"],
        )
        st.dataframe(source_table, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
