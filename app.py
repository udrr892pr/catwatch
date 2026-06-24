import hashlib
import re
from datetime import datetime, timezone

import feedparser
import pandas as pd
import requests
import streamlit as st
from dateutil import parser as dateparser

st.set_page_config(
    page_title="CatWatch – Live Event Monitor",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"


# ---------- Styling ----------
def inject_css():
    st.markdown(
        """
        <style>
        .main {
            background: linear-gradient(180deg, #f6f9fc 0%, #ffffff 18%);
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }
        .hero {
            background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 55%, #0ea5e9 100%);
            color: white;
            padding: 1.2rem 1.4rem;
            border-radius: 20px;
            margin-bottom: 1rem;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.18);
        }
        .hero h1 {
            margin: 0 0 0.35rem 0;
            font-size: 2rem;
        }
        .hero p {
            margin: 0;
            opacity: 0.92;
            line-height: 1.45;
        }
        .mini-note {
            font-size: 0.92rem;
            color: #475569;
            margin-top: 0.35rem;
        }
        .event-card {
            background: white;
            border-radius: 18px;
            padding: 1rem;
            margin-bottom: 0.9rem;
            border: 1px solid #e2e8f0;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.07);
        }
        .card-title {
            font-size: 1.06rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0.45rem 0;
        }
        .card-meta {
            color: #475569;
            font-size: 0.93rem;
            line-height: 1.45;
        }
        .badge {
            display: inline-block;
            border-radius: 999px;
            padding: 0.22rem 0.62rem;
            font-size: 0.78rem;
            font-weight: 700;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
        }
        .sev-Critical {background:#7f1d1d;color:#fff;}
        .sev-Red {background:#dc2626;color:#fff;}
        .sev-Orange {background:#f97316;color:#fff;}
        .sev-Amber {background:#f59e0b;color:#111827;}
        .sev-Yellow {background:#fde68a;color:#111827;}
        .sev-Green {background:#22c55e;color:#062b12;}
        .sev-Unknown {background:#cbd5e1;color:#0f172a;}
        .pill {
            display: inline-block;
            border-radius: 999px;
            padding: 0.22rem 0.6rem;
            font-size: 0.76rem;
            font-weight: 600;
            background: #eff6ff;
            color: #1d4ed8;
            border: 1px solid #bfdbfe;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
        }
        .section-card {
            background: white;
            border-radius: 18px;
            padding: 1rem 1.1rem;
            border: 1px solid #e2e8f0;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
        }
        .detail-label {
            color: #64748b;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.1rem;
        }
        .detail-value {
            color: #0f172a;
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
        }
        .summary-box {
            background: #f8fafc;
            border-left: 4px solid #2563eb;
            padding: 0.9rem 1rem;
            border-radius: 10px;
            color: #0f172a;
            line-height: 1.55;
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
        .stMetric {
            background: white;
            border: 1px solid #e2e8f0;
            padding: 0.35rem 0.6rem;
            border-radius: 16px;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------- Utility ----------
def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def make_id(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.md5(text.encode('utf-8')).hexdigest()[:10].upper()}"


def parse_date(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return dateparser.parse(str(value))
    except Exception:
        return None


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()


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
    }.get(peril, "📍")


def extract_country(location_text: str) -> str:
    text = str(location_text or "").strip()
    if not text:
        return "Unknown"
    if "," in text:
        return text.split(",")[-1].strip()
    patterns = [" in ", " near ", " of "]
    lower = text.lower()
    for p in patterns:
        if p in lower:
            return text[lower.rfind(p) + len(p):].strip().title()
    return text


def short_text(text: str, max_len: int = 180) -> str:
    text = str(text or "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


# ---------- Data fetching ----------
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
            location = place
            country = extract_country(place)

            events.append({
                "Event_ID": f"USGS-{feature.get('id', make_id('EQ', place))}",
                "Event_Name": f"M{mag} earthquake - {place}",
                "Peril": "Earthquake",
                "Event_Status": "Active",
                "Severity": severity,
                "Location_Label": location,
                "Country": country,
                "Latitude": coords[1] if len(coords) > 1 else None,
                "Longitude": coords[0] if len(coords) > 0 else None,
                "Start_Date": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                "Latest_Update_Date": utc_now_text(),
                "Source_Name": "USGS",
                "Source_Link": url,
                "Physical_Intensity": f"Magnitude {mag}; depth {coords[2] if len(coords) > 2 else 'Unknown'} km",
                "Human_Impact": "Unknown from USGS feed",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "High for hazard parameters; Low for impact and loss",
                "Board_Summary": (
                    f"USGS reports a magnitude {mag} earthquake near {place}. "
                    "Hazard information is available immediately, but casualties and economic or insured loss data usually require follow-up from humanitarian and public reporting sources."
                ),
                "Comparable_Events": "To be assessed",
                "Track_Info": "Point location available. Event path not applicable for earthquakes.",
                "Notes": "Automated USGS significant earthquake feed."
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
            country = extract_country(title)
            track_info = "Map pin available. Track path can be added later for cyclones when NOAA/NHC storm-track data is connected."
            if peril != "Tropical Cyclone":
                track_info = "Map pin available. Event path data source not yet connected for this peril."

            events.append({
                "Event_ID": make_id("GDACS", title + link),
                "Event_Name": title,
                "Peril": peril,
                "Event_Status": "Active",
                "Severity": severity,
                "Location_Label": location,
                "Country": country,
                "Latitude": lat,
                "Longitude": lon,
                "Start_Date": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                "Latest_Update_Date": utc_now_text(),
                "Source_Name": "GDACS",
                "Source_Link": link,
                "Physical_Intensity": short_text(summary, 250) or "See source for alert details",
                "Human_Impact": "Check GDACS and follow-up reports",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "Medium to High for alert status; Low for impact and loss",
                "Board_Summary": (
                    f"GDACS alert: {title}. Monitor this event for affected population, escalation or de-escalation, and any emerging public economic or insured loss estimates."
                ),
                "Comparable_Events": "To be assessed",
                "Track_Info": track_info,
                "Notes": "Automated GDACS RSS feed."
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
    df["Start_Date_Sort"] = pd.to_datetime(df["Start_Date"], errors="coerce")
    df = df.sort_values(["Severity_Rank", "Start_Date_Sort"], ascending=[False, False])
    return df


# ---------- Presentation ----------
def render_badges(event: pd.Series) -> str:
    sev = event.get("Severity", "Unknown")
    peril = event.get("Peril", "Other")
    source = event.get("Source_Name", "Source")
    return (
        f"<span class='badge sev-{sev}'>{sev}</span>"
        f"<span class='pill'>{peril_emoji(peril)} {peril}</span>"
        f"<span class='pill'>Source: {source}</span>"
    )


def render_event_card(event: pd.Series):
    st.markdown(
        f"""
        <div class='event-card'>
            {render_badges(event)}
            <div class='card-title'>{event.get('Event_Name', 'Unnamed event')}</div>
            <div class='card-meta'>
                <b>Country / Area:</b> {event.get('Country', 'Unknown')}<br>
                <b>Location:</b> {event.get('Location_Label', 'Unknown')}<br>
                <b>Latest:</b> {event.get('Latest_Update_Date', 'Unknown')}<br>
                <b>Loss watch:</b> {event.get('Industry_Loss_Status', 'Unknown')}<br>
                <b>Summary:</b> {short_text(event.get('Board_Summary', ''), 180)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def board_summary(event: pd.Series) -> str:
    return f"""
BOARD UPDATE – {event.get('Event_Name', 'Selected event')}

Status: {event.get('Event_Status', 'Unknown')}
Peril: {event.get('Peril', 'Unknown')}
Severity: {event.get('Severity', 'Unknown')}
Country / area: {event.get('Country', 'Unknown')}
Location: {event.get('Location_Label', 'Unknown')}
Latest update: {event.get('Latest_Update_Date', 'Unknown')}
Source: {event.get('Source_Name', 'Unknown')}

Executive view:
{event.get('Board_Summary', 'No summary available')}

Hazard / physical intensity:
{event.get('Physical_Intensity', 'Unknown')}

Human impact:
{event.get('Human_Impact', 'Unknown')}

Economic / insured / industry loss:
Economic loss: {event.get('Economic_Loss', 'Unknown')}
Insured loss: {event.get('Insured_Loss', 'Unknown')}
Industry loss status: {event.get('Industry_Loss_Status', 'Unknown')}

Suggested action:
Continue monitoring official disaster alerts and public loss commentary. Treat any impact figures as preliminary unless confirmed by recognized sources.

Source link:
{event.get('Source_Link', '')}
""".strip()


# ---------- App ----------
def main():
    inject_css()

    st.markdown(
        f"""
        <div class='hero'>
            <h1>🌍 CatWatch</h1>
            <p>A cleaner live catastrophe event monitor designed for fast reading on phone and tablet — with color-coded severity, country / area information, map view, and board-ready summaries.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    df = load_events()
    if df.empty:
        st.error("No event data loaded. Check internet access or source availability.")
        return

    with st.sidebar:
        st.header("Filter events")
        if st.button("Refresh live data"):
            st.cache_data.clear()
            st.rerun()

        peril_options = ["All"] + sorted(df["Peril"].dropna().unique().tolist())
        severity_options = ["All"] + sorted(df["Severity"].dropna().unique().tolist(), key=severity_rank, reverse=True)
        country_options = ["All"] + sorted(df["Country"].dropna().astype(str).unique().tolist())

        selected_peril = st.selectbox("Peril", peril_options)
        selected_severity = st.selectbox("Severity", severity_options)
        selected_country = st.selectbox("Country / area", country_options)
        search = st.text_input("Search event / place")

    filtered = df.copy()
    if selected_peril != "All":
        filtered = filtered[filtered["Peril"] == selected_peril]
    if selected_severity != "All":
        filtered = filtered[filtered["Severity"] == selected_severity]
    if selected_country != "All":
        filtered = filtered[filtered["Country"] == selected_country]
    if search.strip():
        needle = search.lower().strip()
        mask = filtered.apply(lambda row: needle in " ".join(row.astype(str)).lower(), axis=1)
        filtered = filtered[mask]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Events shown", len(filtered))
    k2.metric("Critical / Red", int(filtered["Severity"].isin(["Critical", "Red"]).sum()))
    k3.metric("Countries / areas", int(filtered["Country"].nunique()))
    k4.metric("Last refresh", utc_now_text().split()[1] + " UTC")

    selected_name = None
    if not filtered.empty:
        selected_name = st.selectbox(
            "Open an event",
            filtered["Event_Name"].tolist(),
            help="Select an event to view full details below.",
        )
        event = filtered[filtered["Event_Name"] == selected_name].iloc[0]
    else:
        event = None

    tab1, tab2, tab3, tab4 = st.tabs([
        "Overview",
        "Event Detail",
        "Loss Watch",
        "Board Brief"
    ])

    with tab1:
        left, right = st.columns([1.1, 1])
        with left:
            st.subheader("Top events to watch")
            if filtered.empty:
                st.info("No events match the current filters.")
            else:
                for _, row in filtered.head(8).iterrows():
                    render_event_card(row)
        with right:
            st.subheader("Global event map")
            map_df = filtered[["Latitude", "Longitude"]].dropna().rename(columns={"Latitude": "lat", "Longitude": "lon"})
            if not map_df.empty:
                st.map(map_df, latitude="lat", longitude="lon", zoom=1)
                st.caption("Map shows event points currently available from the live sources.")
            else:
                st.info("No map coordinates available for the selected filters.")

            st.markdown("<div class='mini-note'>Storm path / track view can be added next when we connect cyclone track feeds such as NOAA / NHC.</div>", unsafe_allow_html=True)

    with tab2:
        st.subheader("Easy-to-read event detail")
        if event is not None:
            st.markdown(render_badges(event), unsafe_allow_html=True)
            st.markdown(f"### {event['Event_Name']}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Severity", event["Severity"])
            c2.metric("Peril", event["Peril"])
            c3.metric("Status", event["Event_Status"])
            c4.metric("Country / Area", event["Country"])

            a, b = st.columns([1.3, 1])
            with a:
                st.markdown("<div class='section-card'>", unsafe_allow_html=True)
                st.markdown("#### Executive summary")
                st.markdown(f"<div class='summary-box'>{event['Board_Summary']}</div>", unsafe_allow_html=True)
                st.markdown("#### Details")
                st.write(f"**Location:** {event['Location_Label']}")
                st.write(f"**Physical intensity:** {event['Physical_Intensity']}")
                st.write(f"**Human impact:** {event['Human_Impact']}")
                st.write(f"**Economic loss:** {event['Economic_Loss']}")
                st.write(f"**Insured loss:** {event['Insured_Loss']}")
                st.write(f"**Industry loss status:** {event['Industry_Loss_Status']}")
                st.write(f"**Event path / map status:** {event['Track_Info']}")
                st.write(f"**Confidence level:** {event['Confidence_Level']}")
                st.write(f"**Source:** [{event['Source_Name']}]({event['Source_Link']})")
                st.markdown("</div>", unsafe_allow_html=True)
            with b:
                st.markdown("<div class='section-card'>", unsafe_allow_html=True)
                st.markdown("#### Timing")
                st.write(f"**Event start / feed time:** {event['Start_Date']}")
                st.write(f"**Latest refresh:** {event['Latest_Update_Date']}")
                st.markdown("#### Map")
                if pd.notna(event.get("Latitude")) and pd.notna(event.get("Longitude")):
                    map_df = pd.DataFrame([{"lat": event["Latitude"], "lon": event["Longitude"]}])
                    st.map(map_df, latitude="lat", longitude="lon", zoom=3)
                else:
                    st.info("No coordinates available for this event yet.")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Choose an event above to see details.")

    with tab3:
        st.subheader("Affected regions & industry loss watch")
        st.info(
            "This version highlights whether public economic or insured loss information is available. "
            "Open-source loss data is often incomplete in the early hours of an event."
        )
        loss_cols = [
            "Severity", "Peril", "Country", "Event_Name", "Human_Impact",
            "Economic_Loss", "Insured_Loss", "Industry_Loss_Status", "Source_Name"
        ]
        if not filtered.empty:
            st.dataframe(filtered[loss_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No events match the current filters.")

    with tab4:
        st.subheader("Board-ready brief")
        if event is not None:
            summary = board_summary(event)
            st.text_area("Copy / edit this board update", summary, height=420)
            st.download_button(
                "Download board summary",
                summary.encode("utf-8"),
                "catwatch_board_summary.txt",
                "text/plain",
            )
        else:
            st.info("Choose an event above to generate the board brief.")


if __name__ == "__main__":
    main()
