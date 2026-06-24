import hashlib
import re
from datetime import datetime, timezone

import feedparser
import pandas as pd
import requests
import streamlit as st
from dateutil import parser as dateparser


st.set_page_config(
    page_title="CatWatch – Live Catastrophe Monitor",
    page_icon="🌍",
    layout="wide",
)

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
RELIEFWEB_API_URL = "https://api.reliefweb.int/v1/reports"


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


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", text).strip()


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

            events.append({
                "Event_ID": f"USGS-{feature.get('id', make_id('EQ', place))}",
                "Event_Name": f"M{mag} earthquake - {place}",
                "Peril": "Earthquake",
                "Event_Status": "Active",
                "Severity": severity,
                "Country_or_Region": place,
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
                "Confidence_Level": "High for hazard parameters; Low for loss impact",
                "Board_Summary": (
                    f"USGS reports a magnitude {mag} earthquake near {place}. "
                    "Human impact and insured/economic loss are not available from this feed and require monitoring from humanitarian and public loss sources."
                ),
                "Comparable_Events": "To be assessed",
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

            events.append({
                "Event_ID": make_id("GDACS", title + link),
                "Event_Name": title,
                "Peril": peril,
                "Event_Status": "Active",
                "Severity": severity,
                "Country_or_Region": title,
                "Latitude": lat,
                "Longitude": lon,
                "Start_Date": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                "Latest_Update_Date": utc_now_text(),
                "Source_Name": "GDACS",
                "Source_Link": link,
                "Physical_Intensity": summary[:250],
                "Human_Impact": "Check GDACS/ReliefWeb updates",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "Medium to High for alert status; Low for loss impact",
                "Board_Summary": (
                    f"GDACS alert: {title}. The event should be monitored for affected population, casualty updates, "
                    "and any emerging public economic or insured loss estimates."
                ),
                "Comparable_Events": "To be assessed",
                "Notes": "Automated GDACS RSS feed."
            })
    except Exception as e:
        st.warning(f"GDACS fetch failed: {e}")
    return events


@st.cache_data(ttl=600)
def fetch_reliefweb_reports() -> list[dict]:
    events = []
    try:
        params = {
            "appname": "catwatch",
            "profile": "list",
            "preset": "latest",
            "limit": 25,
            "query[value]": "earthquake OR flood OR cyclone OR hurricane OR typhoon OR wildfire OR drought OR volcano",
            "sort[]": "date:desc",
        }
        r = requests.get(RELIEFWEB_API_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        for item in data.get("data", []):
            fields = item.get("fields", {}) or {}
            title = fields.get("title", "ReliefWeb report")
            link = fields.get("url_alias", "")
            date = fields.get("date", {}).get("created") or fields.get("date", {}).get("original")
            dt = parse_date(date)
            countries = ", ".join([c.get("name", "") for c in fields.get("country", [])]) or "Unknown"
            sources = ", ".join([s.get("name", "") for s in fields.get("source", [])]) or "ReliefWeb"
            peril = infer_peril(title)

            events.append({
                "Event_ID": make_id("RW", title + link),
                "Event_Name": title,
                "Peril": peril,
                "Event_Status": "Watching",
                "Severity": "Unknown",
                "Country_or_Region": countries,
                "Latitude": None,
                "Longitude": None,
                "Start_Date": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                "Latest_Update_Date": utc_now_text(),
                "Source_Name": f"ReliefWeb / {sources}",
                "Source_Link": link,
                "Physical_Intensity": "Report-based update",
                "Human_Impact": "Review report for casualties, displacement, affected population",
                "Economic_Loss": "Unknown",
                "Insured_Loss": "Unknown",
                "Industry_Loss_Status": "Not yet reported",
                "Confidence_Level": "Medium; depends on underlying reporting source",
                "Board_Summary": (
                    f"ReliefWeb report for {countries}: {title}. Use this as a humanitarian impact update and verify any figures against the original source."
                ),
                "Comparable_Events": "To be assessed",
                "Notes": "Automated ReliefWeb latest reports search."
            })
    except Exception as e:
        st.warning(f"ReliefWeb fetch failed: {e}")
    return events


@st.cache_data(ttl=300)
def load_events() -> pd.DataFrame:
    rows = []
    rows.extend(fetch_usgs_events())
    rows.extend(fetch_gdacs_events())
    rows.extend(fetch_reliefweb_reports())

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["Severity_Rank"] = df["Severity"].apply(severity_rank)
    df = df.sort_values(["Severity_Rank", "Start_Date"], ascending=[False, False])
    return df


def board_summary(event: pd.Series) -> str:
    return f"""
BOARD UPDATE – {event.get('Event_Name', 'Selected event')}

Status: {event.get('Event_Status', 'Unknown')}
Peril: {event.get('Peril', 'Unknown')}
Severity: {event.get('Severity', 'Unknown')}
Location/region: {event.get('Country_or_Region', 'Unknown')}
Latest update: {event.get('Latest_Update_Date', 'Unknown')}
Source: {event.get('Source_Name', 'Unknown')}

Executive view:
{event.get('Board_Summary', 'No summary available')}

Human impact:
{event.get('Human_Impact', 'Unknown')}

Economic / insured / industry loss:
Economic loss: {event.get('Economic_Loss', 'Unknown')}
Insured loss: {event.get('Insured_Loss', 'Unknown')}
Industry loss status: {event.get('Industry_Loss_Status', 'Unknown')}

Suggested action:
Continue monitoring official disaster alerts, humanitarian reports, and public insured-loss commentary. Treat loss figures as preliminary unless confirmed by a recognized loss-reporting source.

Source link:
{event.get('Source_Link', '')}
""".strip()


def main():
    st.title("🌍 CatWatch – Live Catastrophe Monitor")
    st.caption("Prototype: open-source catastrophe event tracker for hazard, affected regions, casualties, industry loss watch, and board summaries.")

    with st.sidebar:
        st.header("Filters")
        refresh = st.button("Refresh data")
        if refresh:
            st.cache_data.clear()
            st.rerun()

    df = load_events()

    if df.empty:
        st.error("No event data loaded. Check internet access or source availability.")
        return

    with st.sidebar:
        peril_options = ["All"] + sorted(df["Peril"].dropna().unique().tolist())
        severity_options = ["All"] + sorted(df["Severity"].dropna().unique().tolist(), key=severity_rank, reverse=True)
        selected_peril = st.selectbox("Peril", peril_options)
        selected_severity = st.selectbox("Severity", severity_options)
        search = st.text_input("Search event / country / region")

    filtered = df.copy()
    if selected_peril != "All":
        filtered = filtered[filtered["Peril"] == selected_peril]
    if selected_severity != "All":
        filtered = filtered[filtered["Severity"] == selected_severity]
    if search.strip():
        mask = filtered.apply(lambda row: search.lower() in " ".join(row.astype(str)).lower(), axis=1)
        filtered = filtered[mask]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Events shown", len(filtered))
    k2.metric("Critical/Red", int(filtered["Severity"].isin(["Critical", "Red"]).sum()))
    k3.metric("Earthquakes", int((filtered["Peril"] == "Earthquake").sum()))
    k4.metric("Loss estimates", int((filtered["Industry_Loss_Status"] != "Not yet reported").sum()))

    tab1, tab2, tab3, tab4 = st.tabs([
        "Live Event Feed",
        "Event Detail",
        "Affected Regions & Loss Watch",
        "Board Summary"
    ])

    with tab1:
        st.subheader("Live Event Feed")
        display_cols = [
            "Severity", "Peril", "Event_Name", "Country_or_Region",
            "Start_Date", "Source_Name", "Industry_Loss_Status", "Confidence_Level"
        ]
        st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
        st.download_button(
            "Download filtered events as CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            "catwatch_events.csv",
            "text/csv",
        )

    selected_event_name = None
    if not filtered.empty:
        selected_event_name = st.selectbox(
            "Select event for detail / board summary",
            filtered["Event_Name"].tolist()
        )
        event = filtered[filtered["Event_Name"] == selected_event_name].iloc[0]
    else:
        event = None

    with tab2:
        st.subheader("Event Detail")
        if event is not None:
            left, right = st.columns([2, 1])
            with left:
                st.markdown(f"### {event['Event_Name']}")
                st.write(event["Board_Summary"])
                st.write(f"**Physical intensity:** {event['Physical_Intensity']}")
                st.write(f"**Human impact:** {event['Human_Impact']}")
                st.write(f"**Economic loss:** {event['Economic_Loss']}")
                st.write(f"**Insured loss:** {event['Insured_Loss']}")
                st.write(f"**Industry loss status:** {event['Industry_Loss_Status']}")
                st.write(f"**Source:** [{event['Source_Name']}]({event['Source_Link']})")
            with right:
                st.metric("Severity", event["Severity"])
                st.metric("Peril", event["Peril"])
                st.metric("Status", event["Event_Status"])
                st.caption(f"Confidence: {event['Confidence_Level']}")

            if pd.notna(event.get("Latitude")) and pd.notna(event.get("Longitude")):
                map_df = pd.DataFrame([{"lat": event["Latitude"], "lon": event["Longitude"]}])
                st.map(map_df, latitude="lat", longitude="lon", zoom=3)

    with tab3:
        st.subheader("Affected Regions & Industry Loss Watch")
        st.info(
            "This prototype currently shows open-source event alerts. "
            "Public industry loss estimates are often delayed or subscription-based, so this section flags whether a public loss estimate is available."
        )
        loss_cols = [
            "Event_Name", "Country_or_Region", "Human_Impact",
            "Economic_Loss", "Insured_Loss", "Industry_Loss_Status", "Source_Name"
        ]
        st.dataframe(filtered[loss_cols], use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("Board Summary Draft")
        if event is not None:
            summary = board_summary(event)
            st.text_area("Copy/paste board update", summary, height=420)
            st.download_button(
                "Download board summary text",
                summary.encode("utf-8"),
                "catwatch_board_summary.txt",
                "text/plain",
            )


if __name__ == "__main__":
    main()
