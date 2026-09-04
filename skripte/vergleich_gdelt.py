"""Traegt GDELT etwas zur Tagesprognose bei? -- der ehrliche Test.

Fragestellung der Bachelorarbeit, aber mit sauberem Design:

  Zielvariable   liegt der MARKTBASIERTE Risikoindex eines Landes in
                 H Handelstagen mindestens SCHWELLE Standardabweichungen
                 ueber seinem eigenen 120-Tage-Mittel?
  Merkmale       einmal nur Markt, einmal nur GDELT, einmal beides.

Warum das der Zirkelschluss-Kritik entgeht: Ziel und GDELT-Merkmale stammen
aus voellig getrennten Datenquellen. Das Ziel kommt aus Wechselkursen und
Aktienindizes, die Merkmale aus Ereignismeldungen. Es gibt keine
Transformation, die das eine ins andere ueberfuehrt -- anders als in der
urspruenglichen Arbeit, wo das Label eine Funktion der Ereigniszaehlung war.

Vier Modelle, bewusst inklusive Nullmodellen:

  M0  Persistenz      Score = heutiges z. Null Parameter, nichts gelernt.
                      Der Vergleichsmassstab, dessen Fehlen kritisiert wurde.
  M1  Markt           z, dz, dr1, dr5  -- die Fortschreibung des Index selbst.
  M2  GDELT           nur Ereignismerkmale. Das ist das Modell der Arbeit.
  M3  Kombiniert      Markt + GDELT.

Bewertet wird streng zeitgeordnet: Trainiert wird auf allem, was VOR dem
Bewertungsblock liegt, vorhergesagt wird der naechste Block, dann wandert
das Fenster weiter (expanding window). Kein Shuffle, keine Zukunft im
Training. Alle vier Modelle werden auf EXAKT denselben Tagen bewertet,
sonst ist der AUC-Vergleich wertlos.

Die entscheidende Zahl ist nicht der AUC von M2, sondern

  Delta = AUC(M3) - AUC(M1)

also der Zugewinn DURCH GDELT ueber das hinaus, was der Index ohnehin
ueber sich selbst weiss -- mit gepaartem Bootstrap-Konfidenzintervall.
Schliesst das Intervall die Null ein, ist kein Beitrag nachweisbar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import LAENDER, NORM_FENSTER, PROGNOSE_HORIZONT, PROGNOSE_SCHWELLE
from gdelt_merkmale import (MERKMALE, MERKMALE_GLATT, gdelt_merkmale)
import aktualisieren as akt

WURZEL = Path(__file__).resolve().parent.parent
DATEN = WURZEL / "daten"
M_MERKMALE = ["z", "z_d1", "r_d1", "r_d5"]
START_ANTEIL = 0.5     # erster Trainingsblock
BLOCK = 20             # Bewertungsblock in Handelstagen
BOOT = 2000


def oof(X: pd.DataFrame, y: np.ndarray) -> np.ndarray:
    """Out-of-fold-Vorhersagen im expandierenden Zeitfenster."""
    p = np.full(len(y), np.nan)
    start = int(len(y) * START_ANTEIL)
    for a in range(start, len(y), BLOCK):
        b = min(a + BLOCK, len(y))
        ytr = y[:a]
        if len(np.unique(ytr)) < 2:
            continue
        sc = StandardScaler().fit(X.iloc[:a])
        m = LogisticRegression(max_iter=4000, class_weight="balanced")
        m.fit(sc.transform(X.iloc[:a]), ytr)
        p[a:b] = m.predict_proba(sc.transform(X.iloc[a:b]))[:, 1]
    return p


def boot_delta(y: np.ndarray, pa: np.ndarray, pb: np.ndarray,
               rng: np.random.Generator) -> tuple[float, float]:
    """Gepaartes Bootstrap-KI fuer AUC(pb) - AUC(pa) auf denselben Tagen."""
    d = []
    n = len(y)
    for _ in range(BOOT):
        i = rng.integers(0, n, n)
        if len(np.unique(y[i])) < 2:
            continue
        d.append(roc_auc_score(y[i], pb[i]) - roc_auc_score(y[i], pa[i]))
    return (float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))) if d else (np.nan, np.nan)


def main() -> int:
    glatt = "--glatt" in sys.argv
    G_MERKMALE = MERKMALE_GLATT if glatt else MERKMALE
    print(f"Merkmalsvariante: {'geglaettet' if glatt else 'roh'} "
          f"({len(G_MERKMALE)} GDELT-Merkmale)\n")
    gpr = pd.read_excel(DATEN / "gpr.xls")[["date", "GPRD"]].rename(columns={"GPRD": "gpr"})
    gpr["date"] = pd.to_datetime(gpr.date)
    gpr["geopolitik"] = (gpr.gpr - gpr.gpr.mean()) / gpr.gpr.std()
    gpr = gpr[["date", "geopolitik"]]

    gd = pd.read_csv(DATEN / "gdelt_tagesaggregate.csv", sep=";", parse_dates=["date"])
    rng = np.random.default_rng(20260902)
    zeilen = []

    for code, (name, _, _) in LAENDER.items():
        g = gd[gd.code == code]
        if len(g) < 400:
            print(f"[UEBERSPRUNGEN] {name}: nur {len(g)} GDELT-Tage")
            continue
        d = akt.risikoreihe(code, gpr)
        if d is None or len(d) < 400:
            print(f"[UEBERSPRUNGEN] {name}: Risikoreihe zu kurz")
            continue

        mu = d.risiko.rolling(NORM_FENSTER, min_periods=60).mean()
        sd = d.risiko.rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
        d["z"] = (d.risiko - mu) / sd
        d["z_d1"] = d.z.diff(); d["r_d1"] = d.risiko.diff(); d["r_d5"] = d.risiko.diff(5)
        d["y"] = (d.z.shift(-PROGNOSE_HORIZONT) >= PROGNOSE_SCHWELLE).astype(float)

        d = d.merge(gdelt_merkmale(g, glatt), on="date", how="left")
        alle = M_MERKMALE + G_MERKMALE
        d = d.dropna(subset=alle + ["y"]).reset_index(drop=True)
        if len(d) < 400 or d.y.nunique() < 2:
            print(f"[UEBERSPRUNGEN] {name}: {len(d)} gemeinsame Tage")
            continue

        y = d.y.to_numpy()
        p = {"M1 Markt": oof(d[M_MERKMALE], y),
             "M2 GDELT": oof(d[G_MERKMALE], y),
             "M3 Kombi": oof(d[alle], y)}
        p["M0 Persistenz"] = d.z.to_numpy()

        gilt = ~np.isnan(p["M1 Markt"]) & ~np.isnan(p["M2 GDELT"]) & ~np.isnan(p["M3 Kombi"])
        yy = y[gilt]
        if len(np.unique(yy)) < 2:
            print(f"[UEBERSPRUNGEN] {name}: Bewertungsfenster einklassig")
            continue
        auc = {k: roc_auc_score(yy, v[gilt]) for k, v in p.items()}

        lo_g, hi_g = boot_delta(yy, p["M1 Markt"][gilt], p["M3 Kombi"][gilt], rng)
        lo_m, hi_m = boot_delta(yy, p["M0 Persistenz"][gilt], p["M1 Markt"][gilt], rng)

        zeilen.append({"land": name, "tage": int(gilt.sum()),
                       "basisrate": round(float(yy.mean()), 3),
                       **{k: round(v, 3) for k, v in auc.items()},
                       "d_gdelt": round(auc["M3 Kombi"] - auc["M1 Markt"], 3),
                       "ki_lo": round(lo_g, 3), "ki_hi": round(hi_g, 3),
                       "d_markt": round(auc["M1 Markt"] - auc["M0 Persistenz"], 3),
                       "ki_markt_lo": round(lo_m, 3), "ki_markt_hi": round(hi_m, 3)})
        z = zeilen[-1]
        print(f"{name:<12} n={z['tage']:>4} Basis={z['basisrate']:.3f} | "
              f"M0={z['M0 Persistenz']:.3f} M1={z['M1 Markt']:.3f} "
              f"M2={z['M2 GDELT']:.3f} M3={z['M3 Kombi']:.3f} | "
              f"GDELT-Beitrag {z['d_gdelt']:+.3f} [{z['ki_lo']:+.3f}, {z['ki_hi']:+.3f}]")

    if not zeilen:
        print("Keine auswertbaren Laender.")
        return 1
    t = pd.DataFrame(zeilen)
    ziel = WURZEL / "daten" / ("vergleich_gdelt_glatt.csv" if glatt else "vergleich_gdelt.csv")
    t.to_csv(ziel, index=False, sep=";")
    print()
    print(f"Laender mit GDELT-Beitrag > 0 (Punktschaetzer): "
          f"{int((t.d_gdelt > 0).sum())} von {len(t)}")
    print(f"davon signifikant (KI schliesst 0 aus):        "
          f"{int((t.ki_lo > 0).sum())}")
    print(f"Median GDELT-Beitrag: {t.d_gdelt.median():+.3f}   "
          f"Median Markt-Beitrag ueber Persistenz: {t.d_markt.median():+.3f}")
    print(f"[OK] {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
