"""Liegt der Nullbefund an der logistischen Regression?

Alle bisherigen 75 Konstellationen benutzen dieselbe Modellklasse. Damit ist
streng genommen nur gezeigt: EIN LOGISTISCHES MODELL findet in den
GDELT-Merkmalen nichts. Der naheliegende Einwand lautet:

    "Die logistische Regression bildet nur lineare Zusammenhaenge in den
    Log-Odds ab. Ein Ereigniseffekt koennte nichtlinear wirken -- erst ab
    einer Schwelle, oder nur im Zusammenspiel von Gewaltanteil und Ton."

Der Einwand ist berechtigt und laesst sich beantworten, ohne neue Daten:
dieselben Tage, dieselbe zeitgeordnete Validierung, dieselben Merkmale --
zusaetzlich mit Gradient Boosting, das Schwellenwerte und Wechselwirkungen
von sich aus findet.

Findet auch das nichts, liegt es nicht an der Modellklasse.

Zwei Vergleiche werden ausgewiesen:

  1. Traegt GDELT unter dem NICHTLINEAREN Modell etwas bei?
     Delta = AUC(GB, Markt+GDELT) - AUC(GB, nur Markt), gepaartes Bootstrap-KI.
  2. Ist das GDELT-Modell unter Gradient Boosting ueberhaupt besser als
     unter logistischer Regression? Also: gibt es Struktur, die die lineare
     Form uebersieht?

Bewusst konservativ parametriert (flache Baeume, kleine Lernrate,
Regularisierung): bei rund 500 Beobachtungen je Land wuerde ein tiefes
Modell nur das Trainingsrauschen auswendig lernen und out-of-sample
schlechter abschneiden -- was den Test wertlos machen wuerde, weil man den
Nullbefund dann der Ueberanpassung zuschreiben koennte.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import LAENDER, NORM_FENSTER, PROGNOSE_HORIZONT, PROGNOSE_SCHWELLE
from gdelt_merkmale import MERKMALE as G_MERKMALE, gdelt_merkmale
from vergleich_gdelt import BLOCK, BOOT, M_MERKMALE, START_ANTEIL, boot_delta
import aktualisieren as akt

WURZEL = Path(__file__).resolve().parent.parent
DATEN = WURZEL / "daten"


def gb():
    return HistGradientBoostingClassifier(
        max_iter=200, max_depth=3, learning_rate=0.05,
        min_samples_leaf=20, l2_regularization=1.0,
        early_stopping=False, random_state=0)


def oof(X: pd.DataFrame, y: np.ndarray, art: str) -> np.ndarray:
    """Out-of-fold im expandierenden Fenster -- identisch fuer beide Klassen."""
    p = np.full(len(y), np.nan)
    for a in range(int(len(y) * START_ANTEIL), len(y), BLOCK):
        b = min(a + BLOCK, len(y))
        ytr = y[:a]
        if len(np.unique(ytr)) < 2:
            continue
        if art == "lr":
            sc = StandardScaler().fit(X.iloc[:a])
            m = LogisticRegression(max_iter=4000, class_weight="balanced")
            m.fit(sc.transform(X.iloc[:a]), ytr)
            p[a:b] = m.predict_proba(sc.transform(X.iloc[a:b]))[:, 1]
        else:
            # Baeume brauchen keine Skalierung; die Gewichtung ersetzt
            # class_weight="balanced", das HistGradientBoosting nicht kennt.
            m = gb().fit(X.iloc[:a], ytr,
                         sample_weight=compute_sample_weight("balanced", ytr))
            p[a:b] = m.predict_proba(X.iloc[a:b])[:, 1]
    return p


def main() -> int:
    gpr = pd.read_excel(DATEN / "gpr.xls")[["date", "GPRD"]].rename(columns={"GPRD": "gpr"})
    gpr["date"] = pd.to_datetime(gpr.date)
    gpr["geopolitik"] = (gpr.gpr - gpr.gpr.mean()) / gpr.gpr.std()
    gpr = gpr[["date", "geopolitik"]]
    gd = pd.read_csv(DATEN / "gdelt_tagesaggregate.csv", sep=";", parse_dates=["date"])
    rng = np.random.default_rng(20260904)
    zeilen = []

    for code, (name, _, _) in LAENDER.items():
        g = gd[gd.code == code]
        d = akt.risikoreihe(code, gpr)
        if len(g) < 400 or d is None or len(d) < 400:
            print(f"[UEBERSPRUNGEN] {name}")
            continue
        mu = d.risiko.rolling(NORM_FENSTER, min_periods=60).mean()
        sd = d.risiko.rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
        d["z"] = (d.risiko - mu) / sd
        d["z_d1"] = d.z.diff(); d["r_d1"] = d.risiko.diff(); d["r_d5"] = d.risiko.diff(5)
        d["y"] = (d.z.shift(-PROGNOSE_HORIZONT) >= PROGNOSE_SCHWELLE).astype(float)
        d = d.merge(gdelt_merkmale(g), on="date", how="left")
        alle = M_MERKMALE + G_MERKMALE
        d = d.dropna(subset=alle + ["y"]).reset_index(drop=True)
        if len(d) < 400 or d.y.nunique() < 2:
            print(f"[UEBERSPRUNGEN] {name}: {len(d)} Tage")
            continue

        y = d.y.to_numpy()
        p = {}
        for art in ("lr", "gb"):
            p[f"markt_{art}"] = oof(d[M_MERKMALE], y, art)
            p[f"gdelt_{art}"] = oof(d[G_MERKMALE], y, art)
            p[f"kombi_{art}"] = oof(d[alle], y, art)

        gilt = ~np.any(np.isnan(np.vstack(list(p.values()))), axis=0)
        yy = y[gilt]
        if len(np.unique(yy)) < 2:
            continue
        auc = {k: roc_auc_score(yy, v[gilt]) for k, v in p.items()}
        lo, hi = boot_delta(yy, p["markt_gb"][gilt], p["kombi_gb"][gilt], rng)

        z = {"land": name, "tage": int(gilt.sum()),
             **{k: round(v, 3) for k, v in auc.items()},
             "d_gdelt_gb": round(auc["kombi_gb"] - auc["markt_gb"], 3),
             "ki_lo": round(lo, 3), "ki_hi": round(hi, 3),
             "gewinn_durch_gb": round(auc["gdelt_gb"] - auc["gdelt_lr"], 3)}
        zeilen.append(z)
        print(f"{name:<12} n={z['tage']:>4} | GDELT allein: LR {z['gdelt_lr']:.3f} "
              f"GB {z['gdelt_gb']:.3f} ({z['gewinn_durch_gb']:+.3f}) | "
              f"Markt GB {z['markt_gb']:.3f} Kombi GB {z['kombi_gb']:.3f} | "
              f"Beitrag {z['d_gdelt_gb']:+.3f} [{z['ki_lo']:+.3f}, {z['ki_hi']:+.3f}]")

    if not zeilen:
        print("Keine auswertbaren Laender."); return 1
    t = pd.DataFrame(zeilen)
    t.to_csv(DATEN / "vergleich_modellklasse.csv", index=False, sep=";")
    print()
    print(f"GDELT-Beitrag unter Gradient Boosting > 0: {int((t.d_gdelt_gb > 0).sum())} von {len(t)}"
          f", davon signifikant: {int((t.ki_lo > 0).sum())}")
    print(f"Median GDELT-Beitrag (GB): {t.d_gdelt_gb.median():+.3f}   "
          f"(logistisch war es -0,016)")
    print(f"GDELT-Modell allein: Median AUC  LR {t.gdelt_lr.median():.3f}  ->  "
          f"GB {t.gdelt_gb.median():.3f}  ({t.gewinn_durch_gb.median():+.3f})")
    print(f"Marktmodell allein:  Median AUC  LR {t.markt_lr.median():.3f}  ->  "
          f"GB {t.markt_gb.median():.3f}")
    print(f"[OK] {DATEN / 'vergleich_modellklasse.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
