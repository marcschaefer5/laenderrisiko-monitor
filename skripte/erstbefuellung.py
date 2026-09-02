"""
erstbefuellung.py -- einmaliger Transfer der vorhandenen Daten ins Monitor-Repo.

Uebernimmt aus der Bachelorarbeit, was der taegliche Lauf sonst erst ueber
Monate aufbauen muesste:
  - GDELT-Tagesaggregate (3,6 Jahre) aus dem Cache von D36
  - Wechselkurse und Aktienindizes aus D35
  - den GPR-Index

Danach ist der Monitor sofort mit voller Historie lauffaehig; der taegliche
Lauf haengt nur noch die neuen Tage an. Laender ohne vorhandene Marktreihe
(die Erweiterung um Tuerkei, Brasilien und weitere) holt der erste
taegliche Lauf selbst nach.

Aufruf einmalig:  python3 skripte/erstbefuellung.py
"""
from pathlib import Path
import shutil
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import LAENDER, ESKALATION

MONITOR = Path(__file__).resolve().parent.parent
ARBEIT = MONITOR.parent
DATEN = MONITOR / "daten"
DATEN.mkdir(exist_ok=True)

CACHE = ARBEIT / "ml_trainingsergebnisse/_daily_country_risk/gdelt_tagesmerkmale_cache.csv"
RISK = ARBEIT / "Datengrundlage/risk_inputs"
GPR = ARBEIT / "Datengrundlage/external_targets/data_gpr_daily_recent.xls"

# Der Cache aus D36 benennt die Eskalationsspalten nach Klartext,
# der taegliche Lauf nach Rootcode. Hier wird umbenannt.
NAME_ZU_CODE = {v.lower(): k for k, v in ESKALATION.items()}


def main() -> int:
    if not CACHE.exists():
        print(f"[FEHLER] {CACHE} fehlt. Erst D36 ausfuehren."); return 1

    g = pd.read_csv(CACHE, sep=";", parse_dates=["date"])
    umbenennen = {}
    for spalte in g.columns:
        if spalte.startswith("n_"):
            rest = spalte[2:].lower()
            if rest in NAME_ZU_CODE:
                umbenennen[spalte] = f"n_{NAME_ZU_CODE[rest]}"
    g = g.rename(columns=umbenennen)
    behalten = ["date", "code", "n_events", "tone_sum", "tone_cnt"] + \
               [f"n_{rc}" for rc in ESKALATION if f"n_{rc}" in g.columns]
    g = g[[c for c in behalten if c in g.columns]]
    g = g[g.code.isin(LAENDER)]
    g.to_csv(DATEN / "gdelt_tagesaggregate.csv", index=False, sep=";")
    print(f"GDELT-Aggregate: {len(g):,} Zeilen, {g.code.nunique()} Länder, "
          f"{g.date.min().date()} bis {g.date.max().date()}")

    n = 0
    for datei in sorted(RISK.glob("*.csv")):
        if datei.name == "qualitaetsbericht.csv":
            continue
        code = datei.stem.split("_")[-1]
        if code in LAENDER:
            shutil.copy2(datei, DATEN / datei.name)
            n += 1
    print(f"Marktreihen übernommen: {n}")

    if GPR.exists():
        shutil.copy2(GPR, DATEN / "gpr.xls")
        print("GPR-Index übernommen")

    fehlend = [LAENDER[c][0] for c in LAENDER
               if LAENDER[c][1] and not (DATEN / f"fx_{c}.csv").exists()]
    if fehlend:
        print(f"\nOhne Marktreihe (holt der erste tägliche Lauf): {', '.join(fehlend)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
