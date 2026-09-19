"""
aktualisieren.py -- taeglicher Lauf des Laenderrisiko-Monitors.

WAS DER LAUF TUT
  1. GDELT der letzten Tage nachladen, sofort auf Land-Tag verdichten und die
     Rohdateien verwerfen. Es wandert nie eine Parquet-Datei ins Repository --
     der vollstaendige Speicher hat 2,1 GB, die abgeleiteten Aggregate wenige
     hundert Kilobyte.
  2. Wechselkurse, Aktienindizes und den GPR aktualisieren.
  3. Risikoindex, Lagemeldungen und -- nachrangig -- die Fortschreibung
     der Reihen neu rechnen.
  4. dashboard_data.json und die Auffaelligkeitshistorie schreiben.
  5. Neue Auffaelligkeiten in benachrichtigung.json ablegen, damit der
     Workflow daraus eine E-Mail bauen kann.

WOZU DER MONITOR DA IST
Der Monitor ist zuerst ein WARNWERKZEUG und erst danach ein Prognosewerkzeug.
Die erste Ebene sind Lagemeldungen (warnungen.py): datierte Aussagen darueber,
was gerade eingetreten ist -- ein Sprung im Index, ein anhaltend erhoehtes
Niveau, ein einzelner Baustein ausserhalb des Rahmens, eine laufende Episode
in den Ereignisdaten. Die zweite Ebene ist der Ausblick (ausblick.py): jede
Reihe wird aus ihrer eigenen Historie fortgeschrieben, zusaetzlich einmal
unter Einbezug der GDELT-Merkmale, und beides steht immer neben dem Fehler
der einfachsten Regel -- den letzten Wert beizubehalten. Diese Reihenfolge
folgt dem Befund der zugrunde liegenden Arbeit: die Gegenwart laesst sich aus
Ereignisdaten beschreiben, die naechsten Tage lassen sich daraus nicht
belastbar vorhersagen.

WAS DER RISIKOINDEX IST -- UND WAS NICHT
Der Index besteht aus vier Bausteinen: laenderspezifischer Ereignislage
(GDELT), Waehrungsdruck, Marktvolatilitaet und dem globalen geopolitischen
Umfeld (GPR). Gewichtung und Aggregation stehen in index_gewichte.py.

Die Ereignislage ist seit dieser Fassung Teil des Index, und das ist KEIN
Widerspruch zum Befund der zugrunde liegenden Arbeit. Dort war gezeigt, dass
aus Ereignisdaten kein PROGNOSEBEITRAG gegenueber einem Persistenz-Nullmodell
nachweisbar ist. Der Index ist aber eine ZUSTANDSGROESSE: er beschreibt, wie
die Lage heute gegenueber der eigenen Normallage aussieht. Genau das koennen
Ereignisdaten belegbar leisten -- die Episodenerkennung lebt davon. Die
Trennung ist im Code durchgezogen: Ereignismerkmale gehen in den Zustand ein
(index_gewichte.py) und bleiben aus der Fortschreibung heraus (ausblick.py),
wo weiterhin gegen die Beibehaltungsregel geprueft wird.

Neue Laender bekommen die Marktbausteine sofort mit voller Historie; ihre
Ereignislage und ihr Nachrichten-Feed fuellen sich ab dem ersten Lauf,
solange die GDELT-Historie nicht nachgeladen wurde (gdelt_historie.py).

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
from gdelt_merkmale import MERKMALE as G_MERKMALE, gdelt_merkmale
from krisen import krisen
from warnungen import warnungen, zusammenfassen
from ausblick import fortschreibung
from index_gewichte import (BAUSTEINE, ereignislage, gewichte_laden,
                            normieren, vollstaendig, zusammensetzen)
from gdelt_filter import zeilen_filtern, slug_erlaubt
from tagesgueltigkeit import bereinigen, kurse_bereinigen
import grundniveau as GN
from weltbank import profil
from config import (LAENDER, UEBERBLICK, WB_INDIKATOREN, GPR_URL, GDELT_MASTER, ESKALATION, VOL_FENSTER,
                    NORM_FENSTER, PROGNOSE_HORIZONT, PROGNOSE_SCHWELLE,
                    AUFF_BEWEGUNG, AUFF_NIVEAU, TAGE_ANZEIGE, NEWS_TAGE,
                    NACHLAUF_TAGE, FFILL_TAGE, MIN_BAUSTEIN_TAGE,
                    MAX_BAUSTEIN_ALTER)

WURZEL = Path(__file__).resolve().parent.parent
DATEN, DOCS = WURZEL / "daten", WURZEL / "docs"
DATEN.mkdir(exist_ok=True); DOCS.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64)"
# C7 / C17 sind Actor1CountryCode und Actor2CountryCode. Sie werden seit der
# Filterkorrektur mitgelesen (gdelt_filter.py) -- ohne sie laesst sich nicht
# unterscheiden, ob ein Ereignis das Land betrifft oder es nur erwaehnt.
KEEP_FEST = ["C1", "C7", "C17", "C28", "C30", "C34"]
# So viele Tage darf der Ereignisbaustein ohne neue Messung weitergefuehrt
# werden (siehe Begruendung an der Verwendungsstelle).
EREIGNIS_NACHLAUF = 3
# Mindestanteil der 96 Viertelstundendateien eines Tages, damit er uebernommen
# wird. Derselbe Wert wie in gdelt_historie.py -- beide Wege muessen gleich
# streng sein, sonst haengt das Niveau der Reihe davon ab, welcher Weg den Tag
# geladen hat.
MIN_ERNTE = 0.95
TARGET = set(LAENDER)


def log(m): print(m, flush=True)


def holen(url: str, versuche: int = 4, timeout: int = 90) -> bytes | None:
    """Laedt eine URL. Gibt None zurueck, wenn alle Versuche scheitern.

    Die Wartezeit waechst exponentiell statt linear (2, 4, 8 statt 2, 4, 6).
    Grund: die Ausfaelle treten gebuendelt auf, wenn viele Abrufe gleichzeitig
    laufen -- GDELT bremst dann. Linear wartend trifft der zweite Versuch
    dieselbe Bremse. Sichtbar wurde das daran, dass dieselben Tage bei
    verschiedenen Laeufen verschieden viele Ereignisse ergaben (bis Faktor
    neun), obwohl die Masterliste fuer jeden Tag 96 Dateien fuehrt.
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(versuche):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == versuche - 1:
                return None
            time.sleep(2 ** (i + 1))
    return None


# ---------------------------------------------------------------- GDELT
def geo_indizes(n: int) -> tuple[int, int, int]:
    """Geo-CountryCodes positionsbasiert vom rechten Rand -- wie in D2/D24.

    Von hinten gerechnet: die letzten beiden Felder sind DATEADDED und
    SOURCEURL, davor liegen drei Geo-Bloecke à 8 Feldern (Actor1Geo,
    Actor2Geo, ActionGeo). Der CountryCode ist jeweils das dritte Feld im
    Block, also Blockanfang + 2.

        dateadded = n - 2
        ActionGeo beginnt bei dateadded - 8   -> CountryCode = n - 8
        Actor2Geo beginnt bei dateadded - 16  -> CountryCode = n - 16
        Actor1Geo beginnt bei dateadded - 24  -> CountryCode = n - 24

    Bei n = 61 sind das 37, 45, 53 -- nachgemessen an einer echten Datei.
    In einer frueheren Fassung stand hier faelschlich "n - 24 + 2", weil das
    "+2" aus D2 uebernommen, das "- 2" fuer DATEADDED aber vergessen wurde.
    Die Indizes zeigten damit auf ADM2Code statt CountryCode. Dort stehen
    Werte wie "CA037" oder "18585", die nie einem Laendercode entsprechen --
    also kein Fehler, keine Ausnahme, sondern lautlos null Treffer.
    """
    return (n - 24, n - 16, n - 8)


def url_spalte(chunk: pd.DataFrame, n: int) -> str | None:
    """Findet die SOURCEURL-Spalte, statt sie auf C60 festzunageln.

    GDELT-Exportdateien enden mit DATEADDED und SOURCEURL. Die Spaltenzahl
    ist aber nicht garantiert konstant -- taucht auch nur eine Spalte mehr
    auf, ist C60 nicht mehr die URL, sondern das Datum. Genau das war der
    Grund, warum nachrichten.json leer blieb: die Aggregate stimmten, aber
    slug_zu_titel() bekam Zahlen statt Adressen und gab jedes Mal None
    zurueck. Deshalb wird die Spalte jetzt am Inhalt erkannt.
    """
    for i in range(n - 1, max(n - 6, -1), -1):
        sp = chunk[f"C{i}"].dropna().astype(str)
        if len(sp) and sp.str.startswith("http").mean() > 0.5:
            return f"C{i}"
    return None


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
    # Kennungen aussortieren. Viele Redaktionssysteme bauen die URL aus einer
    # UUID ("article_26410ca0-15b1-40bf-9df9-facb65c7a7ae"). Der Slug hat dann
    # genug Bestandteile, ergibt aber keinen Text. Kriterium: ueberwiegend
    # Wortteile ohne Vokal oder mit Ziffern darin -- so lesen sich Kennungen,
    # nicht Ueberschriften.
    def wortartig(x: str) -> bool:
        return x.isalpha() and any(v in x.lower() for v in "aeiouäöüy")
    if sum(wortartig(x) for x in w) < max(3, len(w) * 0.6):
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
        teile, fehler = [], []
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
                            us = url_spalte(chunk, n)
                            sub = chunk.loc[treffer, KEEP_FEST + ([us] if us else [])].copy()
                            if us:
                                sub = sub.rename(columns={us: "surl"})
                            else:
                                sub["surl"] = ""
                            sub["G1"], sub["G2"], sub["G3"] = (g.loc[treffer].iloc[:, 0],
                                                               g.loc[treffer].iloc[:, 1],
                                                               g.loc[treffer].iloc[:, 2])
                            teile.append(sub)
            except Exception as e:
                fehler.append(f"{type(e).__name__}: {e}")
                continue
        ok = sum(1 for r in rohe if r is not None)
        # Erntequote: Anteil der Viertelstundendateien, die wirklich ankamen.
        #
        # Ohne diese Pruefung schreibt der Lauf jeden Tag, egal wie wenig
        # angekommen ist -- und der Tag steht danach mit einer zu kleinen
        # Ereigniszahl im Bestand, deren Anteile verzerrt sind. Im Bestand
        # ergab derselbe Tag bei zwei Laeufen bis zum Neunfachen Unterschied.
        # Ein Tag unter MIN_QUOTE wird deshalb NICHT uebernommen; da der Lauf
        # die letzten NACHLAUF_TAGE Tage jedes Mal neu holt, kommt er am
        # naechsten Tag von selbst wieder dran.
        quote = ok / len(urls) if urls else 0.0
        if quote < MIN_ERNTE:
            log(f"      [WARN] {tag}: nur {ok}/{len(urls)} Dateien geladen "
                f"({quote*100:.0f} %) — Tag wird nicht übernommen, "
                f"er wird beim nächsten Lauf erneut geholt")
            continue
        if ok and not teile and not fehler:
            log(f"      [WARN] {tag}: {ok} Dateien gelesen, aber KEINE Zeile "
                f"traf ein Zielland -- Geo-Spalten pruefen "
                f"(skripte/diagnose_gdelt.py)")
        if fehler:
            log(f"      [WARN] {tag}: {len(fehler)} Datei(en) uebersprungen "
                f"-- erste Ursache: {fehler[0][:160]}")
        if not teile:
            log(f"      [WARN] {tag}: keine verwertbaren Zeilen "
                f"({ok}/{len(urls)} Dateien geladen)")
            continue
        d = pd.concat(teile, ignore_index=True)
        d["date"] = pd.to_datetime(d.C1, format="%Y%m%d", errors="coerce")
        d["root"] = pd.to_numeric(d.C28, errors="coerce")
        d["gold"] = pd.to_numeric(d.C30, errors="coerce")
        d["tone"] = pd.to_numeric(d.C34, errors="coerce")
        d = d.dropna(subset=["date"])

        # Nur Ereignisse aus dem geladenen Zeitfenster behalten.
        #
        # C1 (SQLDATE) ist das EREIGNISDATUM, nicht das Meldedatum. Eine Datei
        # von heute enthaelt regelmaessig Rueckblicke auf Ereignisse von 2016.
        # Ohne Filter wandern die in die Tagesaggregate und erzeugen dort
        # Einzeltage in laengst abgeschlossenen Zeitraeumen -- im Bestand
        # standen dadurch Brasilien und Aegypten mit je zwoelf Tagen, verstreut
        # ueber ein Jahr, statt mit einer zusammenhaengenden Reihe. Fuer den
        # taeglichen Nachlauf zaehlt nur, was in den geladenen Tagen passiert
        # ist; die Historie kommt aus der Erstbefuellung.
        fenster = pd.Timestamp(min(letzte)) - pd.Timedelta(days=1)
        vorher = len(d)
        d = d[d.date >= fenster]
        if vorher - len(d):
            log(f"      {tag}: {vorher - len(d):,} Rueckblick-Ereignisse ausserhalb "
                f"des Fensters verworfen")
        if d.empty:
            continue

        geo = d[["G1", "G2", "G3"]]
        for code in LAENDER:
            roh = d.loc[geo.eq(code).any(axis=1)]
            if roh.empty:
                continue
            t = zeilen_filtern(roh, code)
            if t.empty:
                continue
            if len(roh) > 200:
                log(f"      {tag} {code}: {len(roh):,} Erwähnungen -> "
                    f"{len(t):,} zurechenbare Ereignisse")
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
                if not slug_erlaubt(str(r.surl)):
                    continue
                titel = slug_zu_titel(str(r.surl))
                if not titel or titel.lower() in gesehen:
                    continue
                gesehen.add(titel.lower())
                eintraege.append({"titel": titel, "url": str(r.surl),
                                  "gold": round(float(r.gold), 1)})
                if len(eintraege) >= 5:
                    break
            if eintraege:
                news[code][tag] = eintraege
        log(f"      {tag}: {len(d):,} Zeilen verdichtet, "
            f"{sum(len(v[tag]) for v in news.values() if tag in v)} Überschriften")
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


def brauchbar(df: pd.DataFrame | None) -> str | None:
    """Prueft eine frisch geladene Reihe, BEVOR sie gespeichert wird.

    Zwei Ausschluesse, beide aus dem Betrieb gelernt: eine Reihe, die zu kurz
    ist (Yahoo fuehrt ^CASE30, liefert aber einen Tag), und eine, die nicht
    mehr fortgeschrieben wird (IMOEX.ME endet im Juni 2024). Bisher wurden
    solche Reihen gespeichert und erst weiter unten verworfen -- das Land
    verlor den Baustein, ohne dass ein Ausweichsymbol je zum Zug gekommen
    waere. Die Pruefung gehoert deshalb hierher.
    """
    if df is None or df.empty:
        return "nicht abrufbar"
    if len(df) < MIN_BAUSTEIN_TAGE:
        return f"nur {len(df)} Tage"
    alter = (dt.date.today() - df.date.max().date()).days
    if alter > MAX_BAUSTEIN_ALTER:
        return f"endet {df.date.max():%Y-%m-%d}"
    return None


def marktdaten(voll: bool) -> None:
    for code, (name, fx, ak) in LAENDER.items():
        for art, sym in (("fx", fx), ("aktien", ak)):
            kandidaten = [x for x in (sym if isinstance(sym, (list, tuple)) else [sym]) if x]
            if not kandidaten:
                continue
            ziel = DATEN / f"{art}_{code}.csv"
            if ziel.exists() and not voll:
                alt = pd.read_csv(ziel, sep=";", parse_dates=["date"])
                if (dt.date.today() - alt.date.max().date()).days < 1:
                    continue
            gruende = []
            for s in kandidaten:
                df = yahoo(s)
                grund = brauchbar(df)
                if grund:
                    gruende.append(f"{s}: {grund}")
                    time.sleep(0.3)
                    continue
                df.to_csv(ziel, index=False, sep=";")
                if len(kandidaten) > 1:
                    log(f"      {name} {art}: {s} ({len(df)} Tage)"
                        + (f" — übersprungen: {'; '.join(gruende)}" if gruende else ""))
                time.sleep(0.3)
                break
            else:
                log(f"      [WARN] {name} {art}: kein brauchbares Symbol "
                    f"({'; '.join(gruende)})")
    roh = holen(GPR_URL, timeout=120)
    if roh:
        (DATEN / "gpr.xls").write_bytes(roh)


# ---------------------------------------------------------------- Auswertung
def risikoreihe(code: str, gpr: pd.DataFrame) -> pd.DataFrame | None:
    """Setzt den Risikoindex aus den verfuegbaren Bausteinen zusammen.

    Ein Baustein mit zu wenig Historie wird VERWORFEN, nicht das Land. Yahoo
    fuehrt fuer manche Boersen ein Symbol, liefert dazu aber kaum Daten --
    ^CASE30 (Aegypten) gab beim ersten Lauf genau einen Tag zurueck. Ohne
    diese Regel haette Aegypten das Land gekostet statt nur die
    Marktkomponente.
    """
    def lebt(df: pd.DataFrame, was: str) -> bool:
        """Prueft, ob eine Reihe noch fortgeschrieben wird.

        Laenge allein reicht nicht: der Moskauer Aktienindex IMOEX.ME hat
        ueber 600 Tage Historie, endet bei Yahoo aber am 14.06.2024. Weil der
        Index nur vollstaendige Tage ausweist, hat diese eine tote Reihe die
        gesamte Russland-Kurve auf 2024 eingefroren. Eine Reihe, die laenger
        als MAX_BAUSTEIN_ALTER Tage stillsteht, wird deshalb wie ein zu
        kurzer Baustein behandelt: sie faellt weg, das Land bleibt.
        """
        alter = (pd.Timestamp.today().normalize() - df.date.max()).days
        if alter > MAX_BAUSTEIN_ALTER:
            log(f"      [INFO] {code}: {was} endet am "
                f"{df.date.max():%Y-%m-%d} ({alter} Tage alt) — Baustein entfällt")
            return False
        return True

    teile = []
    # Rand, der wegen einer noch unbestaetigten Kursbewegung nicht beurteilbar
    # ist -- wird nach oben gegeben, damit der Tag keine Meldung ausloest.
    unbestaetigt = False
    f = DATEN / f"fx_{code}.csv"
    if f.exists():
        fx = pd.read_csv(f, sep=";", parse_dates=["date"]).sort_values("date")
        if len(fx) >= MIN_BAUSTEIN_TAGE and lebt(fx, "Währungsreihe"):
            fx, nf, uf = kurse_bereinigen(fx)
            unbestaetigt = unbestaetigt or uf
            if nf:
                log(f"      [INFO] {code}: {nf} Fehlnotierung(en) in der "
                    f"Währungsreihe ersetzt (Sprung mit Rückkehr am Folgetag)")
            r = np.log(fx.close).diff()
            fx["v"] = r.rolling(VOL_FENSTER).std(ddof=0) * np.sqrt(252)
            fx["a"] = np.log(fx.close).diff(VOL_FENSTER)
            za = ((fx.v - fx.v.mean()) / fx.v.std() + (fx.a - fx.a.mean()) / fx.a.std()) / 2
            teile.append(pd.DataFrame({"date": fx.date, "waehrung": za}))
        else:
            log(f"      [INFO] {code}: Währungsreihe nicht nutzbar ({len(fx)} Tage) — Baustein entfällt") if len(fx) < MIN_BAUSTEIN_TAGE else None
    a = DATEN / f"aktien_{code}.csv"
    if a.exists():
        ak = pd.read_csv(a, sep=";", parse_dates=["date"]).sort_values("date")
        if len(ak) >= MIN_BAUSTEIN_TAGE and lebt(ak, "Aktienreihe"):
            ak, na, ua = kurse_bereinigen(ak)
            unbestaetigt = unbestaetigt or ua
            if na:
                log(f"      [INFO] {code}: {na} Fehlnotierung(en) in der "
                    f"Aktienreihe ersetzt (Sprung mit Rückkehr am Folgetag)")
            v = np.log(ak.close).diff().rolling(VOL_FENSTER).std(ddof=0) * np.sqrt(252)
            teile.append(pd.DataFrame({"date": ak.date, "markt": (v - v.mean()) / v.std()}))
        else:
            log(f"      [INFO] {code}: Aktienreihe nicht nutzbar ({len(ak)} Tage) — Baustein entfällt") if len(ak) < MIN_BAUSTEIN_TAGE else None
    if not teile:
        return None
    d = teile[0]
    for t in teile[1:]:
        d = d.merge(t, on="date", how="outer")
    d = d.merge(gpr, on="date", how="left").sort_values("date")
    kats = [c for c in ["waehrung", "markt", "geopolitik"] if c in d.columns]

    # Kurze Luecken schliessen, dann nur vollstaendige Tage behalten.
    #
    # Grund: Die Bausteine haben unterschiedliche Kalender. Boersen und
    # Devisenmaerkte haben verschiedene Feiertage, und der GPR-Index wird mit
    # einem Tag Verzoegerung veroeffentlicht. Wird der Index einfach ueber die
    # jeweils vorhandenen Bausteine gemittelt, aendert sich seine
    # ZUSAMMENSETZUNG von Tag zu Tag -- und damit sein Niveau, ohne dass sich
    # am Risiko etwas geaendert haette. Beim ersten Lauf erzeugte genau das
    # vier falsche Auffaelligkeiten: am letzten Tag fehlte der GPR, der
    # zuvor stark positiv war, und der Mittelwert stuerzte ab.
    #
    # Deshalb: bis zu FFILL_TAGE Tage vorwaerts fuellen (ein Feiertag oder
    # eine Veroeffentlichungsverzoegerung aendert das Risiko nicht), und
    # anschliessend jeden Tag verwerfen, an dem ein Baustein weiterhin fehlt.
    # Der Index hat damit an jedem ausgewiesenen Tag dieselbe Basis.
    for k in kats:
        d[k] = d[k].ffill(limit=FFILL_TAGE)
    d = d.dropna(subset=kats)
    if d.empty:
        return None
    d["risiko"] = d[kats].mean(axis=1)
    d = d.reset_index(drop=True)
    # Als SPALTE, nicht als DataFrame.attrs: attrs ueberlebt die nachfolgenden
    # merge-Aufrufe nicht zuverlaessig, und genau daran ging der Hinweis
    # zunaechst verloren -- der unbestaetigte Sprung der Hrywnja am 11.09.
    # (+2,96 % nach Wochen um 0,3 %) kam als bestaetigte Meldung durch.
    d["kurs_offen"] = False
    if unbestaetigt and len(d):
        d.loc[d.index[-1], "kurs_offen"] = True
    return d


def prognose(d: pd.DataFrame, merkmale: list[str]
             ) -> tuple[float | None, float | None]:
    """Wahrscheinlichkeit erhoehter Anspannung in PROGNOSE_HORIZONT Tagen.

    Zurueck kommen ZWEI Zahlen: die Vorhersage fuer heute und die AUC aus
    dem letzten 30-Prozent-Zeitfenster, das im Training nicht vorkam. Die
    zweite Zahl wird im Dashboard immer neben der ersten ausgewiesen -- eine
    Prognose ohne ihre gemessene Guete ist eine Behauptung.

    Die Merkmalsliste wird uebergeben, damit dieselbe Funktion das
    Marktmodell und das GDELT-Modell rechnet. Wuerden beide getrennt
    implementiert, waere jeder Unterschied im Ergebnis nicht mehr eindeutig
    auf die Merkmale zurueckzufuehren.
    """
    F = [m for m in merkmale if m in d.columns]
    if not F:
        return None, None
    dd = d.dropna(subset=F)
    y = (dd.z.shift(-PROGNOSE_HORIZONT) >= PROGNOSE_SCHWELLE).astype(float)
    train = dd.assign(y=y).dropna(subset=["y"])
    if len(train) < 400 or train.y.nunique() < 2:
        return None, None
    # Guete im expandierenden Zeitfenster, NICHT aus einem einzelnen
    # 70/30-Schnitt. Ein Einmal-Split misst das Modell an genau einer
    # Zeitperiode; faellt die zufaellig guenstig aus, steht im Dashboard eine
    # geschoente Zahl. Beim ersten Lauf war das sichtbar: das Ereignismodell
    # fuer Israel kam auf 0,81, waehrend derselbe Merkmalssatz im
    # Modellvergleich (vergleich_gdelt.py, expandierendes Fenster) 0,62
    # erreichte. Zwei verschiedene Zahlen fuer dasselbe Modell sind nicht
    # erklaerbar -- deshalb rechnen jetzt beide Stellen identisch.
    y = train.y.to_numpy()
    X = train[F]
    vorher = np.full(len(y), np.nan)
    for a in range(int(len(y) * 0.5), len(y), 20):
        b = min(a + 20, len(y))
        if len(np.unique(y[:a])) < 2:
            continue
        sc = StandardScaler().fit(X.iloc[:a])
        mm = LogisticRegression(class_weight="balanced", max_iter=4000)
        mm.fit(sc.transform(X.iloc[:a]), y[:a])
        vorher[a:b] = mm.predict_proba(sc.transform(X.iloc[a:b]))[:, 1]
    gilt = ~np.isnan(vorher)
    guete = (round(float(roc_auc_score(y[gilt], vorher[gilt])), 3)
             if gilt.sum() >= 60 and len(np.unique(y[gilt])) > 1 else None)
    sc = StandardScaler().fit(train[F])
    m = LogisticRegression(class_weight="balanced", max_iter=4000).fit(sc.transform(train[F]), train.y)
    return round(float(m.predict_proba(sc.transform(dd[F].tail(1)))[0, 1]), 3), guete


def guete_persistenz(d: pd.DataFrame) -> float | None:
    """Nullmodell: der Score ist das heutige z. Null Parameter, nichts gelernt.

    Steht im Dashboard als Messlatte neben den beiden Modellen. Ein Modell,
    das diese Zahl nicht schlaegt, hat nichts gelernt, egal wie hoch seine
    AUC absolut aussieht.
    """
    dd = d.dropna(subset=["z"])
    y = (dd.z.shift(-PROGNOSE_HORIZONT) >= PROGNOSE_SCHWELLE)
    t = dd.assign(y=y.astype(float)).dropna(subset=["y"])
    te = t.iloc[int(len(t) * 0.5):]
    if len(te) < 30 or te.y.nunique() < 2:
        return None
    return round(float(roc_auc_score(te.y, te.z)), 3)


def bausteinreihe(code: str, gpr: pd.DataFrame, gd: pd.DataFrame):
    """Die vier Bausteine EINES Landes, fertig normiert -- eine Quelle fuer alle.

    Drei Stellen brauchen genau diese Reihe: der taegliche Lauf, die netzfreie
    Nachrechnung und die Gewichtskalibrierung. Sie war an allen drei Stellen
    einzeln nachgebaut, und die Nachbauten sind auseinandergelaufen -- die
    Kalibrierung hatte weder die Tagesgueltigkeit noch die gemeinsame
    Normierung, haette also Gewichte fuer einen Index bestimmt, den es im
    Betrieb nicht mehr gibt. Wer hier etwas aendert, aendert es fuer alle drei.

    Zurueck kommen die Tagesreihe mit den Bausteinspalten, die bereinigten
    Tagesaggregate des Landes (fuer die Episodenerkennung) und das Protokoll
    der Tagesgueltigkeit.
    """
    d = risikoreihe(code, gpr)
    if d is None or len(d) < 300:
        return None, pd.DataFrame(), {"verworfen": 0, "stand": None, "rand": 0}
    g = gd[gd.code == code].copy() if len(gd) else pd.DataFrame()
    if len(g):
        # Unvollstaendige Erntetage entfernen, BEVOR Merkmale gebildet
        # werden. Die Ereignisanteile sind Quotienten; ein halb geernteter
        # Tag hat einen zu kleinen Nenner und damit einen zu hohen Anteil.
        # Gemessen im eigenen Bestand: duenne Tage stellen 1,42 % aller
        # Tage, aber 2,29 % aller Ueberschreitungen von zwei
        # Standardabweichungen -- Faktor 2,4. Begruendung und Schwellen in
        # tagesgueltigkeit.py.
        g, gdq = bereinigen(g)
        g["tone_avg"] = np.where(g.tone_cnt > 0, g.tone_sum / g.tone_cnt, np.nan)
        d = d.merge(g[["date", "n_events", "tone_avg"]], on="date", how="left")
        d = d.merge(gdelt_merkmale(g), on="date", how="left")
        # Ereignislage nur an TATSAECHLICH GEMESSENEN Tagen bilden und von dort
        # hoechstens EREIGNIS_NACHLAUF Kalendertage weitertragen.
        #
        # Zwei Fallen stecken hier, beide bereits hineingetappt:
        # 1. ereignislage() glaettet ueber drei Zeilen. An der Kante erzeugt das
        #    aus sich heraus noch Werte fuer Tage ohne jede Messung -- die
        #    Glaettung verlaengert die Reihe, ohne neue Information zu haben.
        # 2. Eine Grenze in ZEILEN ist keine Grenze in Tagen. Die Reihe laeuft auf
        #    Handelstagen; drei Zeilen nach einem Freitag sind der Mittwoch. Im
        #    Bestand stand dadurch derselbe Ereigniswert an vier aufeinander
        #    folgenden Tagen bis zum 11.09., obwohl die letzte Messung vom 06.09.
        #    war.
        # Gezaehlt wird deshalb in Kalendertagen seit der letzten Messung. Drei
        # Tage deckt das Wochenende ab (Freitag gemessen, Montag gelesen) und
        # bleibt innerhalb der Mindestdauer einer Episode (krisen.MIN_TAGE = 5).
        gemessen = d.n_events.notna()
        stand_ereignis = d.date.where(gemessen).ffill()
        d["ereignis_alter"] = (d.date - stand_ereignis).dt.days
        lage = ereignislage(d).where(gemessen)
        d["ereignis"] = lage.ffill().where(d.ereignis_alter <= EREIGNIS_NACHLAUF)
        # Der ausgewiesene Ereignisstand ist der letzte Tag, den die REIHE
        # benutzt -- nicht der letzte gueltige Kalendertag im Bestand.
        #
        # Die beiden fallen auseinander, wenn die letzte gueltige Messung auf
        # einen Nichthandelstag faellt: fuer die Ukraine stand am 13.09.2026
        # (Sonntag) eine gueltige Messung im Bestand, die Reihe endet aber am
        # Freitag. Die Oberflaeche behauptete dadurch beides gleichzeitig --
        # "Ereignisdaten bis 13.09." und "Baustein Ereignislage fehlt".
        if gemessen.any():
            gdq = dict(gdq)
            gdq["stand"] = d.date[gemessen].max().strftime("%Y-%m-%d")
            gdq["rand"] = int((d.date.max() - d.date[gemessen].max()).days)
    else:
        d["n_events"], d["tone_avg"], d["ereignis"] = np.nan, np.nan, np.nan

    # Gemeinsame Skala fuer alle Bausteine -- Begruendung mit den gemessenen
    # Kennzahlen in index_gewichte.normieren.
    d = normieren(d)
    # Ein noch unbestaetigter Kurssprung am letzten Tag macht diesen Tag
    # unlesbar -- nicht die Reihe. Entscheidet sich morgen, dass die Bewegung
    # Bestand hat, wird sie mit einem Tag Verzug gemeldet; loest sie sich auf,
    # wird sie als Fehlnotierung ersetzt. Einen Tag Verzug gegen einen
    # Fehlalarm ist fuer ein Warnwerkzeug der richtige Tausch.
    return normieren(d), g, gdq

def fehlende_bausteine(zeile: pd.DataFrame, GEW: dict) -> list[str]:
    """Namen der Bausteine, die in dieser Zeile fehlen -- fuer die Oberflaeche."""
    if zeile is None or zeile.empty:
        return []
    r = zeile.iloc[0]
    return [b for b in BAUSTEINE
            if b in zeile.columns and GEW.get(b) and not np.isfinite(r.get(b, np.nan))]


def land_auswerten(code: str, name: str, gpr: pd.DataFrame, gd: pd.DataFrame,
                   GEW: dict, grund: dict, prof: dict, news: dict):
    """Die vollstaendige Auswertung EINES Landes.

    Eigene Funktion, weil es zwei Aufrufer gibt: den taeglichen Lauf und die
    netzfreie Nachrechnung, mit der Aenderungen an der Logik gegen den
    vorhandenen Bestand geprueft werden. Solange dieser Block im Schleifenrumpf
    von main() stand, musste die Nachrechnung ihn nachbauen -- und war nach
    jeder Aenderung an der Reihenfolge der Schritte stillschweigend eine andere
    Rechnung als der Produktivlauf. Genau diese Art von Auseinanderlaufen ist
    der Grund, aus dem gdelt_merkmale.py schon zentral liegt.

    Zurueck kommen der Dashboard-Eintrag, die Lagemeldungen des Landes und die
    Auffaelligkeiten der letzten beiden Tage; None, wenn die Reihe zu kurz ist.
    """
    auff = []
    d, g, gdq = bausteinreihe(code, gpr, gd)
    if d is None:
        log(f"      [WARN] {name}: zu wenig Daten")
        return None


    # Index aus den gewichteten Bausteinen samt Eskalationsklausel. Der
    # ungewichtete Mittelwert aus risikoreihe() bleibt als roher Rueckfall
    # erhalten, damit ein Land ohne jeden Baustein nicht ausfaellt.
    # ZWEI INDIZES, UND DAS IST KEINE DOPPELUNG.
    #
    # risiko        Zustandsindex, MIT Ereignislage. Er beantwortet "wie
    #               ist die Lage heute" und treibt Anzeige und Meldungen.
    # risiko_markt  derselbe Index OHNE Ereignislage, also nur Waehrung,
    #               Markt, globales Umfeld.
    #
    # Der Grund ist ein Zirkelschluss, der mit dem Ereignisbaustein
    # entstanden ist: die Prognosepruefung fragt, ob GDELT-Merkmale kuenftige
    # Anspannung vorhersagen. Enthaelt die ZIELGROESSE selbst schon einen
    # aus GDELT gebildeten Baustein, dann sagt das Ereignismodell zu einem
    # Teil seine eigene Eingabe voraus -- genau der Vorwurf, der in der
    # zugrunde liegenden Arbeit in den Limitationen steht und der dort mit
    # einem externen Ziel geprueft wurde. Deshalb laufen alle
    # Prognoserechnungen gegen risiko_markt, und nur die Zustandsanzeige
    # gegen risiko.
    # Der Marktindex wird GENAUSO gebildet wie der Zustandsindex, nur ohne den
    # Ereignisbaustein -- gewichtet, normiert, mit Eskalationsklausel.
    #
    # Er war zuvor etwas anderes: das ungewichtete Mittel der ROHEN
    # Marktbausteine aus risikoreihe(), ohne Normierung und ohne Klausel. Die
    # Methodennotiz behauptete "derselbe Index ohne Ereignislage", und das
    # stimmte nicht. Fuer die Pruefzahlen ist das nicht gleichgueltig: der
    # Vergleich "traegt GDELT etwas bei" soll zwei Reihen vergleichen, die sich
    # in genau einem Punkt unterscheiden, nicht in drei.
    rm = zusammensetzen(d.drop(columns=["ereignis"], errors="ignore"), GEW)
    d["risiko_markt"] = rm.where(np.isfinite(rm), d.risiko)

    # Bausteine auf eine gemeinsame Skala bringen, BEVOR sie gewichtet werden.
    # Vorher hatten sie drei verschiedene Nullpunkte (Begruendung mit den
    # gemessenen Kennzahlen in index_gewichte.normieren). Folge im Bestand:
    # die Lagemeldung "Waehrungsdruck aussergewoehnlich hoch" wies fuer die
    # Tuerkei +2,26 Standardabweichungen aus, waehrend dieselbe Kurve auf
    # derselben Seite bei -0,32 lag -- die Meldung rechnete einen zweiten
    # z-Wert, den es in der Anzeige nicht gab. Jetzt ist es derselbe Wert.
    neu_index = zusammensetzen(d, GEW)
    d["risiko"] = neu_index.where(np.isfinite(neu_index), d.risiko_markt)

    # Tage, an denen ein eigentlich vorhandener Baustein fehlt, werden NICHT
    # aus den uebrigen hochgerechnet, sondern als nicht beurteilbar gefuehrt.
    # Begruendung mit Zahlenbeispiel in index_gewichte.vollstaendig(); kurz:
    # sonst meldet der Monitor Entspannung, wenn nur die Messung ausgefallen
    # ist. Die Marktbausteine laufen weiter -- der Zustandsindex wartet.
    d["voll"] = vollstaendig(d, GEW)
    # Dazu jeder Tag, an dem eine aussergewoehnliche Kursbewegung noch nicht
    # bestaetigt ist (tagesgueltigkeit.kursausreisser).
    if "kurs_offen" in d.columns and d.kurs_offen.any():
        d.loc[d.kurs_offen.astype(bool), "voll"] = False
        offen = d.date[d.kurs_offen.astype(bool)].max()
        log(f"      [INFO] {name}: Kursbewegung am {offen:%Y-%m-%d} noch nicht "
            f"bestätigt — Tag gilt als nicht beurteilbar")
    d.loc[~d.voll, "risiko"] = np.nan

    mu = d.risiko.rolling(NORM_FENSTER, min_periods=60).mean()
    sd = d.risiko.rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
    d["z"] = (d.risiko - mu) / sd
    mu_m = d.risiko_markt.rolling(NORM_FENSTER, min_periods=60).mean()
    sd_m = d.risiko_markt.rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
    d["z_markt"] = (d.risiko_markt - mu_m) / sd_m
    bew = d.z.diff() / d.z.diff().rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
    # Auffaelligkeit heisst: plotzliche Bewegung NACH OBEN.
    #
    # Zwei Einschraenkungen gegenueber der ersten Fassung:
    # 1. Nur nach oben -- ein ungewoehnlich ruhiger Tag ist fuer einen
    #    Risikomonitor kein Warnsignal.
    # 2. Ohne das Niveaukriterium. Ein wochenlang erhoehtes Risiko erzeugte
    #    sonst dreissig aufeinanderfolgende "Auffaelligkeiten", obwohl es
    #    ein einziger Zustand ist -- in Brasilien traf das 34 von 200 Tagen.
    #    Das Niveau wird ohnehin als Status ausgewiesen (ruhig / normal /
    #    erhoeht / hoch); die Auffaelligkeit meldet die Veraenderung.
    d["auffaellig"] = (bew > AUFF_BEWEGUNG).astype(int)
    # Rand der ROHREIHE festhalten, bevor die nicht beurteilbaren Tage
    # herausfallen. Danach endet d am letzten vollstaendigen Tag -- richtig so,
    # aber die Oberflaeche soll sagen koennen, bis wann Marktdaten vorliegen.
    rand_datum = d.date.max()
    # Die verworfenen Randzeilen aufheben, um gleich sagen zu koennen, WAS an
    # ihnen gefehlt hat.
    # Nur der Rand ZUSAMMENHAENGEND ab dem Stichtag zaehlt. Eine einzelne
    # unlesbare Zeile von vor acht Monaten ist keine Begruendung fuer heute.
    roh_rand = d[~d.voll & (d.date > d.date[d.voll].max())].tail(1) \
        if d.voll.any() else d.tail(0)
    d_roh = d
    d = d.dropna(subset=["z"])
    if d.empty:
        return None
    # Die Hilfsgroessen der Prognose beziehen sich auf den MARKTINDEX --
    # siehe die Begruendung oben.
    d["z_d1"] = d.z_markt.diff()
    d["r_d1"] = d.risiko_markt.diff()
    d["r_d5"] = d.risiko_markt.diff(5)

    # Zwei Prognosen nebeneinander -- die Forschungsfrage der Arbeit, im
    # Produkt sichtbar gemacht. Das Marktmodell schreibt den Marktindex aus
    # sich selbst fort, das Ereignismodell nutzt ausschliesslich GDELT.
    # Beide auf DERSELBEN Zielgroesse, und die ist frei von Ereignisdaten.
    dp = d.assign(z=d.z_markt)
    prog, guete = prognose(dp, ["z", "z_d1", "r_d1", "r_d5"])
    prog_g, guete_g = prognose(dp, G_MERKMALE)
    guete_p = guete_persistenz(dp)

    # Laufende Lagen aus den Ereignisdaten. Das ist die Aufgabe, fuer die
    # GDELT taugt: erkennen, was gerade passiert -- nicht vorhersagen,
    # was kommt.
    lagen = krisen(g, d.date.max()) if len(g) else []

    # Erste Ebene: was ist eingetreten. Die Meldungen entstehen auf der
    # VOLLEN Reihe, nicht auf dem Anzeigefenster -- sonst haengt die
    # Frage "seit wann" davon ab, wie viele Tage die Oberflaeche zeigt.
    meldungen = warnungen(d, lagen, code, name)
    # (Meldungen gehen als Rueckgabewert nach oben)

    # Zweite Ebene: Fortschreibung. Jede Reihe aus ihrer eigenen
    # Historie, dazu eine Variante mit den GDELT-Merkmalen. Der
    # Ruecktest gegen die Beibehaltungsregel wird immer mitgeliefert.
    # Fortgeschrieben wird der MARKTINDEX. Auch hier sonst ein Zirkel: die
    # Zeile "mit GDELT-Merkmalen" soll pruefen, ob Ereignisdaten etwas
    # beitragen -- in einer Reihe, die sie schon enthaelt, kann sie das
    # nicht ehrlich pruefen.
    aus_b = {"gesamt": fortschreibung(d.z_markt.tolist())}
    # Fortgeschrieben werden nur die MARKTBAUSTEINE. Die Ereignislage
    # bleibt aussen vor: fuer sie ist genau der Prognosebeitrag geprueft
    # und nicht nachweisbar -- sie gehoert in den Zustand, nicht in die
    # Fortschreibung.
    for k in [c for c in ["waehrung", "markt", "geopolitik"] if c in d.columns]:
        aus_b[k] = fortschreibung(d[k].tolist())
    vorhandene = [m for m in G_MERKMALE if m in d.columns]
    aus_b["gdelt"] = (fortschreibung(d.z_markt.tolist(), merkmale=d[vorhandene].to_numpy())
                      if len(vorhandene) >= 3 else None)

    # Der Zustand wird auf der letzten VOLLSTAENDIGEN Zeile gelesen. Die
    # Reihe selbst reicht weiter: Boersenkurse kommen noch, Ereignisdaten
    # nicht. Ohne diese Trennung stuende in der Kopfzeile ein Wert, der aus
    # weniger Bausteinen gebildet ist als alle Werte davor.
    vz = d[d.voll & d.z.notna()]
    if vz.empty:
        log(f"      [WARN] {name}: kein vollstaendiger Tag")
        return None
    letzte_voll = vz.date.iloc[-1]
    z = d.tail(TAGE_ANZEIGE)
    kats = [c for c in BAUSTEINE if c in z.columns]
    eintrag = {
        "name": name,
        "daten": [x.strftime("%Y-%m-%d") for x in z.date],
        "risiko": [None if pd.isna(v) else round(float(v), 3) for v in z.z],
        "kategorien": {k: [None if pd.isna(v) else round(float(v), 3) for v in z[k]] for k in kats},
        "n_events": [None if pd.isna(v) else int(v) for v in z.n_events],
        "tone_avg": [None if pd.isna(v) else round(float(v), 2) for v in z.tone_avg],
        "auffaellig": [int(v) for v in z.auffaellig],
        "prognose_7t": prog, "prognose_auc": guete,
        "steckbrief": {k: prof.get(code, {}).get(k) for k in WB_INDIKATOREN
                       if prof.get(code, {}).get(k)},
        "ueberblick": UEBERBLICK.get(code, ""),
        "grundniveau": grund.get(code),
        # Datenstand der EREIGNISDATEN, getrennt vom Stand der Reihe.
        # Beides auseinanderzuhalten ist kein Detail: die Kurve endet
        # heute, die Ereignismessung endet oft ein bis fuenf Tage frueher.
        # Ohne diese Angabe liest man einen Ereigniswert als heutigen.
        "gdelt_stand": gdq.get("stand"),
        "gdelt_rand": gdq.get("rand", 0),
        "gdelt_verworfen": gdq.get("verworfen", 0),
        "krisen": lagen,
        "warnungen": meldungen,
        "ausblick": aus_b,
        "prognose_gdelt_7t": prog_g, "prognose_gdelt_auc": guete_g,
        "prognose_basis": "Marktindex ohne Ereignislage",
        "z_markt": (None if pd.isna(z.z_markt.iloc[-1])
                    else round(float(z.z_markt.iloc[-1]), 2)),
        "prognose_persistenz_auc": guete_p,
        "stand_datum": letzte_voll.strftime("%Y-%m-%d"),
        "stand_z": round(float(vz.z.iloc[-1]), 2),
        # Bis wohin die Reihe ueberhaupt Daten hat, auch wenn sie nicht mehr
        # vollstaendig sind -- damit die Oberflaeche den Unterschied benennen
        # kann statt ihn zu verschweigen.
        "reihe_bis": rand_datum.strftime("%Y-%m-%d"),
        "unvollstaendig_tage": int((rand_datum - letzte_voll).days),
        # WELCHER Baustein fehlt. Ohne diese Angabe steht in der Oberflaeche
        # "mindestens ein Baustein fehlt" -- wahr, aber fuer den Leser nicht
        # nachvollziehbar, und damit keine Begruendung, sondern eine Ausrede.
        "unvollstaendig_grund": fehlende_bausteine(roh_rand, GEW),
        # Der zweite Grund, aus dem ein Tag nicht beurteilbar ist: eine
        # aussergewoehnliche Kursbewegung, deren Bestand erst der Folgetag
        # zeigt. Beide Gruende muessen unterscheidbar sein -- "ein Baustein
        # fehlt" und "eine Notierung ist noch offen" sind verschiedene
        # Aussagen, und nur die zweite loest sich von allein auf.
        "kurs_offen_am": (None if not ("kurs_offen" in d_roh.columns and d_roh.kurs_offen.any())
                          else d_roh.date[d_roh.kurs_offen.astype(bool)].max().strftime("%Y-%m-%d")),
        "nachrichten": news.get(code, {}),
    }
    # Auffaelligkeiten der letzten beiden Tage -> Historie und Meldung
    for _, r in z.tail(2).iterrows():
        if r.auffaellig == 1:
            auff.append({"datum": r.date.strftime("%Y-%m-%d"), "code": code,
                             "land": name, "z": round(float(r.z), 2)})
    return eintrag, meldungen, auff


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

    # Datum des Filterwechsels festhalten. Solange die Historie nicht mit
    # demselben Filter neu geladen ist, hat die Ereigniszahl hier einen Sprung
    # nach unten -- der soll benannt sein und nicht entdeckt werden muessen.
    pfad_fw = DATEN / "filterwechsel.json"
    if not pfad_fw.exists() and not neu_agg.empty:
        pfad_fw.write_text(json.dumps({
            "ab": min(neu_agg.date).strftime("%Y-%m-%d"),
            "was": "Handlungsort statt beliebiger Erwaehnung, Akteur des Landes "
                   "verlangt, Duplikate je Quelle entfernt",
            "wirkung": "Ereigniszahl sinkt um rund 70 bis 80 Prozent, Anteile "
                       "bleiben nahezu unveraendert",
            "hinweis": "Fuer eine bruchfreie Reihe die Historie mit "
                       "gdelt_historie.py neu laden."}, ensure_ascii=False, indent=1))
        log(f"      [WICHTIG] Filterwechsel ab {min(neu_agg.date):%Y-%m-%d} "
            f"vermerkt (daten/filterwechsel.json)")

    log("[2/4] Marktdaten und Steckbrief aktualisieren ...")
    marktdaten(args.voll)
    prof = profil()

    log("[3/4] Risikoindex, Lagemeldungen, Ausblick ...")
    GEW, herkunft = gewichte_laden(DATEN)
    log("      Gewichte: " + ", ".join(f"{b} {GEW.get(b, 0):.2f}" for b in BAUSTEINE)
        + f"  ({herkunft})")
    gpr = pd.read_excel(DATEN / "gpr.xls")[["date", "GPRD"]].rename(columns={"GPRD": "gpr"})
    gpr["date"] = pd.to_datetime(gpr.date)
    gpr["geopolitik"] = (gpr.gpr - gpr.gpr.mean()) / gpr.gpr.std()
    gpr = gpr[["date", "geopolitik"]]

    gd = (pd.read_csv(pfad_agg, sep=";", parse_dates=["date"])
          if pfad_agg.exists() else pd.DataFrame(columns=["date", "code"]))
    # Grundniveau: die zweite, langsame Achse. Sie beantwortet nicht "was ist
    # heute", sondern "wie riskant ist dieses Land ueberhaupt" -- ohne sie
    # erschien ein Land im Dauerkonflikt an einem ruhigen Tag als risikoarm.
    # Steht hier, weil dafuer die Tagesaggregate vorliegen muessen.
    grund = GN.berechnen(LAENDER, DATEN, gd)
    GN.schreiben(grund, DATEN)
    unsicher = [c for c in grund if grund[c].get("unsicher")]
    log(f"      Grundniveau für {len(grund)} Länder"
        + (f" ({len(unsicher)} vorläufig, zu wenige Größen: "
           f"{', '.join(sorted(unsicher))})" if unsicher else ""))

    ausgabe, historie_neu = {"stand": None, "laender": {}}, []
    alle_meldungen = []
    for code, (name, _, _) in LAENDER.items():
        erg = land_auswerten(code, name, gpr, gd, GEW, grund, prof, news)
        if erg is None:
            continue
        eintrag, meldungen, auff = erg
        ausgabe["laender"][code] = eintrag
        alle_meldungen += meldungen
        historie_neu += auff


    if not ausgabe["laender"]:
        log("[FEHLER] Keine auswertbaren Laender."); return 1
    ausgabe["stand"] = max(v["stand_datum"] for v in ausgabe["laender"].values())
    ausgabe["lage"] = zusammenfassen(alle_meldungen)
    ausgabe["grundniveau"] = {"fenster_tage": GN.FENSTER, "groessen": GN.GROESSEN}
    # Datenlage als eigener Abschnitt: was ist gemessen, was verworfen, wie
    # alt ist die juengste Ereignismessung. Ein Warnwerkzeug, das nicht sagt,
    # wie frisch seine Eingangsdaten sind, laedt zur Fehllesung ein.
    staende = [v["gdelt_stand"] for v in ausgabe["laender"].values() if v.get("gdelt_stand")]
    ausgabe["datenlage"] = {
        "gdelt_stand_frueh": min(staende) if staende else None,
        "gdelt_stand_spaet": max(staende) if staende else None,
        "verworfen": sum(v.get("gdelt_verworfen", 0) for v in ausgabe["laender"].values()),
        "nachlauf_tage": EREIGNIS_NACHLAUF,
        "regel": ("Ein GDELT-Tag gilt als gemessen, wenn er mindestens 30 Ereignisse "
                  "und mindestens 40 Prozent der ueblichen Menge desselben Wochentags "
                  "enthaelt; sonst wird er als nicht gemessen behandelt."),
    }
    log(f"      Ereignisdaten: Stand {ausgabe['datenlage']['gdelt_stand_frueh']} bis "
        f"{ausgabe['datenlage']['gdelt_stand_spaet']}, "
        f"{ausgabe['datenlage']['verworfen']} Tage als unvollstaendig verworfen")

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

    lage = ausgabe["lage"]
    log(f"\nStand {ausgabe['stand']} | {len(ausgabe['laender'])} Länder"
        f" | {lage['anzahl']} Lagemeldungen ({lage['neu']} neu, "
        f"{lage['kritisch']} kritisch) in {lage['laender']} Ländern"
        f" | {len(frisch)} neue Auffälligkeiten")
    for m in lage["meldungen"][:8]:
        log(f"   {'!' if m['neu'] else ' '} [{m['stufe']:>9}] {m['land']}: "
            f"{m['titel']} (seit {m['seit']})")
    for f in frisch:
        log(f"   ! {f['land']} {f['datum']} z={f['z']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
