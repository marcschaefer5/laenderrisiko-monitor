"""
aktualisieren.py -- taeglicher Lauf des Laenderrisiko-Monitors.

WAS DER LAUF TUT
  1. GDELT der letzten Tage nachladen, sofort auf Land-Tag verdichten und die
     Rohdateien verwerfen. Es wandert nie eine Parquet-Datei ins Repository --
     der vollstaendige Speicher hat 2,1 GB, die abgeleiteten Aggregate wenige
     hundert Kilobyte.
  2. Wechselkurse, Aktienindizes und den GPR aktualisieren.
  3. Risikoindex, Auffaelligkeiten und Kurzfristprognose neu rechnen.
  4. dashboard_data.json und die Auffaelligkeitshistorie schreiben.
  5. Neue Auffaelligkeiten in benachrichtigung.json ablegen, damit der
     Workflow daraus eine E-Mail bauen kann.

WAS DER RISIKOINDEX IST -- UND WAS NICHT
Der Index besteht aus Waehrungsdruck, Marktvolatilitaet und geopolitischer
Spannung. Er enthaelt KEINE GDELT-Merkmale: in 47 geprueften Konstellationen
war kein Prognosebeitrag von GDELT nachweisbar. GDELT liefert im Monitor den
Nachrichtenkontext, nicht die Vorhersage. Neue Laender bekommen deshalb sofort
die volle Risikohistorie; nur ihr Nachrichten-Feed fuellt sich ab dem ersten
Lauf.

Aufruf:  python3 skripte/aktualisieren.py [--voll]
         --voll erzwingt einen vollstaendigen Neuaufbau der Marktreihen.
"""
from __future__ import annotations
import argparse, io, json, re, sys, time, zipfile
import datetime as dt
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse, quote
import urllib.request

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (LAENDER, GPR_URL, GDELT_MASTER, ESKALATION, VOL_FENSTER,
                    NORM_FENSTER, PROGNOSE_HORIZONT, PROGNOSE_SCHWELLE,
                    AUFF_BEWEGUNG, AUFF_NIVEAU, TAGE_ANZEIGE, NEWS_TAGE,
                    NACHLAUF_TAGE)

WURZEL = Path(__file__).resolve().parent.parent
DATEN, DOCS = WURZEL / "daten", WURZEL / "docs"
DATEN.mkdir(exist_ok=True); DOCS.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64)"
KEEP = ["C1", "C28", "C30", "C34", "C60"]
TARGET = set(LAENDER)


def log(m): print(m, flush=True)


def holen(url: str, versuche: int = 3, timeout: int = 90) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(versuche):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == versuche - 1:
                return None
            time.sleep(2 * (i + 1))
    return None


# ---------------------------------------------------------------- GDELT
def geo_indizes(n: int) -> tuple[int, int, int]:
    """Geo-CountryCodes positionsbasiert vom rechten Rand -- wie in D2/D24."""
    return (n - 24 + 2, n - 16 + 2, n - 8 + 2)


def slug_zu_titel(url: str) -> str | None:
    try:
        pfad = urlparse(url).path
    except Exception:
        return None
    teile = [t for t in pfad.strip("/").split("/") if t]
    if not teile:
        return None
    s = re.sub(r"\.(html?|php|aspx?)$", "", teile[-1])
    s = re.sub(r"-?\d{4}-\d{2}-\d{2}-?$", "", s)
    s = re.sub(r"-?id\d+$|-?\d{6,}$", "", s)
    w = [x for x in s.split("-") if x and not x.isdigit()]
    if len(w) < 4:
        return None
    t = " ".join(w).strip()
    return t[:1].upper() + t[1:]


def gdelt_nachladen(tage: int) -> tuple[pd.DataFrame, dict]:
    """Laedt die juengsten GDELT-Tage, verdichtet sie und verwirft die Rohdaten."""
    master = holen(GDELT_MASTER, timeout=180)
    if master is None:
        log("[WARN] Masterliste nicht erreichbar -- GDELT-Schritt uebersprungen")
        return pd.DataFrame(), {}
    pat = re.compile(r"(\S+/(\d{14})\.export\.CSV\.zip)")
    nach_tag = defaultdict(list)
    for zeile in master.decode(errors="ignore").splitlines():
        m = pat.search(zeile)
        if m:
            nach_tag[m.group(2)[:8]].append(m.group(1))
    letzte = sorted(nach_tag)[-tage:]
    log(f"      GDELT-Tage: {', '.join(letzte)}")

    agg, news = [], defaultdict(dict)
    for tag in letzte:
        urls = sorted(set(nach_tag[tag]))
        with ThreadPoolExecutor(max_workers=6) as ex:
            rohe = list(ex.map(holen, urls))
        teile = []
        for roh in rohe:
            if roh is None:
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(roh)) as zf:
                    name = next((m for m in zf.namelist() if m.lower().endswith(".csv")), None)
                    if not name:
                        continue
                    with zf.open(name) as f:
                        for chunk in pd.read_csv(f, sep="\t", header=None, dtype=str,
                                                 chunksize=200_000, low_memory=False,
                                                 on_bad_lines="skip"):
                            n = chunk.shape[1]
                            if n < 26:
                                continue
                            chunk.columns = [f"C{i}" for i in range(n)]
                            a1, a2, ac = geo_indizes(n)
                            g = chunk.iloc[:, [a1, a2, ac]].fillna("").astype(str)
                            treffer = g.isin(TARGET).any(axis=1)
                            if not treffer.any():
                                continue
                            sub = chunk.loc[treffer, KEEP].copy()
                            sub["G1"], sub["G2"], sub["G3"] = (g.loc[treffer].iloc[:, 0],
                                                               g.loc[treffer].iloc[:, 1],
                                                               g.loc[treffer].iloc[:, 2])
                            teile.append(sub)
            except Exception:
                continue
        if not teile:
            continue
        d = pd.concat(teile, ignore_index=True)
        d["date"] = pd.to_datetime(d.C1, format="%Y%m%d", errors="coerce")
        d["root"] = pd.to_numeric(d.C28, errors="coerce")
        d["gold"] = pd.to_numeric(d.C30, errors="coerce")
        d["tone"] = pd.to_numeric(d.C34, errors="coerce")
        d = d.dropna(subset=["date"])
        geo = d[["G1", "G2", "G3"]]
        for code in LAENDER:
            t = d.loc[geo.eq(code).any(axis=1)]
            if t.empty:
                continue
            g = t.groupby("date").agg(n_events=("root", "size"),
                                      tone_sum=("tone", "sum"),
                                      tone_cnt=("tone", lambda s: s.notna().sum()))
            for rc, nm in ESKALATION.items():
                g[f"n_{rc}"] = t[t.root == rc].groupby("date").size()
            g = g.fillna(0).reset_index()
            g["code"] = code
            agg.append(g)
            # Nachrichten: staerkster Konfliktbezug des Tages
            eintraege, gesehen = [], set()
            for _, r in t.nsmallest(60, "gold").iterrows():
                titel = slug_zu_titel(str(r.C60))
                if not titel or titel.lower() in gesehen:
                    continue
                gesehen.add(titel.lower())
                eintraege.append({"titel": titel, "url": str(r.C60),
                                  "gold": round(float(r.gold), 1)})
                if len(eintraege) >= 5:
                    break
            if eintraege:
                news[code][tag] = eintraege
        log(f"      {tag}: {len(d):,} Zeilen verdichtet")
    return (pd.concat(agg, ignore_index=True) if agg else pd.DataFrame()), dict(news)


# ---------------------------------------------------------------- Marktdaten
def yahoo(symbol: str) -> pd.DataFrame | None:
    roh = holen(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
                f"?period1=1640995200&period2=9999999999&interval=1d", timeout=60)
    if roh is None:
        return None
    try:
        r = json.loads(roh)["chart"]["result"][0]
        if "timestamp" not in r:
            return None
        return pd.DataFrame({"date": pd.to_datetime(r["timestamp"], unit="s").normalize(),
                             "close": r["indicators"]["quote"][0]["close"]}).dropna()
    except Exception:
        return None


def marktdaten(voll: bool) -> None:
    for code, (name, fx, ak) in LAENDER.items():
        for art, sym in (("fx", fx), ("aktien", ak)):
            if not sym:
                continue
            ziel = DATEN / f"{art}_{code}.csv"
            if ziel.exists() and not voll:
                alt = pd.read_csv(ziel, sep=";", parse_dates=["date"])
                if (dt.date.today() - alt.date.max().date()).days < 1:
                    continue
            df = yahoo(sym)
            if df is None or df.empty:
                log(f"      [WARN] {name} {art} ({sym}) nicht abrufbar")
                continue
            df.to_csv(ziel, index=False, sep=";")
            time.sleep(0.3)
    roh = holen(GPR_URL, timeout=120)
    if roh:
        (DATEN / "gpr.xls").write_bytes(roh)


# ---------------------------------------------------------------- Auswertung
def risikoreihe(code: str, gpr: pd.DataFrame) -> pd.DataFrame | None:
    teile = []
    f = DATEN / f"fx_{code}.csv"
    if f.exists():
        fx = pd.read_csv(f, sep=";", parse_dates=["date"]).sort_values("date")
        r = np.log(fx.close).diff()
        fx["v"] = r.rolling(VOL_FENSTER).std(ddof=0) * np.sqrt(252)
        fx["a"] = np.log(fx.close).diff(VOL_FENSTER)
        za = ((fx.v - fx.v.mean()) / fx.v.std() + (fx.a - fx.a.mean()) / fx.a.std()) / 2
        teile.append(pd.DataFrame({"date": fx.date, "waehrung": za}))
    a = DATEN / f"aktien_{code}.csv"
    if a.exists():
        ak = pd.read_csv(a, sep=";", parse_dates=["date"]).sort_values("date")
        v = np.log(ak.close).diff().rolling(VOL_FENSTER).std(ddof=0) * np.sqrt(252)
        teile.append(pd.DataFrame({"date": ak.date, "markt": (v - v.mean()) / v.std()}))
    if not teile:
        return None
    d = teile[0]
    for t in teile[1:]:
        d = d.merge(t, on="date", how="outer")
    d = d.merge(gpr, on="date", how="left").sort_values("date")
    kats = [c for c in ["waehrung", "markt", "geopolitik"] if c in d.columns]
    d["risiko"] = d[kats].mean(axis=1, skipna=True)
    return d.dropna(subset=["risiko"]).reset_index(drop=True)


def prognose(d: pd.DataFrame) -> tuple[float | None, float | None]:
    d = d.copy()
    d["z_d1"] = d.z.diff(); d["r_d1"] = d.risiko.diff(); d["r_d5"] = d.risiko.diff(5)
    F = ["z", "z_d1", "r_d1", "r_d5"]
    dd = d.dropna(subset=F)
    y = (dd.z.shift(-PROGNOSE_HORIZONT) >= PROGNOSE_SCHWELLE).astype(float)
    train = dd.assign(y=y).dropna(subset=["y"])
    if len(train) < 400 or train.y.nunique() < 2:
        return None, None
    k = int(len(train) * 0.7)
    guete = None
    tr, te = train.iloc[:k], train.iloc[k:]
    if te.y.nunique() > 1:
        sc = StandardScaler().fit(tr[F])
        m = LogisticRegression(class_weight="balanced", max_iter=4000).fit(sc.transform(tr[F]), tr.y)
        guete = round(float(roc_auc_score(te.y, m.predict_proba(sc.transform(te[F]))[:, 1])), 3)
    sc = StandardScaler().fit(train[F])
    m = LogisticRegression(class_weight="balanced", max_iter=4000).fit(sc.transform(train[F]), train.y)
    return round(float(m.predict_proba(sc.transform(dd[F].tail(1)))[0, 1]), 3), guete


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voll", action="store_true")
    args = ap.parse_args()

    log("[1/4] GDELT nachladen und verdichten ...")
    neu_agg, neu_news = gdelt_nachladen(NACHLAUF_TAGE)
    pfad_agg, pfad_news = DATEN / "gdelt_tagesaggregate.csv", DATEN / "nachrichten.json"
    if not neu_agg.empty:
        alt = (pd.read_csv(pfad_agg, sep=";", parse_dates=["date"])
               if pfad_agg.exists() else pd.DataFrame())
        ges = pd.concat([alt, neu_agg], ignore_index=True)
        ges = ges.sort_values("date").drop_duplicates(["date", "code"], keep="last")
        ges.to_csv(pfad_agg, index=False, sep=";")
    news = json.loads(pfad_news.read_text()) if pfad_news.exists() else {}
    for code, tage in neu_news.items():
        news.setdefault(code, {}).update(tage)
    grenze = (dt.date.today() - dt.timedelta(days=NEWS_TAGE)).strftime("%Y%m%d")
    news = {c: {t: v for t, v in d.items() if t >= grenze} for c, d in news.items()}
    pfad_news.write_text(json.dumps(news, ensure_ascii=False))

    log("[2/4] Marktdaten aktualisieren ...")
    marktdaten(args.voll)

    log("[3/4] Risikoindex, Auffaelligkeiten, Prognose ...")
    gpr = pd.read_excel(DATEN / "gpr.xls")[["date", "GPRD"]].rename(columns={"GPRD": "gpr"})
    gpr["date"] = pd.to_datetime(gpr.date)
    gpr["geopolitik"] = (gpr.gpr - gpr.gpr.mean()) / gpr.gpr.std()
    gpr = gpr[["date", "geopolitik"]]

    gd = (pd.read_csv(pfad_agg, sep=";", parse_dates=["date"])
          if pfad_agg.exists() else pd.DataFrame(columns=["date", "code"]))
    ausgabe, historie_neu = {"stand": None, "laender": {}}, []
    for code, (name, _, _) in LAENDER.items():
        d = risikoreihe(code, gpr)
        if d is None or len(d) < 300:
            log(f"      [WARN] {name}: zu wenig Daten")
            continue
        mu = d.risiko.rolling(NORM_FENSTER, min_periods=60).mean()
        sd = d.risiko.rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
        d["z"] = (d.risiko - mu) / sd
        bew = d.z.diff() / d.z.diff().rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
        d["auffaellig"] = ((bew.abs() > AUFF_BEWEGUNG) | (d.z > AUFF_NIVEAU)).astype(int)
        d = d.dropna(subset=["z"])
        if d.empty:
            continue
        prog, guete = prognose(d)

        g = gd[gd.code == code].copy() if len(gd) else pd.DataFrame()
        if len(g):
            g["tone_avg"] = np.where(g.tone_cnt > 0, g.tone_sum / g.tone_cnt, np.nan)
            d = d.merge(g[["date", "n_events", "tone_avg"]], on="date", how="left")
        else:
            d["n_events"], d["tone_avg"] = np.nan, np.nan

        z = d.tail(TAGE_ANZEIGE)
        kats = [c for c in ["waehrung", "markt", "geopolitik"] if c in z.columns]
        ausgabe["laender"][code] = {
            "name": name,
            "daten": [x.strftime("%Y-%m-%d") for x in z.date],
            "risiko": [None if pd.isna(v) else round(float(v), 3) for v in z.z],
            "kategorien": {k: [None if pd.isna(v) else round(float(v), 3) for v in z[k]] for k in kats},
            "n_events": [None if pd.isna(v) else int(v) for v in z.n_events],
            "tone_avg": [None if pd.isna(v) else round(float(v), 2) for v in z.tone_avg],
            "auffaellig": [int(v) for v in z.auffaellig],
            "prognose_7t": prog, "prognose_auc": guete,
            "stand_datum": z.date.iloc[-1].strftime("%Y-%m-%d"),
            "stand_z": round(float(z.z.iloc[-1]), 2),
            "nachrichten": news.get(code, {}),
        }
        # Auffaelligkeiten der letzten beiden Tage -> Historie und Meldung
        for _, r in z.tail(2).iterrows():
            if r.auffaellig == 1:
                historie_neu.append({"datum": r.date.strftime("%Y-%m-%d"), "code": code,
                                     "land": name, "z": round(float(r.z), 2)})

    if not ausgabe["laender"]:
        log("[FEHLER] Keine auswertbaren Laender."); return 1
    ausgabe["stand"] = max(v["stand_datum"] for v in ausgabe["laender"].values())

    log("[4/4] Schreiben ...")
    pfad_hist = DATEN / "auffaelligkeiten.json"
    hist = json.loads(pfad_hist.read_text()) if pfad_hist.exists() else []
    bekannt = {(h["datum"], h["code"]) for h in hist}
    frisch = [h for h in historie_neu if (h["datum"], h["code"]) not in bekannt]
    hist = sorted(hist + frisch, key=lambda h: (h["datum"], h["code"]), reverse=True)[:400]
    pfad_hist.write_text(json.dumps(hist, ensure_ascii=False, indent=1))
    ausgabe["auffaelligkeiten"] = hist[:120]

    (DOCS / "dashboard_data.json").write_text(
        json.dumps(ausgabe, ensure_ascii=False, separators=(",", ":")))
    for f in frisch:
        f["nachrichten"] = list(news.get(f["code"], {}).get(
            f["datum"].replace("-", ""), []))[:3]
    (WURZEL / "benachrichtigung.json").write_text(
        json.dumps(frisch, ensure_ascii=False, indent=1))

    log(f"\nStand {ausgabe['stand']} | {len(ausgabe['laender'])} Länder"
        f" | {len(frisch)} neue Auffälligkeiten")
    for f in frisch:
        log(f"   ! {f['land']} {f['datum']} z={f['z']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
