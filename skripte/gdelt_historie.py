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


def tag_verarbeiten(tag: str, urls: list[str], ziel: set[str]) -> pd.DataFrame:
    with ThreadPoolExecutor(max_workers=8) as ex:
        rohe = list(ex.map(holen, sorted(set(urls))))
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
        return pd.DataFrame(columns=SPALTEN)

    d = pd.concat(teile, ignore_index=True)
    d["date"] = pd.to_datetime(d.C1, format="%Y%m%d", errors="coerce")
    d["root"] = pd.to_numeric(d.C28, errors="coerce")
    d["tone"] = pd.to_numeric(d.C34, errors="coerce")
    d = d.dropna(subset=["date"])
    # Nur Ereignisse DIESES Tages. C1 ist das Ereignisdatum; die Datei enthaelt
    # auch Rueckblicke auf weit zurueckliegende Ereignisse.
    d = d[d.date == pd.Timestamp(tag)]
    if d.empty:
        return pd.DataFrame(columns=SPALTEN)

    geo = d[["G1", "G2", "G3"]]
    zeilen = []
    for code in ziel:
        t = d.loc[geo.eq(code).any(axis=1)]
        if t.empty:
            continue
        r = {"date": pd.Timestamp(tag), "code": code, "n_events": len(t),
             "tone_sum": float(t.tone.sum()), "tone_cnt": int(t.tone.notna().sum())}
        for rc in ESKALATION:
            r[f"n_{rc}"] = int((t.root == rc).sum())
        zeilen.append(r)
    return pd.DataFrame(zeilen, columns=SPALTEN)


def einspielen() -> int:
    dateien = sorted(HIST.glob("*.csv"))
    if not dateien:
        log("[FEHLER] Keine Tagesdateien in daten/historie/")
        return 1
    neu = pd.concat([pd.read_csv(f, sep=";", parse_dates=["date"]) for f in dateien],
                    ignore_index=True)
    neu = neu[neu.n_events > 0]
    ziel = DATEN / "gdelt_tagesaggregate.csv"
    alt = pd.read_csv(ziel, sep=";", parse_dates=["date"]) if ziel.exists() else pd.DataFrame()
    if len(alt):
        ziel.with_suffix(".csv.bak").write_bytes(ziel.read_bytes())
    ges = pd.concat([alt, neu], ignore_index=True)
    ges = ges.sort_values("date").drop_duplicates(["date", "code"], keep="last")
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
    offen = [t for t in tage if not (HIST / f"{t}.csv").exists()]
    log(f"[INFO] {len(tage)} Tage im Zeitraum, {len(tage)-len(offen)} bereits vorhanden, "
        f"{len(offen)} offen")
    if not offen:
        log("[OK] Nichts zu tun. Mit --einspielen uebernehmen.")
        return 0

    start = time.time()
    for i, tag in enumerate(offen, 1):
        t0 = time.time()
        try:
            df = tag_verarbeiten(tag, nach_tag[tag], ziel)
        except KeyboardInterrupt:
            log("\n[ABBRUCH] Fertige Tage bleiben erhalten. Erneut starten "
                "setzt an dieser Stelle fort.")
            return 130
        # Auch ein leerer Tag wird geschrieben, sonst wird er bei jedem
        # Neustart erneut geladen.
        df.to_csv(HIST / f"{tag}.csv", index=False, sep=";")
        verstrichen = time.time() - start
        rest = verstrichen / i * (len(offen) - i)
        log(f"  [{i:>4}/{len(offen)}] {tag}: {len(df)} Laender, "
            f"{df.n_events.sum() if len(df) else 0:>7,} Ereignisse "
            f"({time.time()-t0:.0f}s, Rest ca. {rest/3600:.1f} h)")
    log(f"\n[FERTIG] {len(offen)} Tage in {(time.time()-start)/3600:.1f} h")
    log("Jetzt uebernehmen:  python skripte/gdelt_historie.py --einspielen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
