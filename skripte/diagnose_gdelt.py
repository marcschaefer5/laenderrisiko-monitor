"""Zerlegt EINE GDELT-Datei Schritt fuer Schritt.

Der Produktivlauf meldet nur "keine verwertbaren Zeilen". Das kann drei
Ursachen haben: zu wenige Spalten, falsche Geo-Positionen, oder ein
Laendercode-Format, das nicht mehr zu TARGET passt. Raten hilft hier nicht.
"""
import io
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import GDELT_MASTER, LAENDER
from aktualisieren import geo_indizes, holen, url_spalte

master = holen(GDELT_MASTER, timeout=180)
if master is None:
    print("Masterliste nicht erreichbar"); raise SystemExit(1)
pfad = None
for z in master.decode(errors="ignore").splitlines():
    m = re.search(r"(\S+/\d{14}\.export\.CSV\.zip)", z)
    if m:
        pfad = m.group(1)
print("Datei:", pfad)

roh = holen(pfad)
print("Bytes:", len(roh) if roh else None)
with zipfile.ZipFile(io.BytesIO(roh)) as zf:
    name = next(m for m in zf.namelist() if m.lower().endswith(".csv"))
    with zf.open(name) as f:
        chunk = pd.read_csv(f, sep="\t", header=None, dtype=str,
                            low_memory=False, on_bad_lines="skip")
n = chunk.shape[1]
chunk.columns = [f"C{i}" for i in range(n)]
print(f"Zeilen: {len(chunk)}   SPALTEN: {n}   (erwartet wurden 61)")

a1, a2, ac = geo_indizes(n)
print(f"geo_indizes({n}) -> {a1}, {a2}, {ac}")
for i in (a1, a2, ac):
    w = chunk[f"C{i}"].dropna().astype(str)
    print(f"  C{i}: {Counter(w).most_common(6)}")

print("\nSpalten 35-58 (Geo-Bereich), je 4 haeufigste Werte:")
for i in range(35, min(59, n)):
    w = chunk[f"C{i}"].dropna().astype(str)
    if not len(w):
        continue
    print(f"  C{i}: {[x for x, _ in Counter(w).most_common(4)]}")

print("\nSpalten, die 2-stellige Grossbuchstaben-Codes enthalten "
      "und mindestens einen Zielcode treffen:")
ziel = set(LAENDER)
for i in range(n):
    w = chunk[f"C{i}"].dropna().astype(str)
    if not len(w):
        continue
    tr = w.isin(ziel).sum()
    if tr:
        print(f"  C{i}: {tr} Treffer  z.B. {[x for x,_ in Counter(w[w.isin(ziel)]).most_common(5)]}")

print("\nURL-Spalte laut url_spalte():", url_spalte(chunk, n))
print("letzte Spalte C%d, Beispiel: %s" % (n - 1, str(chunk[f"C{n-1}"].dropna().iloc[0])[:120]))
