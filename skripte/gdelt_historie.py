"""GDELT-Tagesaggregate rueckwirkend nachladen -- unterbrechbar.

Warum ein eigenes Skript und nicht der Nachlauf in aktualisieren.py:
Der taegliche Lauf holt vier Tage. Hier geht es um mehr als 1.300 Tage à
96 Dateien, also gut 125.000 Downloads. Das laeuft Stunden und wird
zwangslaeufig unterbrochen -- durch Netz, Ruhezustand oder Strg-C.

Deshalb schreibt dieses Skript JEDEN fertigen Tag sofort als eigene Datei
nach daten/historie/. Ein erneuter Start ueberspringt alles, was schon da
liegt. Es gibt keinen Zustand im Arbeitsspeicher, der verloren gehen
koennte, und keinen Lauf, der von vorn beginnen muss.

    python skripte/gdelt_historie.py --von 2023-02-01
    python skripte/gdelt_historie.py --von 2023-02-01 --codes TU,BR,SF,IN,MX,EG
    python skripte/gdelt_historie.py --einspielen      # in den Bestand uebernehmen

Der letzte Aufruf fuehrt die Tagesdateien in gdelt_tagesaggregate.csv
zusammen. Bestehende Zeilen desselben Tages und Landes werden ersetzt.
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
import io
import re
import sys
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import GDELT_MASTER, ESKALATION, LAENDER
from aktualisieren import KEEP_FEST, geo_indizes, holen, url_spalte
from gdelt_filter import zeilen_filtern

WURZEL = Path(__file__).resolve().parent.parent
DATEN = WURZEL / "daten"
HIST = DATEN / "historie"
SPALTEN = ["date", "code", "n_events", "tone_sum", "tone_cnt"] + [f"n_{r}" for r in ESKALATION]


def log(m):
    print(m, flush=True)


def masterliste() -> dict[str, list[str]]:
    """Die Masterliste ist rund 100 MB. Sie wird einmal geholt und gepuffert."""
    puffer = DATEN / "masterfilelist.txt"
    if puffer.exists() and (time.time() - puffer.stat().st_mtime) < 6 * 3600:
        roh = puffer.read_bytes()
        log(f"[INFO] Masterliste aus Puffer ({len(roh)/1e6:.0f} MB)")
    else:
        log("[INFO] Masterliste laden ...")
        roh = holen(GDELT_MASTER, timeout=600)
        if roh is None:
            log("[FEHLER] Masterliste nicht erreichbar")
            raise SystemExit(1)
        puffer.write_bytes(roh)
    pat = re.compile(r"(\S+/(\d{14})\.export\.CSV\.zip)")
    nach_tag = defaultdict(list)
    for zeile in roh.decode(errors="ignore").splitlines():
        m = pat.search(zeile)
        if m:
            nach_tag[m.group(2)[:8]].append(m.group(1))
    return nach_tag


def tag_verarbeiten(tag: str, urls: list[str], ziel: set[str]
                    ) -> tuple[pd.DataFrame, float]:
    """Verdichtet einen Tag. Zweiter Rueckgabewert: die Erntequote.

    Die Quote ist der Anteil der 96 Viertelstundendateien, die wirklich
    gelesen wurden. Sie ist noetig, weil ein Tag sonst auch dann als fertig
    gilt, wenn gar nichts angekommen ist: beim vollstaendigen Neuladen blieben
    108 Tagesdateien leer, wurden aber geschrieben und im Manifest als erledigt
    vermerkt -- ein erneuter Lauf haette sie nie wieder angefasst.
    """
    liste = sorted(set(urls))
    # Vier Faeden statt acht, fuenf Versuche statt drei.
    #
    # Gemessener Anlass: derselbe Tag, zweimal geladen, zwei Ergebnisse.
    # Deutschland am 08.09.2026 -- in der Sitzung vom 09.09. 1.883 Ereignisse,
    # in der Sitzung vom 13.09. fuer benachbarte Tage nur 120 bis 437, bei
    # identischer Masterliste mit 96 Dateien je Tag. Das Niveau haing also
    # daran, WANN geladen wurde, nicht am Kalender: mit acht parallelen
    # Abrufen scheiterten Einzeldateien, und der Fehlschlag wurde stillschweigend
    # uebersprungen. Die Quote unten macht ihn sichtbar, die geringere
    # Parallelitaet seltener.
    with ThreadPoolExecutor(max_workers=4) as ex:
        rohe = list(ex.map(lambda u: holen(u, versuche=5), liste))
    quote = (sum(1 for r in rohe if r is not None) / len(liste)) if liste else 0.0
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
                        treffer = g.isin(ziel).any(axis=1)
                        if not treffer.any():
                            continue
                        us = url_spalte(chunk, n)
                        sub = chunk.loc[treffer, KEEP_FEST + ([us] if us else [])].copy()
                        sub = sub.rename(columns={us: "surl"}) if us else sub.assign(surl="")
                        sub["G1"], sub["G2"], sub["G3"] = (g.loc[treffer].iloc[:, 0],
                                                           g.loc[treffer].iloc[:, 1],
                                                           g.loc[treffer].iloc[:, 2])
                        teile.append(sub)
        except Exception:
            continue
    if not teile:
        return pd.DataFrame(columns=SPALTEN), quote

    d = pd.concat(teile, ignore_index=True)
    d["date"] = pd.to_datetime(d.C1, format="%Y%m%d", errors="coerce")
    d["root"] = pd.to_numeric(d.C28, errors="coerce")
    d["tone"] = pd.to_numeric(d.C34, errors="coerce")
    d = d.dropna(subset=["date"])
    # Nur Ereignisse DIESES Tages. C1 ist das Ereignisdatum; die Datei enthaelt
    # auch Rueckblicke auf weit zurueckliegende Ereignisse.
    d = d[d.date == pd.Timestamp(tag)]
    if d.empty:
        return pd.DataFrame(columns=SPALTEN), quote

    geo = d[["G1", "G2", "G3"]]
    zeilen = []
    for code in ziel:
        roh = d.loc[geo.eq(code).any(axis=1)]
        if roh.empty:
            continue
        # Dieselbe Verengung wie im Tageslauf: Handlungsort im Land, ein
        # Akteur des Landes, Duplikate je Quelle entfernt. Beide Wege muessen
        # denselben Filter verwenden, sonst hat die Reihe an der Nahtstelle
        # zwischen Historie und Tageslauf einen Sprung -- genau der Fehler,
        # den der Filterwechsel gerade behebt.
        t = zeilen_filtern(roh, code)
        if t.empty:
            continue
        r = {"date": pd.Timestamp(tag), "code": code, "n_events": len(t),
             "tone_sum": float(t.tone.sum()), "tone_cnt": int(t.tone.notna().sum())}
        for rc in ESKALATION:
            r[f"n_{rc}"] = int((t.root == rc).sum())
        zeilen.append(r)
    return pd.DataFrame(zeilen, columns=SPALTEN), quote


# Welche Laender ein bereits geladener Tag abdeckt.
#
# Der Wiederaufsetzpunkt war urspruenglich allein die Existenz der Tagesdatei.
# Das war falsch, sobald --codes ins Spiel kam: nach der Aufnahme von Malaysia,
# Indonesien, Spanien und Saudi-Arabien meldete der Lauf "1294 bereits
# vorhanden" und lud nur die sechs fehlenden Tage -- die 1294 Dateien
# existierten ja, enthielten die vier neuen Laender aber nicht. Ein Tag gilt
# deshalb jetzt erst dann als erledigt, wenn er die ANGEFRAGTEN Laender
# abdeckt.
#
# Die Abdeckung steht in einem Manifest neben den Tagesdateien, weil sie sich
# nicht zuverlaessig aus dem Inhalt ablesen laesst: ein Land ohne Ereignisse an
# diesem Tag erzeugt keine Zeile. Ohne Manifest waere ein solcher Tag fuer
# dieses Land dauerhaft "offen" und wuerde bei jedem Lauf erneut geladen.
ABDECKUNG = HIST / "_abdeckung.json"

# Mindestanteil der 96 Viertelstundendateien, den ein Tag erreichen muss, um
# als geladen zu gelten. Darunter wird er beim naechsten Lauf erneut geholt.
MIN_QUOTE = 0.95


def abdeckung_lesen() -> dict[str, list[str]]:
    if ABDECKUNG.exists():
        try:
            return json.loads(ABDECKUNG.read_text())
        except Exception:
            log("[WARN] _abdeckung.json unlesbar -- wird neu aufgebaut")
    return {}


def abdeckung_schreiben(abd: dict[str, list[str]]) -> None:
    ABDECKUNG.write_text(json.dumps(abd, separators=(",", ":"), sort_keys=True))


def abdeckung_ableiten(tag: str) -> list[str]:
    """Ersatzangabe fuer Tagesdateien aus der Zeit vor dem Manifest."""
    f = HIST / f"{tag}.csv"
    if not f.exists():
        return []
    try:
        return sorted(pd.read_csv(f, sep=";", usecols=["code"]).code.dropna().unique())
    except Exception:
        return []


def tag_speichern(tag: str, df: pd.DataFrame, ziel: set[str],
                  abd: dict, quote: float = 1.0) -> None:
    """Schreibt einen Tag, ohne bereits vorhandene Laender zu verlieren.

    Frueher wurde die Tagesdatei ueberschrieben. Wer danach mit --codes einen
    Teilbestand nachlud, loeschte damit alle uebrigen Laender aus dieser Datei
    -- unbemerkt, weil der Gesamtbestand aus dem taeglichen Lauf noch stimmte.
    """
    f = HIST / f"{tag}.csv"
    if f.exists():
        alt = pd.read_csv(f, sep=";", parse_dates=["date"])
        behalten = alt[~alt.code.isin(ziel)]
        df = pd.concat([behalten, df], ignore_index=True) if len(behalten) else df
    df.sort_values("code").to_csv(f, index=False, sep=";")
    # Im Manifest stehen jetzt Laender UND Erntequote. Die alte Form (eine
    # blosse Liste) bleibt lesbar, damit vorhandene Manifeste weiter gelten.
    vorher = abd.get(tag)
    laender = sorted(set((vorher.get("laender") if isinstance(vorher, dict) else vorher)
                         or abdeckung_ableiten(tag)) | ziel)
    abd[tag] = {"laender": laender, "quote": round(float(quote), 3)}


def einspielen() -> int:
    dateien = sorted(HIST.glob("*.csv"))
    if not dateien:
        log("[FEHLER] Keine Tagesdateien in daten/historie/")
        return 1
    neu = pd.concat([pd.read_csv(f, sep=";", parse_dates=["date"]) for f in dateien],
                    ignore_index=True)
    # Welche TAGE neu geladen wurden -- unabhaengig davon, ob an ihnen
    # Ereignisse gefunden wurden. Das ist der Unterschied, an dem der erste
    # Versuch gescheitert ist: 108 Tagesdateien waren leer, die Zeile
    # "neu[n_events > 0]" liess sie verschwinden, und damit blieben im Bestand
    # die ALTEN, ungefilterten Zeilen dieser Tage stehen. Der Bestand hatte
    # dadurch zwei Niveaus -- fuer die USA 43.721 Ereignisse im Februar 2026
    # gegen 12.374 im Mai, ein Faktor von 3,5, der nach Nachrichtenlage aussah
    # und nur die Handschrift zweier Filterfassungen war.
    geladene_tage = set(neu.date.unique())
    neu = neu[neu.n_events > 0]
    ziel = DATEN / "gdelt_tagesaggregate.csv"
    alt = pd.read_csv(ziel, sep=";", parse_dates=["date"]) if ziel.exists() else pd.DataFrame()
    if len(alt):
        ziel.with_suffix(".csv.bak").write_bytes(ziel.read_bytes())
    # Alte Zeilen GEZIELT entfernen, statt sich auf die Reihenfolge zu verlassen.
    #
    # Hier stand sort_values("date").drop_duplicates(..., keep="last"). Das sah
    # richtig aus und war es nicht: pandas sortiert standardmaessig instabil
    # (quicksort), also ist die Reihenfolge zweier Zeilen mit DEMSELBEN Datum
    # unbestimmt -- und "keep last" behielt mal die neue, mal die alte. Nach dem
    # vollstaendigen Neuladen der Historie stand deshalb fuer den 10.06.2026 im
    # Bestand 1.596 Ereignisse fuer Deutschland, in der Tagesdatei 303. Der
    # Filterwechsel war damit nur auf einem Teil der Tage angekommen -- also
    # genau der Sprung in der Reihe, den das Neuladen beseitigen sollte, nur
    # jetzt unregelmaessig ueber den Zeitraum verteilt statt an einer Stelle.
    if len(alt):
        # Erst alles aus den neu geladenen TAGEN entfernen ...
        vorher_tage = len(alt)
        alt = alt[~alt.date.isin(geladene_tage)]
        if vorher_tage - len(alt):
            log(f"[INFO] {vorher_tage - len(alt):,} Zeilen aus neu geladenen Tagen entfernt")
    if len(alt):
        # ... dann zur Sicherheit noch einzelne Land-Tag-Treffer.
        schluessel = set(zip(neu.date, neu.code))
        vorher = len(alt)
        alt = alt[~pd.Series(list(zip(alt.date, alt.code)), index=alt.index).isin(schluessel)]
        log(f"[INFO] {vorher - len(alt):,} alte Zeilen durch neu geladene ersetzt")
    ges = pd.concat([alt, neu], ignore_index=True)
    ges = ges.drop_duplicates(["date", "code"], keep="last")
    ges.sort_values(["date", "code"]).to_csv(ziel, index=False, sep=";")
    log(f"[OK] {len(dateien)} Tagesdateien eingespielt -> {len(ges):,} Zeilen")
    log(ges.groupby("code").agg(n=("date", "size"), von=("date", "min"),
                                bis=("date", "max")).to_string())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--von", default="2023-02-01")
    ap.add_argument("--bis", default=None)
    ap.add_argument("--codes", default=",".join(LAENDER))
    ap.add_argument("--einspielen", action="store_true")
    a = ap.parse_args()
    HIST.mkdir(parents=True, exist_ok=True)
    if a.einspielen:
        return einspielen()

    ziel = {c.strip().upper() for c in a.codes.split(",") if c.strip()}
    von = dt.date.fromisoformat(a.von)
    bis = dt.date.fromisoformat(a.bis) if a.bis else dt.date.today()
    log(f"[INFO] Zeitraum {von} bis {bis} | Laender: {sorted(ziel)}")

    nach_tag = masterliste()
    tage = [t for t in sorted(nach_tag)
            if von.strftime("%Y%m%d") <= t <= bis.strftime("%Y%m%d")]
    abd = abdeckung_lesen()
    def erledigt(t: str) -> bool:
        if not (HIST / f"{t}.csv").exists():
            return False
        e = abd.get(t)
        if isinstance(e, dict):
            # Ein Tag mit schlechter Ernte gilt NICHT als erledigt, auch wenn
            # die Tagesdatei existiert und alle Laender vermerkt sind.
            if e.get("quote", 0) < MIN_QUOTE:
                return False
            vorhanden = set(e.get("laender") or [])
        else:
            vorhanden = set(e or abdeckung_ableiten(t))
        return ziel <= vorhanden
    offen = [t for t in tage if not erledigt(t)]
    log(f"[INFO] {len(tage)} Tage im Zeitraum, {len(tage)-len(offen)} für diese "
        f"Länder bereits abgedeckt, {len(offen)} offen")
    if not offen:
        log("[OK] Nichts zu tun. Mit --einspielen uebernehmen.")
        return 0

    start = time.time()
    for i, tag in enumerate(offen, 1):
        t0 = time.time()
        try:
            df, quote = tag_verarbeiten(tag, nach_tag[tag], ziel)
        except KeyboardInterrupt:
            abdeckung_schreiben(abd)
            log("\n[ABBRUCH] Fertige Tage bleiben erhalten. Erneut starten "
                "setzt an dieser Stelle fort.")
            return 130
        # Auch ein leerer Tag wird geschrieben, sonst wird er bei jedem
        # Neustart erneut geladen.
        tag_speichern(tag, df, ziel, abd, quote)
        if i % 25 == 0 or i == len(offen):
            abdeckung_schreiben(abd)
        verstrichen = time.time() - start
        rest = verstrichen / i * (len(offen) - i)
        log(f"  [{i:>4}/{len(offen)}] {tag}: {len(df)} Laender, "
            f"{df.n_events.sum() if len(df) else 0:>7,} Ereignisse, "
            f"Ernte {quote*100:.0f} %"
            + ("  [WARN] wird erneut geholt" if quote < MIN_QUOTE else "")
            + f" ({time.time()-t0:.0f}s, Rest ca. {rest/3600:.1f} h)")
    log(f"\n[FERTIG] {len(offen)} Tage in {(time.time()-start)/3600:.1f} h")
    log("Jetzt uebernehmen:  python skripte/gdelt_historie.py --einspielen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
