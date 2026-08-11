from __future__ import annotations
import csv, io, json, re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUT=Path(__file__).resolve().parents[1]/'data/dashboard.json'
def load_previous_data():
    if not OUT.exists():
        return {}

    try:
        return json.loads(
            OUT.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}


PREVIOUS_DATA = load_previous_data()
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

def brent_oil():
    url = (
        "https://raw.githubusercontent.com/"
        "datasets/oil-prices/main/data/brent-daily.csv"
    )

    response = S.get(
        url,
        timeout=(20, 60)
    )

    response.raise_for_status()

    rows = []

    for row in csv.DictReader(
        io.StringIO(response.text)
    ):
        try:
            datum = row["Date"]
            ar_szoveg = row["Price"]

            if (
                not datum
                or not ar_szoveg
                or ar_szoveg.strip() == "."
            ):
                continue

            # A dashboardon 2000-től jelenítjük meg az adatokat.
            if datum < "2000-01-01":
                continue

            rows.append({
                "date": datum,
                "value": float(ar_szoveg)
            })

        except (ValueError, KeyError, TypeError):
            continue

    if not rows:
        raise RuntimeError(
            "A Brent CSV nem tartalmaz feldolgozható adatot."
        )

    return sorted(
        rows,
        key=lambda x: x["date"]
    )


def ecb_fx():
    url = "https://data-api.ecb.europa.eu/service/data/EXR/D.HUF+USD+GBP.EUR.SP00.A"
    response = S.get(
        url,
        params={"format": "csvdata", "startPeriod": "2000-01-01"},
        headers={"Accept": "text/csv"},
        timeout=90,
    )
    response.raise_for_status()

    raw = []
    for row in csv.DictReader(io.StringIO(response.text)):
        try:
            raw.append({
                "date": row["TIME_PERIOD"],
                "currency": row["CURRENCY"],
                "value": float(row["OBS_VALUE"]),
            })
        except (KeyError, TypeError, ValueError):
            continue

    by_date = {}
    for row in raw:
        by_date.setdefault(row["date"], {})[row["currency"]] = row["value"]

    eurhuf, usdhuf, gbphuf = [], [], []
    for date, rates in sorted(by_date.items()):
        huf = rates.get("HUF")
        usd = rates.get("USD")
        gbp = rates.get("GBP")
        if huf is not None:
            eurhuf.append({"date": date, "value": huf})
        if huf is not None and usd not in (None, 0):
            usdhuf.append({"date": date, "value": huf / usd})
        if huf is not None and gbp not in (None, 0):
            gbphuf.append({"date": date, "value": huf / gbp})

    return {"eurhuf": eurhuf, "usdhuf": usdhuf, "gbphuf": gbphuf}


def ksh_earnings():
    urls = [
        "https://www.ksh.hu/stadat_files/mun/hu/mun0143.csv",
        "https://ksh.hu/stadat_files/mun/hu/mun0143.csv",
    ]

    content = None
    last_error = None

    for url in urls:
        try:
            print(f"KSH átlagkereset lekérése: {url}")

            response = requests.get(
    url,
    headers={
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/127.0 Safari/537.36"
        ),
        "Accept": (
            "text/csv,text/plain,"
            "application/octet-stream,*/*"
        ),
    },
    timeout=(10, 30),
)

            response.raise_for_status()

            if not response.content:
                raise RuntimeError(
                    "A KSH üres választ adott vissza."
                )

            content = response.content

            print(
                "KSH átlagkereset sikeresen letöltve: "
                f"{len(content)} bájt"
            )

            break

        except requests.RequestException as error:
            last_error = error

            print(
                "A KSH-forrás nem volt elérhető: "
                f"{url}; hiba: {error}"
            )

        if content is None:
        previous_earnings = PREVIOUS_DATA.get(
            "earnings"
        )

        # Az új JSON-szerkezet már gross, median és net
        # adatsorokat tartalmaz.
        if isinstance(previous_earnings, dict):
            gross = previous_earnings.get("gross", [])
            median = previous_earnings.get("median", [])
            net = previous_earnings.get("net", [])

            if gross or median or net:
                print(
                    "FIGYELMEZTETÉS: a KSH nem volt elérhető. "
                    "A korábbi átlagkereseti adatok maradnak érvényben."
                )

                return {
                    "gross": gross,
                    "median": median,
                    "net": net,
                }

        # A korábbi dashboard-verzióban az earnings még
        # egyszerű lista lehetett, amely a bruttó keresetet
        # tartalmazta.
        if isinstance(previous_earnings, list):
            print(
                "FIGYELMEZTETÉS: a KSH nem volt elérhető. "
                "A régi bruttó átlagkereseti idősor kerül megtartásra."
            )

            return {
                "gross": previous_earnings,
                "median": [],
                "net": [],
            }

        # Első futáskor vagy korábbi kereseti adatok hiányában
        # nem állítjuk le az egész dashboard frissítését.
        print(
            "FIGYELMEZTETÉS: a KSH nem volt elérhető, "
            "és nincs korábbi kereseti adat. "
            "A kereseti adatsorok átmenetileg üresek maradnak. "
            f"Utolsó hiba: {last_error}"
        )

        return {
            "gross": [],
            "median": [],
            "net": [],
        }

    try:
        decoded_content = content.decode("cp1250")
        
    except UnicodeDecodeError:
        decoded_content = content.decode(
            "utf-8-sig"
        )

    rows = list(
        csv.reader(
            io.StringIO(decoded_content),
            delimiter=";",
        )
    )

    months = {
        "január": 1,
        "február": 2,
        "március": 3,
        "április": 4,
        "május": 5,
        "június": 6,
        "július": 7,
        "augusztus": 8,
        "szeptember": 9,
        "október": 10,
        "november": 11,
        "december": 12,
    }

    result = {
        "gross": [],
        "median": [],
        "net": [],
    }

    year = None

    def number(value):
        if value is None:
            return None

        cleaned = (
            str(value)
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
            .strip()
        )

        if cleaned == "":
            return None

        return float(cleaned)

    for row in rows:
        if len(row) < 8:
            continue

        year_match = re.search(
            r"(20\d{2})",
            row[0] or "",
        )

        if year_match:
            year = int(
                year_match.group(1)
            )

        month_name = (
            row[1] or ""
        ).strip().lower()

        month = months.get(
            month_name
        )

        if not year or not month:
            continue

        try:
            gross = number(row[2])
            median = number(row[4])
            net = number(row[6])

        except (
            ValueError,
            TypeError,
            IndexError,
        ):
            continue

        if (
            gross is None
            or median is None
            or net is None
        ):
            continue

        if not 100000 <= gross <= 2000000:
            continue

        date = (
            f"{year}-"
            f"{month:02d}-01"
        )

        result["gross"].append(
            {
                "date": date,
                "value": gross,
            }
        )

        result["median"].append(
            {
                "date": date,
                "value": median,
            }
        )

        result["net"].append(
            {
                "date": date,
                "value": net,
            }
        )

        if not result["gross"]:
        previous_earnings = PREVIOUS_DATA.get(
            "earnings"
        )

        if isinstance(previous_earnings, dict):
            gross = previous_earnings.get("gross", [])
            median = previous_earnings.get("median", [])
            net = previous_earnings.get("net", [])

            if gross or median or net:
                print(
                    "FIGYELMEZTETÉS: a KSH-fájl letöltődött, "
                    "de nem volt feldolgozható. "
                    "A korábbi kereseti adatok maradnak érvényben."
                )

                return {
                    "gross": gross,
                    "median": median,
                    "net": net,
                }

        if isinstance(previous_earnings, list):
            print(
                "FIGYELMEZTETÉS: a KSH-fájl nem volt "
                "feldolgozható. A korábbi bruttó idősor "
                "kerül megtartásra."
            )

            return {
                "gross": previous_earnings,
                "median": [],
                "net": [],
            }

        print(
            "FIGYELMEZTETÉS: a KSH-fájl nem tartalmazott "
            "feldolgozható havi kereseti adatokat. "
            "A kereseti sorozatok üresek maradnak."
        )

        return {
            "gross": [],
            "median": [],
            "net": [],
        }

    print(
        "KSH átlagkereseti sorok száma: "
        f"{len(result['gross'])}"
    )

    return result
    
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

fx_data = ecb_fx()

data={
 'updated_at':datetime.now(timezone.utc).isoformat(),
 'inflation':eurostat('prc_hicp_minr',{'geo':'HU','coicop18':'TOTAL','unit':'RCH_A'}),
 'eurhuf': fx_data['eurhuf'],
 'fx': fx_data,
 'brent': brent_oil(),
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
