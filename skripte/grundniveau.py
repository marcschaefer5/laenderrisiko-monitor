"""
grundniveau.py -- das Grundrisiko eines Landes, nicht seine Tagesabweichung.

DIE LUECKE, DIE DAS SCHLIESST
Der Risikostand des Monitors ist ein z-Wert gegen die EIGENE Normallage des
Landes. Das ist fuer ein Warnwerkzeug richtig -- gemeldet werden soll, was von
dem abweicht, was dort ueblich ist. Es hat aber eine Kehrseite, die auf der
Karte sichtbar wurde: ein Land im Dauerkonflikt hat eine hohe Normallage, und
ein ruhiger Tag darin erscheint als niedriges Risiko. Russland lag damit
niedriger als Deutschland, obwohl niemand behaupten wuerde, dass dort
grundsaetzlich weniger Risiko besteht.

Beides ist wahr und beides ist eine andere Frage:

    Grundniveau   Wie riskant ist dieses Land ueberhaupt, verglichen mit den
                  anderen im Monitor? Langsam, strukturell, aendert sich in
                  Monaten.
    Abweichung    Wie weit liegt HEUTE ueber der eigenen Normallage? Schnell,
                  taeglich, der Warnanlass.

Der Monitor zeigt jetzt beide. Auf der Karte traegt die FLAECHE das
Grundniveau und die MARKE die Abweichung -- die Struktur als gedaempfte
Farbe, das Ereignis als Signal.

WIE DAS GRUNDNIVEAU GEMESSEN WIRD
Aus denselben Daten wie der Index, aber in ABSOLUTEN Groessen statt als
z-Wert, gemittelt ueber FENSTER Tage:

    Gewaltanteil    (CAMEO 18-20) / alle Ereignisse
    Zwangsanteil    (CAMEO 17)    / alle Ereignisse
    Tonlage         mittlerer AvgTone, negativ gewendet
    Waehrungsvolatilitaet   annualisiert, aus den Tagesrenditen
    Marktvolatilitaet       annualisiert, aus den Tagesrenditen

Jede Groesse wird ueber die Laender in einen RANG umgerechnet (0 bis 1), und
das Grundniveau ist der Mittelwert der verfuegbaren Raenge. Zwei Gruende fuer
Raenge statt Werte: die Groessen haben voellig verschiedene Einheiten, und ein
einzelner Extremwert -- etwa die Lira-Volatilitaet -- wuerde einen Mittelwert
sonst allein bestimmen.

WAS DAS NICHT IST
Kein Laenderrating. Es ist eine Rangfolge INNERHALB der 18 ueberwachten
Laender, aus fuenf Groessen, die dieser Monitor ohnehin fuehrt. Ein Land, das
nicht im Monitor ist, hat kein Grundniveau, und die Skala hat keine Bedeutung
ausserhalb dieser Gruppe. Genau deshalb wird sie als Rang ausgewiesen und nicht
als Note.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from tagesgueltigkeit import bereinigen

FENSTER = 365          # Tage, ueber die das Grundniveau gemittelt wird
MIN_TAGE = 120         # weniger Historie -> kein Grundniveau
VOL_FENSTER = 21

# Die Stufe kommt aus dem RANGPLATZ, nicht aus dem Punktwert.
#
# Warum: der Punktwert ist ein Mittel aus Rangprozenten. Bei siebzehn Laendern
# liegt er fast zwangslaeufig in der Mitte -- beim ersten Lauf hiessen zehn von
# siebzehn Laendern "erhoeht", darunter Russland (64), die USA (60) und
# Brasilien (52). Eine Einordnung, die auf die Mehrheit zutrifft, sagt nichts.
# Die Stufe ist deshalb das Viertel, in dem das Land innerhalb der Gruppe
# liegt, und die Bezeichnungen sagen das auch: es ist eine Rangfolge unter den
# ueberwachten Laendern und kein absolutes Urteil.
VIERTEL = ["oberes Viertel", "drittes Viertel", "zweites Viertel", "unteres Viertel"]
KURZ = {"oberes Viertel": "hoch", "drittes Viertel": "erhöht",
        "zweites Viertel": "mittel", "unteres Viertel": "niedrig"}

GROESSEN = {
    "gewalt":    "Anteil Gewaltereignisse (CAMEO 18–20)",
    "zwang":     "Anteil Zwangsereignisse (CAMEO 17)",
    "tonlage":   "Tonlage der Berichterstattung",
    "waehrung":  "Währungsvolatilität",
    "markt":     "Marktvolatilität",
}


def _vol(pfad: Path) -> float | None:
    if not pfad.exists():
        return None
    d = pd.read_csv(pfad, sep=";", parse_dates=["date"]).sort_values("date")
    d = d[d.date >= d.date.max() - pd.Timedelta(days=FENSTER)]
    if len(d) < MIN_TAGE:
        return None
    r = np.log(d.close.astype(float)).diff()
    v = r.rolling(VOL_FENSTER).std(ddof=0) * np.sqrt(252)
    v = v.dropna()
    return float(v.mean()) if len(v) else None


def rohgroessen(laender: dict, daten: Path, gd: pd.DataFrame) -> pd.DataFrame:
    """Absolute Niveaus je Land -- noch keine Raenge."""
    zeilen = []
    for code in laender:
        z = {"code": code}
        g = gd[gd.code == code]
        if len(g):
            # Dieselbe Tagespruefung wie im Index und in der
            # Episodenerkennung. Ohne sie gingen die unvollstaendig geernteten
            # Tage mit ihren ueberhoehten Anteilen in das Jahresmittel ein --
            # und zwar genau bei den Laendern mit den meisten Erntelucken.
            g, _ = bereinigen(g)
            g = g.dropna(subset=["n_events"])
            g = g[g.date >= g.date.max() - pd.Timedelta(days=FENSTER)]
        if len(g) >= MIN_TAGE:
            n = g.n_events.astype(float).replace(0, np.nan)
            z["gewalt"] = float(((g.n_18 + g.n_19 + g.n_20) / n).mean())
            z["zwang"] = float((g.n_17 / n).mean())
            ton = np.where(g.tone_cnt > 0, g.tone_sum / g.tone_cnt, np.nan)
            # Negativ gewendet: eine negativere Tonlage bedeutet mehr Risiko.
            z["tonlage"] = float(-np.nanmean(ton))
        z["waehrung"] = _vol(daten / f"fx_{code}.csv")
        z["markt"] = _vol(daten / f"aktien_{code}.csv")
        zeilen.append(z)
    return pd.DataFrame(zeilen).set_index("code")


def berechnen(laender: dict, daten: Path, gd: pd.DataFrame) -> dict:
    """Grundniveau je Land: Mittel der verfuegbaren Raenge, 0 bis 100."""
    roh = rohgroessen(laender, daten, gd)
    raenge = pd.DataFrame(index=roh.index)
    for sp in GROESSEN:
        if sp not in roh.columns:
            continue
        spalte = roh[sp].astype(float)
        if spalte.notna().sum() < 3:
            continue
        # pct=True gibt den Rang als Anteil; fehlende Werte bleiben fehlend und
        # gehen nicht als Null ein -- ein Land ohne Aktienindex ist nicht
        # risikoarm, es ist an dieser Stelle unbekannt.
        raenge[sp] = spalte.rank(pct=True)

    aus = {}
    for code in roh.index:
        r = raenge.loc[code].dropna() if len(raenge.columns) else pd.Series(dtype=float)
        if r.empty:
            continue
        # MITTEL der Raenge, und hier bewusst kompensatorisch -- anders als im
        # Zustandsindex, der mit max(Mittel, 0,7 x groesster Baustein) rechnet.
        #
        # Der Unterschied ist kein Versehen, sondern folgt aus der
        # verschiedenen Frage. Der Zustandsindex fragt "passiert hier gerade
        # etwas"; dort darf ein ruhiger Devisenmarkt eine Gewaltwelle nicht
        # kleinrechnen, weil ein einzelner Ausbruch das Ereignis IST. Das
        # Grundniveau fragt "wie riskant ist dieses Land ueberhaupt", gemittelt
        # ueber ein Jahr -- und da ist ein Land mit hohem Gewaltanteil und
        # stabiler Waehrung tatsaechlich ein anderes Risikoprofil als eines mit
        # beidem. Mit einer Klausel waere jedes Land auf seinen schlimmsten
        # Einzelrang zusammengezogen, und 18 Laender haetten faktisch vier
        # verschiedene Werte.
        #
        # Damit der hoechste Einzelrang nicht verschwindet, werden alle
        # Einzelraenge im Feld "grundlagen" mitgegeben; die Oberflaeche zeigt
        # sie als Balken und benennt den hoechsten ausdruecklich: die
        # Ukraine hat den hoechsten Gewaltanteil aller ueberwachten Laender
        # (Rang 100) und steht im Gesamtmittel dennoch auf Platz 7 -- beides
        # richtig, und beides sichtbar.
        wert = float(r.mean() * 100)
        # Mit weniger als drei Groessen ist der Mittelwert der Raenge nicht
        # tragfaehig: Indonesien stand beim ersten Lauf allein auf
        # Waehrungs- und Marktvolatilitaet und landete damit auf Platz 3,
        # obwohl seine Ereignisdaten noch fehlten. Solche Faelle werden
        # ausgewiesen, nicht geglaettet.
        aus[code] = {
            "wert": round(wert, 1),
            "stufe": None,        # wird nach der Rangfolge gesetzt
            "viertel": None,
            "unsicher": len(r) < 3,
            "anzahl_groessen": int(len(r)),
            "rang": None,      # wird unten gesetzt
            "grundlagen": {sp: round(float(raenge.loc[code, sp] * 100), 1)
                           for sp in raenge.columns if pd.notna(raenge.loc[code, sp])},
            "roh": {sp: (None if pd.isna(roh.loc[code, sp]) else round(float(roh.loc[code, sp]), 4))
                    for sp in raenge.columns},
        }
    # Platz in der Rangfolge, und daraus das Viertel.
    n = len(aus)
    for platz, code in enumerate(sorted(aus, key=lambda c: -aus[c]["wert"]), 1):
        aus[code]["rang"] = platz
        aus[code]["von"] = n
        i = min(3, int((platz - 1) * 4 / max(n, 1)))
        aus[code]["viertel"] = VIERTEL[i]
        aus[code]["stufe"] = KURZ[VIERTEL[i]]
    return aus


def schreiben(aus: dict, daten: Path) -> None:
    (daten / "grundniveau.json").write_text(
        json.dumps({"stand": pd.Timestamp.today().strftime("%Y-%m-%d"),
                    "fenster_tage": FENSTER, "groessen": GROESSEN, "laender": aus},
                   ensure_ascii=False, indent=1), encoding="utf-8")
