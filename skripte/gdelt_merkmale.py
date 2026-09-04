"""GDELT-Merkmale fuer die ereignisbasierte Prognose.

Zentral, damit Test (vergleich_gdelt.py) und Produktivlauf
(aktualisieren.py) garantiert dieselben Merkmale verwenden. Ein
Auseinanderlaufen dieser beiden Stellen ist der klassische Weg, wie ein
Modell im Test besser aussieht als im Betrieb.

Konstruktionsprinzip (uebernommen aus der Bachelorarbeit): nicht die
Rohzahlen, sondern ihre ROLLENDEN z-WERTE. Absolute Ereigniszahlen sind
zwischen Laendern nicht vergleichbar (USA: ~43.000 Ereignisse/Tag,
Taiwan: ~520) und driften ueber die Zeit mit der GDELT-Abdeckung. Der
rollende z-Wert fragt stattdessen: ist HEUTE viel, gemessen an den
letzten FENSTER Tagen DIESES Landes? Das ist die Groesse, die ein
Fruehwarnsystem braucht.

Alle Merkmale nutzen ausschliesslich Information bis einschliesslich Tag t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FENSTER = 60          # Referenzfenster fuer die rollenden z-Werte
MIN_TAGE = 30         # Mindestbelegung, bevor ein z-Wert ausgewiesen wird

MERKMALE = ["ev_z", "ton_z", "gewalt_z", "protest_z", "zwang_z",
            "ev_z_d7", "ton_z_d7"]

# Variante "geglaettet": zusaetzlich 3- und 7-Tage-Mittel sowie Verzoegerungen.
#
# Zwei Gruende, das ueberhaupt zu pruefen:
# 1. WOCHENENDEN. GDELT meldet taeglich, Boersen nicht. Beim Zusammenfuehren
#    auf Handelstage fallen Samstag und Sonntag ersatzlos weg -- rund 28 % der
#    Ereignistage. Ein 3-Tage-Mittel traegt sie in den Montag hinein.
# 2. MESSRAUSCHEN. Ein einzelner GDELT-Tag ist stark von der Abdeckung
#    abhaengig (Feiertage, Ausfaelle einzelner Quellen). Wenn ein Signal
#    existiert, sollte es ein Mittel ueberleben; wenn es nur im Tagesrauschen
#    sichtbar ist, war es keines.
MERKMALE_GLATT = MERKMALE + ["ev_z_m3", "ton_z_m3", "gewalt_z_m3",
                             "ev_z_m7", "ton_z_m7", "gewalt_z_m7",
                             "ev_z_l1", "gewalt_z_l1", "gewalt_z_l3"]


def _rollz(s: pd.Series, fenster: int = FENSTER) -> pd.Series:
    mu = s.rolling(fenster, min_periods=MIN_TAGE).mean()
    sd = s.rolling(fenster, min_periods=MIN_TAGE).std(ddof=0)
    return (s - mu) / sd.replace(0, np.nan)


def gdelt_merkmale(g: pd.DataFrame, glatt: bool = False) -> pd.DataFrame:
    """Erwartet die Tagesaggregate EINES Landes, sortiert nach date."""
    d = g.sort_values("date").copy()
    n = d.n_events.astype(float).replace(0, np.nan)

    # Menge: log, weil die Ereigniszahl rechtsschief ist.
    d["ev_z"] = _rollz(np.log(n))

    # Ton: mittlerer AvgTone des Tages. Negativ = negative Berichterstattung.
    d["ton_z"] = _rollz(pd.Series(np.where(d.tone_cnt > 0,
                                           d.tone_sum / d.tone_cnt, np.nan),
                                  index=d.index))

    # Zusammensetzung statt Menge: Anteile der CAMEO-Wurzeln an allen
    # Ereignissen des Tages. Ein Tag mit doppelt so vielen Meldungen, aber
    # gleicher Mischung, ist kein Eskalationssignal -- ein Tag mit gleicher
    # Menge, aber doppeltem Gewaltanteil schon.
    d["gewalt_z"] = _rollz((d.n_18 + d.n_19 + d.n_20) / n)   # Angriff/Kampf/Massengewalt
    d["protest_z"] = _rollz(d.n_14 / n)                       # Protest
    d["zwang_z"] = _rollz(d.n_17 / n)                         # Zwang/Repression

    # Dynamik: Wochenveraenderung der beiden Hauptgroessen.
    d["ev_z_d7"] = d.ev_z.diff(7)
    d["ton_z_d7"] = d.ton_z.diff(7)

    if not glatt:
        return d[["date"] + MERKMALE]

    for k in ("ev_z", "ton_z", "gewalt_z"):
        d[f"{k}_m3"] = d[k].rolling(3, min_periods=2).mean()
        d[f"{k}_m7"] = d[k].rolling(7, min_periods=4).mean()
    d["ev_z_l1"] = d.ev_z.shift(1)
    d["gewalt_z_l1"] = d.gewalt_z.shift(1)
    d["gewalt_z_l3"] = d.gewalt_z.shift(3)
    return d[["date"] + MERKMALE_GLATT]
