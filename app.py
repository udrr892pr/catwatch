
import hashlib, re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
from dateutil import parser as dateparser
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="CatWatch Mobile", page_icon="🌍", layout="centered", initial_sidebar_state="collapsed")

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson"
USGS_30DAY_URL = USGS_URL
GDACS_RSS_URL = "https://www.gdacs.org/xml/rss.xml"
CURRENT_YEAR = datetime.now(timezone.utc).year
VERIFIED_NEWS = ["Reuters","Associated Press","AP News","BBC","The Guardian","Financial Times","Bloomberg","Al Jazeera","CNN","NHK","NPR","ABC News","CBS News","NBC News","New York Times","Washington Post","DW","France 24"]

def css():
    st.markdown("""
    <style>
    .block-container{padding:0.65rem 0.55rem 2.2rem 0.55rem;max-width:760px}
    html,body,[class*="css"]{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif}
    .main{background:linear-gradient(180deg,#f8fafc 0%,#fff 32%)}
    .hero{background:linear-gradient(145deg,#0f172a 0%,#1d4ed8 58%,#0284c7 100%);color:white;padding:1rem;border-radius:24px;margin-bottom:.8rem;box-shadow:0 14px 32px rgba(15,23,42,.20)}
    .title{font-size:1.55rem;font-weight:900;letter-spacing:-.03em;line-height:1.1;margin:0}
    .sub{font-size:.90rem;opacity:.92;line-height:1.38;margin-top:.35rem}
    .section{font-size:1.02rem;font-weight:850;color:#0f172a;margin:.85rem 0 .45rem 0}
    .card{background:white;border:1px solid #e2e8f0;border-radius:20px;padding:.86rem;box-shadow:0 8px 22px rgba(15,23,42,.06);margin-bottom:.72rem}
    .event{border-left:6px solid #94a3b8}.b-Critical{border-left-color:#7f1d1d}.b-Red{border-left-color:#dc2626}.b-Orange{border-left-color:#f97316}.b-Amber{border-left-color:#f59e0b}.b-Yellow{border-left-color:#eab308}.b-Green{border-left-color:#22c55e}.b-Unknown{border-left-color:#94a3b8}
    .et{font-size:1.04rem;font-weight:900;color:#0f172a;margin:.2rem 0 .25rem 0;line-height:1.28}
    .meta{color:#475569;font-size:.89rem;line-height:1.43}
    .badge{display:inline-block;border-radius:999px;padding:.20rem .55rem;font-size:.72rem;font-weight:850;margin-right:.26rem;margin-bottom:.30rem}
    .sev-Critical{background:#7f1d1d;color:white}.sev-Red{background:#dc2626;color:white}.sev-Orange{background:#f97316;color:white}.sev-Amber{background:#f59e0b;color:#111827}.sev-Yellow{background:#fde68a;color:#111827}.sev-Green{background:#22c55e;color:#052e16}.sev-Unknown{background:#cbd5e1;color:#0f172a}
    .tier-P1{background:#991b1b;color:white}.tier-P2{background:#ea580c;color:white}.tier-P3{background:#2563eb;color:white}.tier-P4{background:#64748b;color:white}
    .pill{display:inline-block;border-radius:999px;padding:.20rem .53rem;font-size:.72rem;font-weight:780;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;margin-right:.26rem;margin-bottom:.30rem}
    .chip{display:inline-block;border-radius:999px;padding:.18rem .50rem;font-size:.70rem;font-weight:780;background:#f1f5f9;color:#334155;margin-right:.26rem;margin-bottom:.30rem}
    .summary{background:#f8fafc;border-left:5px solid #2563eb;border-radius:14px;padding:.85rem;color:#0f172a;line-height:1.5;margin-bottom:.7rem;font-size:.92rem}
    .warn{background:#fff7ed;border-left:5px solid #f97316;border-radius:14px;padding:.85rem;color:#0f172a;line-height:1.45;margin-bottom:.7rem;font-size:.90rem}
    div[data-testid="stMetric"]{background:white;border:1px solid #e2e8f0;border-radius:18px;padding:.50rem;box-shadow:0 5px 18px rgba(15,23,42,.05)}
    div[data-testid="stMetricLabel"]{font-size:.72rem} div[data-testid="stMetricValue"]{font-size:1.02rem}
    .stTabs [data-baseweb="tab-list"]{gap:.28rem;overflow-x:auto;white-space:nowrap;padding-bottom:.25rem}
    .stTabs [data-baseweb="tab"]{border-radius:999px;background:#eff6ff;padding:.38rem .68rem;height:auto;font-size:.82rem}
    div[data-baseweb="select"]>div{border-radius:14px}.stTextInput input{border-radius:14px}
    </style>
    """, unsafe_allow_html=True)

def now_txt(): return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def make_id(p,t): return f"{p}-{hashlib.md5(t.encode()).hexdigest()[:10].upper()}"
def clean(x): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",str(x or ""))).strip()
def dt(x):
    try:
        if isinstance(x,(int,float)): return datetime.fromtimestamp(x/1000,tz=timezone.utc)
        d=dateparser.parse(str(x)); return d.replace(tzinfo=d.tzinfo or timezone.utc) if d else None
    except Exception: return None
def short(x,n=180):
    x=str(x or ""); return x if len(x)<=n else x[:n-1].rstrip()+"…"
def sev_rank(s): return {"Critical":5,"Red":4,"Orange":3,"Amber":3,"Yellow":2,"Green":1,"Unknown":0}.get(str(s),0)
def sev_color(s): return {"Critical":[127,29,29,220],"Red":[220,38,38,210],"Orange":[249,115,22,205],"Amber":[245,158,11,205],"Yellow":[253,230,138,205],"Green":[34,197,94,190],"Unknown":[100,116,139,180]}.get(str(s),[100,116,139,180])
def eq_sev(m):
    try: m=float(m)
    except Exception: return "Unknown"
    return "Critical" if m>=7.5 else "Red" if m>=6.5 else "Amber" if m>=5.5 else "Green"
def gdacs_sev(t,s):
    x=f"{t} {s}".lower()
    return "Red" if "red" in x else "Orange" if "orange" in x else "Yellow" if "yellow" in x else "Green" if "green" in x else "Unknown"
def peril(x):
    y=str(x).lower()
    for k,v in [("earthquake","Earthquake"),("tropical cyclone","Tropical Cyclone"),("cyclone","Tropical Cyclone"),("hurricane","Tropical Cyclone"),("typhoon","Tropical Cyclone"),("flood","Flood"),("wildfire","Wildfire"),("fire","Wildfire"),("volcano","Volcano"),("tsunami","Tsunami"),("drought","Drought"),("landslide","Landslide"),("storm","Severe Storm"),("hail","Severe Storm"),("tornado","Severe Storm")]:
        if k in y: return v
    return "Other"
def emoji(p): return {"Earthquake":"🌎","Tropical Cyclone":"🌀","Flood":"🌊","Wildfire":"🔥","Volcano":"🌋","Tsunami":"🌊","Drought":"☀️","Landslide":"⛰️","Severe Storm":"⛈️","Other":"📍"}.get(str(p),"📍")
def country(x):
    x=str(x or "").strip()
    if not x: return "Unknown"
    if "," in x: return x.split(",")[-1].strip()
    low=x.lower()
    for m in [" in "," near "," of "]:
        if m in low: return x[low.rfind(m)+len(m):].strip().title()
    return x
def tier(sev,p,intensity=""):
    z=f"{sev} {p} {intensity}".lower()
    if sev in {"Critical","Red"} or "magnitude 6." in z or "magnitude 7" in z or "magnitude 8" in z: return "P1"
    if sev in {"Orange","Amber"}: return "P2"
    if sev in {"Yellow","Green"}: return "P3"
    return "P4"
def tier_label(t): return {"P1":"P1 Executive Alert","P2":"P2 Analyst Watch","P3":"P3 Monitor","P4":"P4 Information"}.get(t,"P4 Information")
def next_hint(r):
    if r.get("Peril")=="Tropical Cyclone": return "Next advisory cycle; more often near landfall."
    if r.get("Source_Name")=="USGS": return "15–30 min for major earthquake; then as impacts emerge."
    return "15–30 min until stable." if r.get("Notification_Tier")=="P1" else "1–3 hours or when source changes." if r.get("Notification_Tier")=="P2" else "Daily or on escalation."
def action(r):
    if r.get("Notification_Tier")=="P1": return "Prepare management update; verify exposure/loss relevance; monitor every 15–30 min."
    if r.get("Notification_Tier")=="P2": return "Keep on analyst watchlist; check escalation, population affected, impact reports and public loss commentary."
    return "Monitor for official, vendor, humanitarian or loss-related updates."

@st.cache_data(ttl=300)
def fetch_usgs():
    out=[]
    try:
        js=requests.get(USGS_URL,timeout=20).json()
        for f in js.get("features",[]):
            pr=f.get("properties",{}) or {}; geo=f.get("geometry",{}) or {}; c=geo.get("coordinates",[None,None,None])
            m=pr.get("mag"); place=pr.get("place") or "Unknown location"; d=dt(pr.get("time")); s=eq_sev(m)
            intensity=f"Magnitude {m}; depth {c[2] if len(c)>2 else 'Unknown'} km"; tr=tier(s,"Earthquake",intensity)
            out.append({"Event_ID":f"USGS-{f.get('id',make_id('EQ',place))}","Event_Name":f"M{m} earthquake - {place}","Peril":"Earthquake","Event_Status":"Active","Severity":s,"Notification_Tier":tr,"Country":country(place),"Location_Label":place,"Latitude":c[1] if len(c)>1 else None,"Longitude":c[0] if len(c)>0 else None,"Start_Date":d.strftime("%Y-%m-%d %H:%M UTC") if d else "","Latest_Update_Date":now_txt(),"Source_Name":"USGS","Source_Link":pr.get("url") or "","Physical_Intensity":intensity,"Human_Impact":"Unknown from USGS feed","Economic_Loss":"Unknown","Insured_Loss":"Unknown","Industry_Loss_Status":"Not yet reported","Confidence_Level":"High for hazard; low for impact/loss","Why_It_Matters":"Earthquake parameters are confirmed quickly, but casualties, damage and insured loss require follow-up reporting.","Management_Summary":f"USGS reports a magnitude {m} earthquake near {place}. Initial hazard information is available; impact and loss remain uncertain.","Track_Info":"Point location available. Earthquakes do not have a forecast track."})
    except Exception as e: st.warning(f"USGS fetch failed: {e}")
    return out

@st.cache_data(ttl=300)
def fetch_gdacs():
    out=[]
    try:
        feed=feedparser.parse(GDACS_RSS_URL)
        for e in feed.entries[:50]:
            title=getattr(e,"title","GDACS event"); summ=clean(getattr(e,"summary","")); link=getattr(e,"link","")
            d=dt(getattr(e,"published",None) or getattr(e,"updated",None)); s=gdacs_sev(title,summ); p=peril(title+" "+summ); tr=tier(s,p,summ)
            lat=lon=None
            if hasattr(e,"georss_point"):
                try:
                    a=str(e.georss_point).split(); lat=float(a[0]); lon=float(a[1])
                except Exception: pass
            track="Track connector planned: official cyclone forecast track feed. Current version shows event point/alert only." if p=="Tropical Cyclone" else "Map point available when coordinates are provided. No footprint/path layer connected yet."
            out.append({"Event_ID":make_id("GDACS",title+link),"Event_Name":title,"Peril":p,"Event_Status":"Active","Severity":s,"Notification_Tier":tr,"Country":country(title),"Location_Label":title,"Latitude":lat,"Longitude":lon,"Start_Date":d.strftime("%Y-%m-%d %H:%M UTC") if d else "","Latest_Update_Date":now_txt(),"Source_Name":"GDACS","Source_Link":link,"Physical_Intensity":short(summ,250) or "See GDACS source.","Human_Impact":"Check GDACS and follow-up official/humanitarian reports","Economic_Loss":"Unknown","Insured_Loss":"Unknown","Industry_Loss_Status":"Not yet reported","Confidence_Level":"Medium/high for alert; low for loss","Why_It_Matters":"GDACS flags potentially significant sudden-onset disasters; analyst review is needed for impact and loss relevance.","Management_Summary":f"GDACS alert: {title}. Monitor for affected population, escalation, impact reports and public economic/insured loss estimates.","Track_Info":track})
    except Exception as e: st.warning(f"GDACS fetch failed: {e}")
    return out

@st.cache_data(ttl=300)
def load_events():
    rows=fetch_usgs()+fetch_gdacs()
    if not rows: return pd.DataFrame()
    df=pd.DataFrame(rows)
    df["Severity_Rank"]=df["Severity"].apply(sev_rank)
    df["Tier_Rank"]=df["Notification_Tier"].map({"P1":4,"P2":3,"P3":2,"P4":1}).fillna(0)
    df["Start_Date_Sort"]=pd.to_datetime(df["Start_Date"],errors="coerce")
    df["Map_Color"]=df["Severity"].apply(sev_color)
    df["Analyst_Action"]=df.apply(action,axis=1)
    df["Next_Update"]=df.apply(next_hint,axis=1)
    return df.sort_values(["Tier_Rank","Severity_Rank","Start_Date_Sort"],ascending=[False,False,False])

@st.cache_data(ttl=900)
def fetch_news(event_name,country_name,peril_name):
    q=f'"{event_name}" OR "{country_name}" {peril_name} disaster loss casualties damage'
    url="https://news.google.com/rss/search?q="+quote_plus(q)+"&hl=en-US&gl=US&ceid=US:en"
    rows=[]
    try:
        feed=feedparser.parse(url)
        for e in feed.entries[:50]:
            title=clean(getattr(e,"title","")); link=getattr(e,"link",""); published=getattr(e,"published","")
            src=""
            try: src=e.source.title
            except Exception:
                if " - " in title: src=title.split(" - ")[-1].strip()
            if not any(v.lower() in src.lower() for v in VERIFIED_NEWS): continue
            rows.append({"Title":title,"Source":src or "Verified news","Published":published,"Link":link})
            if len(rows)>=12: break
    except Exception as exc: st.warning(f"News fetch failed: {exc}")
    return pd.DataFrame(rows)

def inflation(v,year,rate=.03):
    try: return round(float(v)*((1+rate)**max(0,CURRENT_YEAR-int(year))),1)
    except Exception: return None

@st.cache_data
def load_history():
    # Starter set: approximate USD bn; verify before formal use. Designed to be replaced/extended with EM-DAT, NOAA, PERILS and licensed data.
    rec=[
    ("HIST-001","Hurricane Andrew",1992,"United States","Florida/Louisiana","Tropical Cyclone",27.3,15.5,15.5,65),
    ("HIST-002","Northridge Earthquake",1994,"United States","California","Earthquake",44.0,15.3,15.3,57),
    ("HIST-003","Kobe / Great Hanshin Earthquake",1995,"Japan","Kobe","Earthquake",100.0,3.0,3.0,6434),
    ("HIST-004","Hurricane Katrina",2005,"United States","Louisiana/Mississippi","Tropical Cyclone",125.0,65.0,65.0,1833),
    ("HIST-005","Wenchuan / Sichuan Earthquake",2008,"China","Sichuan","Earthquake",150.0,1.0,1.0,87587),
    ("HIST-006","Chile Maule Earthquake",2010,"Chile","Maule/Concepción","Earthquake",30.0,8.0,8.0,525),
    ("HIST-007","Tohoku Earthquake & Tsunami",2011,"Japan","Tohoku","Earthquake / Tsunami",235.0,35.0,35.0,19759),
    ("HIST-008","Thailand Floods",2011,"Thailand","Central Thailand","Flood",46.5,16.0,16.0,815),
    ("HIST-009","Christchurch Earthquakes",2010,"New Zealand","Canterbury","Earthquake",40.0,30.0,30.0,185),
    ("HIST-010","Hurricane Sandy",2012,"United States","Northeast U.S.","Tropical Cyclone / Storm Surge",70.0,30.0,30.0,233),
    ("HIST-011","Central Europe Floods",2013,"Germany / Central Europe","Germany/Austria/Czechia","Flood",16.0,4.0,4.0,25),
    ("HIST-012","Hurricane Harvey",2017,"United States","Texas","Tropical Cyclone / Flood",125.0,30.0,30.0,107),
    ("HIST-013","Hurricane Irma",2017,"Caribbean / United States","Caribbean/Florida","Tropical Cyclone",77.0,32.0,32.0,134),
    ("HIST-014","Hurricane Maria",2017,"Puerto Rico / Caribbean","Puerto Rico","Tropical Cyclone",90.0,32.0,32.0,3059),
    ("HIST-015","Camp Fire",2018,"United States","California","Wildfire",16.5,12.0,12.0,85),
    ("HIST-016","Typhoon Jebi",2018,"Japan","Kansai","Tropical Cyclone",13.0,12.0,12.0,17),
    ("HIST-017","Australia Black Summer Bushfires",2019,"Australia","NSW/Victoria","Wildfire",100.0,2.0,2.0,34),
    ("HIST-018","Europe Floods",2021,"Germany / Belgium","Ahr Valley/Belgium","Flood",54.0,13.0,13.0,243),
    ("HIST-019","Hurricane Ida",2021,"United States","Louisiana/Northeast","Tropical Cyclone / Flood",75.0,36.0,36.0,107),
    ("HIST-020","Hurricane Ian",2022,"United States","Florida","Tropical Cyclone / Storm Surge",113.0,60.0,60.0,161),
    ("HIST-021","Türkiye–Syria Earthquakes",2023,"Türkiye / Syria","Kahramanmaraş","Earthquake",100.0,5.0,5.0,59000),
    ("HIST-022","Hurricane Otis",2023,"Mexico","Acapulco","Tropical Cyclone",15.0,2.0,2.0,52),
    ("HIST-023","Noto Peninsula Earthquake",2024,"Japan","Ishikawa","Earthquake",17.0,3.0,3.0,240),
    ("HIST-024","Hurricane Beryl",2024,"Caribbean / United States","Caribbean/Texas","Tropical Cyclone",7.0,3.0,3.0,70),
    ("HIST-025","Los Angeles Wildfires",2025,"United States","California","Wildfire",100.0,40.0,40.0,None),
    ]
    cols=["Event_ID","Event_Name","Year","Country","Region","Peril","Economic_Loss_USD_Bn_Reported","Insured_Loss_USD_Bn_Reported","Industry_Loss_USD_Bn_Reported","Fatalities"]
    df=pd.DataFrame(rec,columns=cols)
    for c in ["Economic_Loss_USD_Bn_Reported","Insured_Loss_USD_Bn_Reported","Industry_Loss_USD_Bn_Reported"]:
        df[c.replace("_Reported","_Today_Approx")]=df.apply(lambda r: inflation(r[c],r["Year"]),axis=1)
    df["Inflation_Method"]="Approximate 3% annual USD compounding; replace with official CPI/licensed loss tables."
    df["Source_Status"]="Starter dataset; verify before formal use"
    return df

def html_badges(r):
    s=r.get("Severity","Unknown"); t=r.get("Notification_Tier","P4"); p=r.get("Peril","Other")
    return f"<span class='badge tier-{t}'>{tier_label(t)}</span><span class='badge sev-{s}'>{s}</span><span class='pill'>{emoji(p)} {p}</span><span class='chip'>{r.get('Source_Name','Source')}</span>"
def card(r):
    s=r.get("Severity","Unknown")
    st.markdown(f"""<div class="card event b-{s}">{html_badges(r)}<div class="et">{r.get('Event_Name')}</div><div class="meta"><b>Country / area:</b> {r.get('Country')}<br><b>Why it matters:</b> {short(r.get('Why_It_Matters'),155)}<br><b>Next update:</b> {r.get('Next_Update')}<br><b>Loss watch:</b> {r.get('Industry_Loss_Status')}</div></div>""",unsafe_allow_html=True)
def news_card(r):
    st.markdown(f"""<div class="card"><span class="chip">{r.get('Source')}</span><div class="et">{r.get('Title')}</div><div class="meta"><b>Published:</b> {r.get('Published')}<br><a href="{r.get('Link')}" target="_blank">Open news item</a></div></div>""",unsafe_allow_html=True)
def hist_card(r):
    st.markdown(f"""<div class="card"><span class="badge sev-Unknown">{r.get('Year')}</span><span class="pill">{emoji(r.get('Peril'))} {r.get('Peril')}</span><div class="et">{r.get('Event_Name')}</div><div class="meta"><b>Country:</b> {r.get('Country')}<br><b>Economic loss:</b> USD {r.get('Economic_Loss_USD_Bn_Reported')}bn reported / ~USD {r.get('Economic_Loss_USD_Bn_Today_Approx')}bn today<br><b>Insured loss:</b> USD {r.get('Insured_Loss_USD_Bn_Reported')}bn reported / ~USD {r.get('Insured_Loss_USD_Bn_Today_Approx')}bn today<br><b>Fatalities:</b> {int(r.get('Fatalities')) if pd.notna(r.get('Fatalities')) else 'Unknown'}<br><b>Status:</b> Starter estimate; verify before formal use.</div></div>""",unsafe_allow_html=True)
def make_map(df):
    m=df.dropna(subset=["Latitude","Longitude"]).copy()
    if m.empty: st.info("No coordinates available."); return
    m["lat"]=pd.to_numeric(m["Latitude"],errors="coerce"); m["lon"]=pd.to_numeric(m["Longitude"],errors="coerce"); m=m.dropna(subset=["lat","lon"])
    layer=pdk.Layer("ScatterplotLayer",data=m,get_position="[lon, lat]",get_radius=70000,get_fill_color="Map_Color",pickable=True,auto_highlight=True)
    view=pdk.ViewState(latitude=m["lat"].mean(),longitude=m["lon"].mean(),zoom=1,pitch=0)
    tooltip={"html":"<b>{Event_Name}</b><br/>Severity: {Severity}<br/>Priority: {Notification_Tier}<br/>Country: {Country}<br/>Source: {Source_Name}","style":{"backgroundColor":"#0f172a","color":"white"}}
    st.pydeck_chart(pdk.Deck(layers=[layer],initial_view_state=view,tooltip=tooltip),use_container_width=True)
def vendor_df(event):
    vendors=[("Moody's RMS","Model vendor","Event response, modeled insured loss, hazard footprint","Public + licensed","High"),("Verisk Extreme Event Solutions / PCS","Model vendor / industry loss","Modeled insured loss estimate, PCS catastrophe info","Public + licensed","High"),("KCC","Model vendor","Flash estimate, modeled insured loss, event commentary","Often public summary","High"),("CoreLogic / Cotality","Property analytics","Property impact, exposure, hazard insights","Public + platform","Medium"),("PERILS","Industry loss authority","Industry loss index / loss updates","Mostly licensed","High"),("Aon","Broker / market report","Cat recap, loss commentary","Public reports","Medium"),("Gallagher Re","Broker / market report","Event commentary, loss ranges","Public reports","Medium"),("Swiss Re","Reinsurer","Insured/economic loss commentary","Public summaries","Medium"),("Munich Re","Reinsurer / NatCat","NatCat commentary and historical comparison","Public summaries","Medium")]
    return pd.DataFrame([{"Priority":p,"Source":s,"Category":c,"Check":ch,"Access":a,"Link":"https://www.google.com/search?q="+quote_plus(f'"{event.get("Event_Name")}" {s} insured loss catastrophe model estimate event response')} for s,c,ch,a,p in vendors])
def mgmt(event):
    return f"""MANAGEMENT UPDATE – {event.get('Event_Name')}

Priority: {tier_label(event.get('Notification_Tier'))}
Peril: {event.get('Peril')}
Severity: {event.get('Severity')}
Country / area: {event.get('Country')}
Latest update: {event.get('Latest_Update_Date')}
Source: {event.get('Source_Name')}

Executive view:
{event.get('Management_Summary')}

Why it matters:
{event.get('Why_It_Matters')}

Hazard:
{event.get('Physical_Intensity')}

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

Source:
{event.get('Source_Link')}"""

def app():
    css()
    refresh_count=st_autorefresh(interval=5*60*1000,key="catwatch_v5_refresh")
    st.markdown('<div class="hero"><div class="title">🌍 CatWatch Mobile</div><div class="sub">Live catastrophe triage for phone: events, verified news, vendor/loss watch, historical analogues and ad-hoc management updates.</div></div>',unsafe_allow_html=True)
    df=load_events()
    if df.empty: st.error("No event data loaded."); return
    with st.expander("Filters",expanded=False):
        tiers=st.multiselect("Priority",["P1","P2","P3","P4"],default=["P1","P2","P3","P4"])
        p=st.selectbox("Peril",["All"]+sorted(df["Peril"].dropna().unique()))
        s=st.selectbox("Severity",["All"]+sorted(df["Severity"].dropna().unique(),key=sev_rank,reverse=True))
        countries=["All"]+df["Country"].fillna("Unknown").astype(str).value_counts().index.tolist()
        c=st.selectbox("Country / area",countries)
        q=st.text_input("Search event / place",placeholder="Search event, country, region...")
    f=df.copy()
    if tiers: f=f[f["Notification_Tier"].isin(tiers)]
    if p!="All": f=f[f["Peril"]==p]
    if s!="All": f=f[f["Severity"]==s]
    if c!="All": f=f[f["Country"]==c]
    if q.strip(): f=f[f.apply(lambda r:q.lower().strip() in " ".join(r.astype(str)).lower(),axis=1)]
    a,b,d=st.columns(3); a.metric("Events",len(f)); b.metric("P1/P2",int(f["Notification_Tier"].isin(["P1","P2"]).sum()) if not f.empty else 0); d.metric("UTC",now_txt().split()[1])
    if st.button("Refresh now"): st.cache_data.clear(); st.rerun()
    st.caption(f"Auto-refresh: every 5 minutes while open. Session refresh count: {refresh_count}")
    event=None
    if not f.empty:
        name=st.selectbox("Open event",f["Event_Name"].tolist())
        event=f[f["Event_Name"]==name].iloc[0]
    tabs=st.tabs(["Home","Detail","Map","News","Vendor","Loss","History","Mgmt"])
    with tabs[0]:
        st.markdown('<div class="section">Priority queue</div>',unsafe_allow_html=True)
        show=f[f["Notification_Tier"].isin(["P1","P2"])] if not f.empty else f
        if show.empty: show=f
        if show.empty: st.info("No events match filters.")
        for _,r in show.head(10).iterrows(): card(r)
    with tabs[1]:
        st.markdown('<div class="section">Event detail</div>',unsafe_allow_html=True)
        if event is not None:
            st.markdown(html_badges(event),unsafe_allow_html=True); st.markdown(f"### {event['Event_Name']}")
            x,y=st.columns(2); x.metric("Priority",event["Notification_Tier"]); y.metric("Severity",event["Severity"])
            st.markdown(f"<div class='summary'>{event['Management_Summary']}</div>",unsafe_allow_html=True)
            st.write(f"**Why it matters:** {event['Why_It_Matters']}")
            st.write(f"**Country / area:** {event['Country']}")
            st.write(f"**Location:** {event['Location_Label']}")
            st.write(f"**Hazard:** {event['Physical_Intensity']}")
            st.write(f"**Human impact:** {event['Human_Impact']}")
            st.write(f"**Loss status:** {event['Industry_Loss_Status']}")
            st.write(f"**Confidence:** {event['Confidence_Level']}")
            st.write(f"**Next update:** {event['Next_Update']}")
            st.write(f"**Source:** [{event['Source_Name']}]({event['Source_Link']})")
    with tabs[2]:
        st.markdown('<div class="section">Map & path</div>',unsafe_allow_html=True)
        if event is not None:
            st.write(f"**Path / footprint status:** {event['Track_Info']}")
            make_map(pd.DataFrame([event]))
            st.info("Next mapping upgrade: cyclone forecast tracks, wildfire perimeters, flood extents, earthquake shakemaps and Copernicus EMS footprints.")
    with tabs[3]:
        st.markdown('<div class="section">Latest verified news</div>',unsafe_allow_html=True)
        if event is not None:
            st.caption("News is pulled from Google News RSS and filtered to major/verified brands where possible. Verify figures before formal updates.")
            nd=fetch_news(event["Event_Name"],event["Country"],event["Peril"])
            if nd.empty: st.info("No verified news items found for this event yet.")
            for _,r in nd.iterrows(): news_card(r)
    with tabs[4]:
        st.markdown('<div class="section">Vendor model watch</div>',unsafe_allow_html=True)
        if event is not None:
            st.markdown("<div class='summary'>Check public and licensed vendor/model sources for event response, modeled loss and industry-loss updates. Do not scrape or redistribute paywalled content.</div>",unsafe_allow_html=True)
            for _,r in vendor_df(event).iterrows():
                st.markdown(f"<div class='card'><span class='badge tier-P3'>{r.Priority}</span><div class='et'>{r.Source}</div><div class='meta'><b>Category:</b> {r.Category}<br><b>Check:</b> {r.Check}<br><b>Access:</b> {r.Access}<br><a href='{r.Link}' target='_blank'>Search public update</a></div></div>",unsafe_allow_html=True)
    with tabs[5]:
        st.markdown('<div class="section">Loss watch</div>',unsafe_allow_html=True)
        st.markdown("<div class='warn'>Separate confirmed hazard facts from loss estimates. Early loss numbers may be preliminary, paywalled or absent.</div>",unsafe_allow_html=True)
        cols=["Notification_Tier","Severity","Peril","Country","Event_Name","Economic_Loss","Insured_Loss","Industry_Loss_Status","Confidence_Level","Source_Name"]
        st.dataframe(f[cols],use_container_width=True,hide_index=True)
    with tabs[6]:
        st.markdown('<div class="section">Historical events</div>',unsafe_allow_html=True)
        h=load_history()
        with st.expander("Historical filters",expanded=True):
            hc=st.selectbox("Country",["All"]+sorted(h["Country"].dropna().unique()),key="hc")
            hp=st.selectbox("Peril",["All"]+sorted(h["Peril"].dropna().unique()),key="hp")
            hq=st.text_input("Search by event name",placeholder="Katrina, Tohoku, Ian...",key="hq")
        hh=h.copy()
        if hc!="All": hh=hh[hh["Country"]==hc]
        if hp!="All": hh=hh[hh["Peril"]==hp]
        if hq.strip(): hh=hh[hh["Event_Name"].str.lower().str.contains(hq.lower().strip(),na=False)]
        st.caption("Starter global history dataset. Values are approximate USD bn and should be verified before formal use. Replace/extend with EM-DAT, NOAA, PERILS and licensed sources.")
        for _,r in hh.sort_values("Year",ascending=False).head(50).iterrows(): hist_card(r)
        st.download_button("Download historical starter table",h.to_csv(index=False).encode(),"catwatch_historical_events_starter.csv","text/csv")
    with tabs[7]:
        st.markdown('<div class="section">Ad-hoc management overview</div>',unsafe_allow_html=True)
        if event is not None:
            summary=mgmt(event)+"\n\nVendor/loss caveat:\nNo verified public vendor model or industry loss estimate has been captured in CatWatch unless shown in Vendor/Loss tabs. Any loss number should be labelled by source, date, confidence and access status."
            st.text_area("Management update draft",summary,height=420)
            st.download_button("Download management update",summary.encode(),"catwatch_management_update.txt","text/plain")
if __name__=="__main__": app()
