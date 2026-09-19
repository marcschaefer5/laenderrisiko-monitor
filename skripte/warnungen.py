"""
warnungen.py -- Lagemeldungen: was ist gerade eingetreten?

DIE ROLLE DIESES MODULS
Der Monitor ist in erster Linie ein Warnwerkzeug. Das ist keine
Geschmacksfrage, sondern die Konsequenz aus dem Befund der zugrunde
liegenden Arbeit: ueber 91 geprueften Konstellationen liess sich aus
Nachrichtendaten kein Prognosebeitrag gegenueber einem Nullmodell
nachweisen, das nur die eigene Vergangenheit der Zielgroesse kennt. Was sich
dagegen zeigen laesst, ist die Gegenwart -- Ereignisdaten sind stark darin,
eine Lage zu beschreiben, waehrend sie laeuft.

Dieses Modul erzeugt daraus Meldungen: kurze, datierte Aussagen darueber,
was an einem Land gerade auffaellig ist, jeweils mit der Groesse, auf der
die Aussage beruht.

VIER MELDEARTEN
  Sprung        eine Tagesbewegung des Risikoindex, die deutlich ueber der
                landesueblichen Tagesstreuung liegt.
  Niveau        ein anhaltend erhoehter Indexstand, mit Angabe seit wann.
  Baustein      eine einzelne Komponente -- Waehrung, Markt, Geopolitik --
                laeuft aus dem Rahmen, waehrend der Gesamtindex noch ruhig
                aussieht. Genau diese Meldungen gehen im Mittelwert unter.
  Nachrichtenlage  Meldungsaufkommen oder Gewaltanteil in den GDELT-Daten
                weichen stark von der eigenen Normallage ab; dazu die
                laufenden Episoden aus der Krisenerkennung.

JEDE MELDUNG TRAEGT IHR DATUM
"Seit wann" ist die eigentliche Information eines Warnwerkzeugs. Eine
Meldung, die nur sagt, dass etwas hoch ist, wiederholt den Zustand; eine
Meldung mit Anfangsdatum sagt, dass etwas passiert ist. Meldungen, deren
Zustand innerhalb der letzten NEU_TAGE Tage begonnen hat, werden zusaetzlich
als neu gekennzeichnet und in der Oberflaeche zuerst gezeigt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NIVEAU_HOCH = 1.5        # z-Wert des Gesamtindex
NIVEAU_KRITISCH = 2.5
BAUSTEIN_SCHWELLE = 2.0  # z-Wert einer Einzelkomponente
GDELT_SCHWELLE = 2.0     # rollender z-Wert der Ereignismerkmale
NEU_TAGE = 3             # so jung gilt eine Meldung als neu
SPRUNG_TAGE = 3          # Fenster, in dem ein Sprung noch gemeldet wird

RANG = {"kritisch": 3, "hoch": 2, "beachten": 1}


def _tage(n: int) -> str:
    """Tagesangabe im Fliesstext -- "seit einem Tag" statt "seit 1 Tagen"."""
    return "einem Tag" if n == 1 else f"{n} Tagen"

# Geprueft werden die MARKTBAUSTEINE. Die Ereignislage fehlt hier absichtlich:
# sie ist selbst das Maximum aus Gewalt-, Zwang- und Protestanteil, und genau
# diese drei werden unten einzeln und mit der konkreten CAMEO-Wurzel gemeldet.
# Sie zusaetzlich als Baustein zu fuehren hiesse, denselben Befund zweimal
# auszugeben -- einmal unspezifisch, einmal spezifisch.
BAUSTEIN_NAME = {"waehrung": "Währungsdruck", "markt": "Marktvolatilität",
                 "geopolitik": "Geopolitische Spannung"}


def _lauf_beginn(maske: pd.Series, datum: pd.Series) -> tuple[str | None, int]:
    """Anfang des zusammenhaengenden Laufs, der am letzten Tag endet."""
    m = maske.to_numpy(dtype=bool)
    if not len(m) or not m[-1]:
        return None, 0
    i = len(m) - 1
    while i > 0 and m[i - 1]:
        i -= 1
    return datum.iloc[i].strftime("%Y-%m-%d"), int(len(m) - i)


def _alter(datum_str: str, heute: pd.Timestamp) -> int:
    return int((heute - pd.Timestamp(datum_str)).days)


def warnungen(d: pd.DataFrame, lagen: list[dict], code: str,
              name: str) -> list[dict]:
    """Erzeugt die Lagemeldungen eines Landes, dringlichste zuerst.

    d  -- die aufbereitete Tagesreihe des Landes (z, Kategorien, auffaellig,
          optional die GDELT-Merkmale)
    lagen -- Ergebnis der Krisenerkennung (krisen.py)
    """
    if d.empty:
        return []
    heute = d.date.iloc[-1]
    aus: list[dict] = []

    def melde(stufe, art, titel, text, seit=None, tage=0, wert=None, datum=None):
        dat = datum or seit or heute.strftime("%Y-%m-%d")
        aus.append({"code": code, "land": name, "stufe": stufe,
                    "rang": RANG[stufe], "art": art, "titel": titel,
                    "text": text, "seit": seit, "tage": tage,
                    "wert": None if wert is None else round(float(wert), 2),
                    "datum": dat, "neu": _alter(dat, heute) <= NEU_TAGE})

    # ---------------------------------------------------------- Sprung
    # Die auffaelligen Tage sind bereits in der Reihe markiert: eine
    # Tagesbewegung nach oben, die ein Vielfaches der landesueblichen
    # Tagesstreuung betraegt. Gemeldet werden nur die juengsten -- ein Sprung
    # von vor drei Wochen ist Historie, keine Warnung.
    letzte = d.tail(SPRUNG_TAGE + 1)
    for _, r in letzte[letzte.auffaellig == 1].iterrows():
        dat = r.date.strftime("%Y-%m-%d")
        melde("kritisch" if r.z >= NIVEAU_HOCH else "hoch", "sprung",
              "Sprunghafter Anstieg des Risikoindex",
              f"Der Index ist an diesem Tag um ein Vielfaches der üblichen "
              f"Tagesstreuung dieses Landes gestiegen und steht bei "
              f"{r.z:+.2f} Standardabweichungen über der eigenen Normallage.",
              seit=dat, tage=1, wert=r.z, datum=dat)

    # ---------------------------------------------------------- Niveau
    hoch = d.z >= NIVEAU_HOCH
    seit, tage = _lauf_beginn(hoch, d.date)
    if seit:
        z = float(d.z.iloc[-1])
        stufe = "kritisch" if z >= NIVEAU_KRITISCH else "hoch"
        melde(stufe, "niveau",
              "Risikoniveau anhaltend erhöht",
              f"Der Gesamtindex liegt seit {_tage(tage)} ununterbrochen "
              f"mindestens {NIVEAU_HOCH:.1f} Standardabweichungen über der "
              f"eigenen Normallage der letzten 120 Handelstage; aktuell "
              f"{z:+.2f}.",
              seit=seit, tage=tage, wert=z)

    # ---------------------------------------------------------- Bausteine
    # Der Index ist ein Mittel. Ein Mittel kann ruhig aussehen, waehrend eine
    # seiner Komponenten aus dem Rahmen laeuft -- deshalb wird jede Komponente
    # zusaetzlich einzeln geprueft.
    for k, kname in BAUSTEIN_NAME.items():
        if k not in d.columns:
            continue
        # KEINE zweite Standardisierung hier.
        #
        # Diese Stelle rechnete bis zu dieser Fassung einen eigenen rollenden
        # z-Wert auf den Baustein. Das Ergebnis war eine Zahl, die es nirgends
        # sonst im Monitor gab: fuer die Tuerkei meldete sie "Waehrungsdruck
        # aussergewoehnlich hoch, +2,26 Standardabweichungen", waehrend die
        # Kurve desselben Bausteins auf derselben Seite bei -0,32 lag, also
        # UNTER ihrem Mittel. Fuer die Ukraine standen +4,61 gegen +0,55.
        # Die Bausteine werden inzwischen vor der Indexbildung gemeinsam
        # normiert (index_gewichte.normieren), also ist der Wert in der Reihe
        # bereits der z-Wert -- und Meldung, Kurve und Index sprechen dieselbe
        # Skala.
        zk = d[k]
        if not np.isfinite(zk.iloc[-1]):
            continue
        seit_k, tage_k = _lauf_beginn(zk >= BAUSTEIN_SCHWELLE, d.date)
        if not seit_k:
            continue
        ruhig = float(d.z.iloc[-1]) < NIVEAU_HOCH
        melde("hoch" if not ruhig else "beachten", "baustein",
              f"{kname} außergewöhnlich hoch",
              f"{kname} liegt seit {_tage(tage_k)} bei {zk.iloc[-1]:+.2f} "
              f"Standardabweichungen." +
              (f" Der Gesamtindex bleibt dabei unauffällig ({float(d.z.iloc[-1]):+.2f}) "
               "— die übrigen Bausteine liegen so weit darunter, dass auch die "
               "Eskalationsklausel nicht greift."
               if ruhig else ""),
              seit=seit_k, tage=tage_k, wert=zk.iloc[-1])

    # ---------------------------------------------------------- GDELT
    gdelt_texte = {
        "ev_z": ("Meldungsaufkommen stark erhöht",
                 "Die Zahl der GDELT-Ereignisse zu diesem Land liegt {w:+.2f} "
                 "Standardabweichungen über dem eigenen 60-Tage-Normalwert."),
        "gewalt_z": ("Gewaltanteil der Meldungen erhöht",
                     "Der Anteil der Ereignisse aus den CAMEO-Wurzeln 18–20 "
                     "(Angriff, Kampf, Massengewalt) liegt {w:+.2f} "
                     "Standardabweichungen über der eigenen Normallage."),
        "protest_z": ("Protestmeldungen häufen sich",
                      "Der Anteil der Protestereignisse (CAMEO 14) liegt "
                      "{w:+.2f} Standardabweichungen über der Normallage."),
        "zwang_z": ("Zwangsmaßnahmen häufen sich",
                    "Der Anteil der Zwangsereignisse (CAMEO 17) liegt {w:+.2f} "
                    "Standardabweichungen über der Normallage."),
    }
    for sp, (titel, muster) in gdelt_texte.items():
        if sp not in d.columns:
            continue
        reihe = d[sp]
        if not len(reihe.dropna()):
            continue
        # Dreitagesmittel statt Einzeltag: der laufende GDELT-Tag ist beim
        # Lauf um 04:00 UTC nur teilweise gemeldet und schwankt entsprechend.
        glatt = reihe.rolling(3, min_periods=2).mean()
        if not np.isfinite(glatt.iloc[-1]):
            continue
        seit_g, tage_g = _lauf_beginn(glatt >= GDELT_SCHWELLE, d.date)
        if not seit_g:
            continue
        melde("hoch", "nachrichtenlage", titel,
              muster.format(w=glatt.iloc[-1]) +
              f" Zustand seit {_tage(tage_g)}. Dies ist eine Beschreibung der "
              f"aktuellen Berichterstattung, keine Prognose.",
              seit=seit_g, tage=tage_g, wert=glatt.iloc[-1])

    # ---------------------------------------------------------- Episoden
    for k in lagen:
        if not k.get("laufend"):
            continue
        stufe = {"extrem": "kritisch", "stark": "hoch"}.get(k.get("stufe"), "beachten")
        melde(stufe, "lage", f"{k['name']} — laufende Episode",
              f"{k['beschreibung']} Anteil {str(k['anteil']).replace('.', ',')} % "
              f"gegen sonst {str(k['anteil_normal']).replace('.', ',')} %; "
              f"Spitze {str(k['spitze_z']).replace('.', ',')} "
              f"Standardabweichungen am {k['spitze_am']}.",
              seit=k["von"], tage=k["tage"], wert=k["spitze_z"])

    # Dringlichste zuerst: neu vor bekannt, dann Stufe, dann Anfangsdatum.
    aus.sort(key=lambda m: (m["neu"], m["rang"], m["datum"]), reverse=True)
    return aus


def zusammenfassen(alle: list[dict], grenze: int = 40) -> dict:
    """Verdichtet die Meldungen aller Laender fuer die Startansicht."""
    alle = sorted(alle, key=lambda m: (m["neu"], m["rang"], m["datum"]),
                  reverse=True)
    return {
        "meldungen": alle[:grenze],
        "anzahl": len(alle),
        "neu": sum(1 for m in alle if m["neu"]),
        "kritisch": sum(1 for m in alle if m["stufe"] == "kritisch"),
        "laender": len({m["code"] for m in alle}),
    }
