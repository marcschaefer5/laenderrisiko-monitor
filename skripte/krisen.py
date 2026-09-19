"""Laufende Krisen je Land erkennen -- Nowcast, nicht Prognose.

Der Unterschied ist die ganze Pointe. Ueber 55 Konstellationen hat GDELT
Marktanspannung NICHT vorhergesagt. Das heisst aber nicht, dass die Daten
nichts wert sind: GDELT ist eine Ereignisdatenbank. Sie ist stark darin zu
zeigen, WAS GERADE PASSIERT, und schwach darin zu sagen, was als naechstes
kommt. Genau diese Aufgabe bekommt sie hier.

Eine Krise ist hier eine EPISODE, kein Tag. Definition:

  Aufsetzen   der geglaettete z-Wert der Kategorie liegt AN_SCHWELLE
              Standardabweichungen ueber der eigenen Normallage, und zwar
              MIN_TAGE Tage in Folge.
  Fortdauern  die Episode laeuft weiter, solange der Wert ueber
              AUS_SCHWELLE bleibt.
  Beenden     erst wenn er AUS_TAGE Tage in Folge darunter liegt.

Die zwei getrennten Schwellen (Hysterese) sind der Grund, warum eine Lage
nicht flackert. Mit einer einzigen Schwelle wuerde ein wochenlanger Konflikt
in dreissig Einzelkrisen zerfallen, sobald der Wert einmal kurz durchsackt --
derselbe Fehler, der die Auffaelligkeitsregel schon einmal unbrauchbar
gemacht hat.

Bezugspunkt ist immer die eigene Vergangenheit des Landes ueber
BASIS_FENSTER Tage. Absolute Ereignisanteile sind zwischen Laendern nicht
vergleichbar: Nigerias normaler Gewaltanteil liegt strukturell ueber dem
deutschen. Die Frage lautet nicht "ist es dort gefaehrlich", sondern "ist es
dort gerade gefaehrlicher als sonst".

Wichtig fuer die Einordnung im Dashboard: eine Kategorie kann ruhig
aussehen, obwohl das Niveau hoch ist -- weil das hohe Niveau die Normallage
IST. Deshalb wird zu jeder Lage zusaetzlich der Rohanteil ausgewiesen.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tagesgueltigkeit import gueltig

BASIS_FENSTER = 180      # Referenzzeitraum fuer die Normallage
MIN_BASIS = 90           # so viele Tage muessen belegt sein, sonst kein Urteil
GLATT = 7                # Glaettung, damit einzelne Meldetage nichts ausloesen
AN_SCHWELLE = 1.5
AUS_SCHWELLE = 0.5
MIN_TAGE = 5
AUS_TAGE = 7

# Ab wann eine abgeschlossene Episode nicht mehr zur LAGE gehoert.
#
# Ein Warnwerkzeug zeigt, was jetzt gilt. Eine Protestwelle, die vor
# vierhundert Tagen endete, ist Geschichte des Landes und kein Teil seiner
# heutigen Lage -- steht sie ungetrennt in derselben Liste, verwaessert sie
# genau die Aussage, um die es geht. Sie wird deshalb nicht geloescht, sondern
# als historisch gekennzeichnet und in der Oberflaeche eingeklappt.
AKTUELL_TAGE = 180
MAX_AKTUELL = 6          # so viele laufende/aktuelle Episoden werden gezeigt
MAX_HISTORISCH = 8       # so viele aeltere bleiben zum Nachschlagen

# Ereignis-Kategorien aus den CAMEO-Wurzeln.
KATEGORIEN = {
    "konflikt": {"wurzeln": [18, 19, 20], "name": "Bewaffneter Konflikt",
                 "text": "Angriffe, Kampfhandlungen und Massengewalt (CAMEO 18–20) "
                         "machen einen ungewöhnlich hohen Anteil der Meldungen aus."},
    "protest":  {"wurzeln": [14], "name": "Protestwelle",
                 "text": "Proteste und Demonstrationen (CAMEO 14) prägen die "
                         "Berichterstattung deutlich stärker als üblich."},
    "zwang":    {"wurzeln": [17], "name": "Repression und Zwang",
                 "text": "Zwangsmaßnahmen (CAMEO 17) — Festnahmen, Ausgangssperren, "
                         "Einschränkungen — treten gehäuft auf."},
}

STUFEN = [(4.0, "extrem"), (2.5, "stark"), (1.5, "erhöht")]


def _stufe(z: float) -> str:
    for grenze, name in STUFEN:
        if z >= grenze:
            return name
    return "erhöht"


def _episoden(reihe: pd.Series, datum: pd.Series) -> list[dict]:
    """Findet Episoden mit Hysterese. reihe ist der geglaettete z-Wert."""
    z = reihe.to_numpy(dtype=float)
    aus = []
    i, n = 0, len(z)
    while i < n:
        # Aufsetzen: MIN_TAGE in Folge ueber AN_SCHWELLE
        if not np.all(z[i:i + MIN_TAGE] >= AN_SCHWELLE) or i + MIN_TAGE > n:
            i += 1
            continue
        start = i
        j = i + MIN_TAGE
        unter = 0
        while j < n:
            if np.isnan(z[j]) or z[j] < AUS_SCHWELLE:
                unter += 1
                if unter >= AUS_TAGE:
                    break
            else:
                unter = 0
            j += 1
        ende = j - unter if unter >= AUS_TAGE else n - 1
        seg = z[start:ende + 1]
        aus.append({"von": datum.iloc[start], "bis": datum.iloc[ende],
                    "tage": int(ende - start + 1),
                    "spitze": float(np.nanmax(seg)),
                    "spitze_am": datum.iloc[start + int(np.nanargmax(seg))],
                    "aktuell": float(z[min(ende, n - 1)])})
        i = ende + 1
    return aus


def krisen(g: pd.DataFrame, heute: pd.Timestamp) -> list[dict]:
    """Erwartet die GDELT-Tagesaggregate EINES Landes.

    Zurueck kommen die Lagen, sortiert: laufende zuerst, danach die
    juengsten abgeschlossenen.
    """
    d = g.sort_values("date").copy()
    if len(d) < MIN_BASIS + GLATT:
        return []
    d = d.set_index("date").asfreq("D").reset_index()   # Luecken sichtbar machen
    n = d.n_events.astype(float)

    # Angebrochene Tage ausschliessen.
    #
    # Der taegliche Lauf startet um 04:00 UTC; der laufende Tag ist dann erst
    # zu einem Bruchteil gemeldet. Ein solcher Tag hat verzerrte Anteile und
    # kann eine laufende Lage faelschlich beenden -- also genau an dem Tag ein
    # falsches Negativ erzeugen, an dem es darauf ankommt.
    #
    # Die Regel stand hier einmal als eigene Fassung (50 % des Medians der
    # letzten sieben Tage). Sie stand damit NUR hier: die Merkmalsbildung fuer
    # den Ereignisbaustein des Index hatte keine solche Pruefung, dieselbe
    # Erntelucke konnte also keine Episode ausloesen, aber sehr wohl eine
    # Lagemeldung. Die Definition liegt deshalb jetzt in tagesgueltigkeit.py
    # und wird von beiden Stellen benutzt -- Vergleich je Wochentag, weil die
    # Tagesmenge zwischen Donnerstag und Sonntag um Faktor zwei schwankt.
    genug = gueltig(d.set_index("date").n_events).to_numpy()

    ergebnis = []
    for schluessel, k in KATEGORIEN.items():
        anteil = sum(d[f"n_{w}"].astype(float) for w in k["wurzeln"]) / n
        anteil = anteil.where(genug)
        mu = anteil.rolling(BASIS_FENSTER, min_periods=MIN_BASIS).mean()
        sd = anteil.rolling(BASIS_FENSTER, min_periods=MIN_BASIS).std(ddof=0)
        z = ((anteil - mu) / sd.replace(0, np.nan)).rolling(GLATT, min_periods=4).mean()
        for e in _episoden(z, d.date):
            seit_ende = (heute - e["bis"]).days
            laufend = seit_ende <= AUS_TAGE
            fenster = (d.date >= e["von"]) & (d.date <= e["bis"])
            ergebnis.append({
                "art": schluessel,
                "name": k["name"],
                "beschreibung": k["text"],
                "laufend": bool(laufend),
                "alter_tage": int(max(seit_ende, 0)),
                "historisch": bool(not laufend and seit_ende > AKTUELL_TAGE),
                "von": e["von"].strftime("%Y-%m-%d"),
                "bis": e["bis"].strftime("%Y-%m-%d"),
                "tage": e["tage"],
                "stufe": _stufe(e["spitze"]),
                "spitze_z": round(e["spitze"], 2),
                "spitze_am": e["spitze_am"].strftime("%Y-%m-%d"),
                "anteil": round(float(anteil[fenster].mean() * 100), 1),
                "anteil_normal": round(float(mu[fenster].mean() * 100), 1),
            })

    # Laufende zuerst, innerhalb dessen die juengsten. Danach getrennt
    # zugeschnitten: die aktuelle Lage vollstaendig, die Historie nur als
    # Nachschlagewerk.
    ergebnis.sort(key=lambda x: (x["laufend"], x["bis"]), reverse=True)
    aktuell = [e for e in ergebnis if not e["historisch"]][:MAX_AKTUELL]
    historisch = [e for e in ergebnis if e["historisch"]][:MAX_HISTORISCH]
    return aktuell + historisch
