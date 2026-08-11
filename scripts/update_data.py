from __future__ import annotations
import csv, io, json, re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUT=Path(__file__).resolve().parents[1]/'data/dashboard.json'
S = requests.Session()

S.headers.update({
    "User-Agent": "Mozilla/5.0 magyar-gazdasagi-monitor/1.0",
    "Accept": "*/*"
})

RetryStrategia = Retry(
    total=5,
    connect=5,
    read=5,
    backoff_factor=5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

HTTPAdapterRetry =  HTTPAdapter(
        max_retries=RetryStrategia
    )

S.mount(
    "https://",
    HTTPAdapterRetry
)

S.mount(
    "http://",
    HTTPAdapterRetry
)

def eurostat(dataset, filters):
    url=f'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}'
    j=S.get(url,params={'lang':'EN',**filters},timeout=90).json()
    idx=j['dimension']['time']['category']['index']; vals=j.get('value',{})
    out=[]
    for t,p in idx.items():
        v=vals[p] if isinstance(vals,list) and p<len(vals) else vals.get(str(p)) if isinstance(vals,dict) else None
        if v is not None: out.append({'date':period_date(t),'value':float(v)})
    return sorted(out,key=lambda x:x['date'])

def period_date(t):
    if '-Q' in t:
        y,q=t.split('-Q'); return f'{y}-{int(q)*3:02d}-01'
    return t+'-01' if len(t)==7 else t

def fred(series):
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    response = S.get(
        url,
        params={
            "id": series,
            "cosd": "2000-01-01"
        },
        timeout=(20, 180)
    )

    response.raise_for_status()

    rows = []

    for row in csv.DictReader(
        io.StringIO(response.text)
    ):
        try:
            datum = row["observation_date"]
            ertek_szoveg = row.get(series)

            if (
                ertek_szoveg is None
                or ertek_szoveg.strip() == ""
                or ertek_szoveg.strip() == "."
            ):
                continue

            rows.append({
                "date": datum,
                "value": float(ertek_szoveg)
            })

        except (ValueError, KeyError, TypeError):
            continue

    if not rows:
        raise RuntimeError(
            f"A FRED nem adott vissza feldolgozható adatot: {series}"
        )

    return sorted(
        rows,
        key=lambda x: x["date"]
    )

def ecb_fx():
    url='https://data-api.ecb.europa.eu/service/data/EXR/D.HUF.EUR.SP00.A'
    text=S.get(url,params={'format':'csvdata','startPeriod':'2000-01-01'},headers={'Accept':'text/csv'},timeout=90).text
    rows=[]
    for r in csv.DictReader(io.StringIO(text)):
        try: rows.append({'date':r['TIME_PERIOD'],'value':float(r['OBS_VALUE'])})
        except: pass
    return sorted(rows,key=lambda x:x['date'])

def ksh_earnings():
    b=S.get('https://www.ksh.hu/stadat_files/mun/hu/mun0143.csv',timeout=90).content
    rows=list(csv.reader(io.StringIO(b.decode('cp1250')),delimiter=';'))
    out=[]; year=None
    months={'január':1,'február':2,'március':3,'április':4,'május':5,'június':6,'július':7,'augusztus':8,'szeptember':9,'október':10,'november':11,'december':12}
    for r in rows:
        if len(r)<4: continue
        m=re.search(r'(20\d{2})',r[0] or '')
        if m: year=int(m.group(1))
        month=months.get((r[1] or '').strip().lower())
        try: value=float(r[2].replace('\xa0','').replace(' ', '').replace(',','.'))
        except: continue
        if year and month and 100000<=value<=2000000: out.append({'date':f'{year}-{month:02d}-01','value':value})
    return out

def mnb_rate():
    url='https://www.mnb.hu/en/Jegybanki_alapkamat_alakulasa'
    tables=pd.read_html(S.get(url,timeout=90).text)
    out=[]
    for t in tables:
        if t.shape[1]<2: continue
        for _,r in t.iloc[:,:2].iterrows():
            dt=pd.to_datetime(str(r.iloc[0]),errors='coerce',dayfirst=True)
            m=re.search(r'-?\d+(?:[.,]\d+)?',str(r.iloc[1]))
            if pd.notna(dt) and m: out.append({'date':dt.strftime('%Y-%m-%d'),'value':float(m.group().replace(',','.'))})
    return sorted({x['date']:x for x in out}.values(),key=lambda x:x['date'])

def daily_steps(events):
    if not events:return []
    s=pd.Series({pd.Timestamp(x['date']):x['value'] for x in events}).sort_index()
    idx=pd.date_range(s.index.min(),pd.Timestamp.now().normalize(),freq='D')
    return [{'date':d.strftime('%Y-%m-%d'),'value':float(v)} for d,v in s.reindex(idx).ffill().items()]

data={
 'updated_at':datetime.now(timezone.utc).isoformat(),
 'inflation':eurostat('prc_hicp_minr',{'geo':'HU','coicop18':'TOTAL','unit':'RCH_A'}),
 'eurhuf':ecb_fx(),
 'brent':fred('DCOILBRENTEU'),
 'unemployment':eurostat('une_rt_m',{'geo':'HU','sex':'T','age':'TOTAL','unit':'PC_ACT','s_adj':'SA'}),
 'employment':eurostat('lfsi_emp_q',{'geo':'HU','indic_em':'EMP_LFS','sex':'T','age':'Y15-64','unit':'PC_POP','s_adj':'SA'}),
 'gdp':eurostat('namq_10_gdp',{'geo':'HU','na_item':'B1GQ','unit':'CLV_PCH_SM','s_adj':'NSA'}),
 'earnings':ksh_earnings(),
 'base_rate':mnb_rate(),
 'debt':eurostat('gov_10q_ggdebt',{'geo':'HU','na_item':'GD','sector':'S13','unit':'PC_GDP'}),
 'current_account':eurostat('teibp050',{'geo':'HU','currency':'MIO_EUR','s_adj':'NSA','sector10':'S1','sectpart':'S1','stk_flow':'BAL','partner':'WRL_REST','bop_item':'CA'})
}
data['base_rate_daily']=daily_steps(data['base_rate'])
OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Wrote',OUT)
