"""
index_gewichte.py -- Zusammensetzung des Risikoindex: Bausteine und Gewichte.

WARUM DIESE DATEI EXISTIERT
Bis hierher war der Index das ungewichtete Mittel aus Waehrungsdruck,
Marktvolatilitaet und globaler geopolitischer Spannung. Zwei Schwaechen daran
sind messbar, nicht Geschmackssache:

1. DER GEOPOLITISCHE BAUSTEIN IST NICHT LAENDERSPEZIFISCH. Er kommt aus dem
   globalen GPR-Index von Caldara und Iacoviello -- derselbe Wert fuer alle
   Laender am selben Tag. Nachgemessen betraegt die Spanne dieses Bausteins
   ZWISCHEN den Laendern am selben Tag 0,005 Standardabweichungen, die des
   Waehrungsbausteins 1,84. Ihn hoeher zu gewichten hebt oder senkt alle
   Laender gemeinsam und aendert an der Frage "wo ist gerade etwas" nichts.

2. DIE LAENDERSPEZIFISCHE EREIGNISLAGE FEHLT GANZ. Nigeria stand am 09.09.2026
   bei einem Gesamtwert von -0,76, waehrend der Anteil der Zwangsereignisse
   (CAMEO 17) 2,19 Standardabweichungen ueber der Normallage lag. Der Index
   konnte das nicht zeigen, weil er diese Groesse nicht enthaelt.

WARUM GDELT HIER HINEINDARF -- UND IM PROGNOSETEIL NICHT
Der Befund der zugrunde liegenden Arbeit lautet: aus Ereignisdaten liess sich
kein PROGNOSEBEITRAG gegenueber einem Persistenz-Nullmodell nachweisen. Er
lautet nicht: Ereignisdaten sagen nichts ueber die Gegenwart. Genau umgekehrt
-- die Episodenerkennung zeigt, dass sie eine laufende Lage gut beschreiben.
Der Risikoindex ist eine ZUSTANDSGROESSE, keine Vorhersage. Deshalb gehoert
die Ereignislage in den Zustand und bleibt aus der Fortschreibung heraus. Beide
Stellen sind im Code getrennt: hier der Zustand, in ausblick.py die
Fortschreibung, die weiterhin ohne Ereignismerkmale gegen die
Beibehaltungsregel geprueft wird.

DIE VIER BAUSTEINE
  ereignis     laenderspezifische Eskalationslage aus GDELT (neu)
  waehrung     Volatilitaet und Abwertung der Waehrung
  markt        Volatilitaet des Aktienindex
  geopolitik   globales Umfeld (GPR) -- bewusst mit geringem Gewicht, weil er
               zwischen Laendern nicht trennt, aber das Weltklima abbildet

AGGREGATION: GEWICHTETES MITTEL MIT ESKALATIONSKLAUSEL
Ein Mittelwert ist KOMPENSATORISCH: ein ruhiger Devisenmarkt rechnet eine
Gewaltwelle klein. Fuer ein Warnwerkzeug ist das der falsche Rechenweg. Der
Gesamtwert ist deshalb

    gesamt = max( gewichtetes Mittel ,  KLAUSEL_ANTEIL * groesster Baustein )

und greift damit auf einen einzelnen ausbrechenden Baustein durch, ohne die
uebrigen zu ignorieren. Diese Form ist in der Praxis zusammengesetzter
Indikatoren als nicht-kompensatorische Aggregation etabliert; sie hat genau
einen Parameter und der ist unten dokumentiert.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# Reihenfolge = Anzeigereihenfolge im Dashboard.
BAUSTEINE = ["ereignis", "waehrung", "markt", "geopolitik"]

# Vorgabegewichte. Sie gelten, solange keine kalibrierte Fassung in
# daten/gewichte.json liegt (gewichte_kalibrieren.py erzeugt sie). Die Vorgabe
# ist keine Schaetzung, sondern eine begruendete Setzung: die Ereignislage ist
# der einzige laenderspezifische Baustein mit taeglicher Auflösung, der globale
# GPR der einzige, der zwischen Laendern nicht trennt.
GEWICHTE_VORGABE = {"ereignis": 0.40, "waehrung": 0.25, "markt": 0.25, "geopolitik": 0.10}

# Anteil, mit dem der groesste Einzelbaustein durchgreift. 0,7 heisst: ein
# Baustein bei +3,0 zieht den Gesamtwert auf mindestens +2,1, egal wie ruhig
# der Rest ist. Der Wert ist bewusst < 1, damit ein einzelner Ausschlag den
# Index nicht vollstaendig bestimmt.
KLAUSEL_ANTEIL = 0.70

# Ereignislage: Glaettung und Bestandteile.
EREIGNIS_FENSTER = 3        # Tage; der laufende GDELT-Tag ist unvollstaendig
EREIGNIS_TEILE = ["gewalt_z", "zwang_z", "protest_z"]


def gewichte_laden(daten: Path) -> tuple[dict, str]:
    """Kalibrierte Gewichte, sonst die Vorgabe. Zweiter Rueckgabewert: Herkunft."""
    pfad = daten / "gewichte.json"
    if pfad.exists():
        try:
            g = json.loads(pfad.read_text())
            gew = {b: float(g["gewichte"][b]) for b in BAUSTEINE if b in g.get("gewichte", {})}
            if gew and abs(sum(gew.values()) - 1) < 1e-6:
                return gew, f"kalibriert am {g.get('stand', '?')}"
        except Exception:
            pass
    return dict(GEWICHTE_VORGABE), "Vorgabe (nicht kalibriert)"


def ereignislage(merkmale: pd.DataFrame) -> pd.Series:
    """Laenderspezifische Eskalationslage als EIN z-Wert.

    Zusammengefasst wird ueber das MAXIMUM der drei Kategorien, nicht ueber
    ihren Mittelwert. Begruendung: Gewalt, Zwang und Protest sind alternative
    Erscheinungsformen derselben Frage "passiert hier gerade etwas
    Aussergewoehnliches", keine addierbaren Beitraege. Ein Land mit einer
    Protestwelle und ohne Kampfhandlungen ist nicht halb so auffaellig wie
    eines mit beidem -- es ist auffaellig. Der Mittelwert wuerde genau das
    verwischen, und zwar in der Richtung, die fuer ein Warnwerkzeug schaedlich
    ist.

    Erwartet die Ausgabe von gdelt_merkmale.gdelt_merkmale(): rollende z-Werte
    der Anteile an den CAMEO-Wurzeln, ausschliesslich aus Information bis
    einschliesslich Tag t.
    """
    vorhanden = [s for s in EREIGNIS_TEILE if s in merkmale.columns]
    if not vorhanden:
        return pd.Series(np.nan, index=merkmale.index)
    m = merkmale[vorhanden].rolling(EREIGNIS_FENSTER, min_periods=2).mean()
    return m.max(axis=1)


def zusammensetzen(d: pd.DataFrame, gewichte: dict,
                   klausel: float = KLAUSEL_ANTEIL) -> pd.Series:
    """Gewichtetes Mittel der vorhandenen Bausteine plus Eskalationsklausel.

    Fehlende Bausteine werden NICHT mit Null besetzt, sondern aus Gewicht und
    Mittelwert herausgenommen; die uebrigen Gewichte werden neu normiert. Sonst
    haette ein Land ohne Aktienindex (Ukraine, Nigeria, Pakistan) allein
    deshalb ein niedrigeres Risiko -- ein fehlender Baustein ist keine Ruhe.
    """
    da = [b for b in BAUSTEINE if b in d.columns and gewichte.get(b)]
    if not da:
        return pd.Series(np.nan, index=d.index)
    G = np.array([gewichte[b] for b in da], dtype=float)
    X = d[da].to_numpy(dtype=float)
    maske = np.isfinite(X)
    gew = np.where(maske, G, 0.0)
    summe = gew.sum(axis=1)
    mittel = np.where(summe > 0, np.nansum(np.where(maske, X, 0.0) * gew, axis=1) / np.where(summe > 0, summe, 1), np.nan)
    groesster = np.where(maske.any(axis=1), np.nanmax(np.where(maske, X, -np.inf), axis=1), np.nan)
    groesster = np.where(np.isfinite(groesster), groesster, np.nan)
    gesamt = np.fmax(mittel, klausel * groesster)
    return pd.Series(gesamt, index=d.index)


# Karenzzeit, in der ein Baustein als "eigentlich vorhanden" gilt, obwohl er
# heute fehlt. Siehe vollstaendig().
KARENZ_TAGE = 30


def vollstaendig(d: pd.DataFrame, gewichte: dict,
                 karenz: int = KARENZ_TAGE) -> pd.Series:
    """True fuer Tage, an denen ALLE eigentlich vorhandenen Bausteine belegt sind.

    WOZU DAS NOETIG IST
    zusammensetzen() normiert die Gewichte auf die vorhandenen Bausteine. Das
    ist richtig fuer Laender, die einen Baustein dauerhaft nicht haben -- die
    Ukraine hat keinen brauchbaren Aktienindex, und ein fehlender Baustein ist
    keine Ruhe. Am RECHTEN RAND kehrt dieselbe Regel sich aber um und erzeugt
    genau den Fehler, den sie verhindern soll:

      Israel, 09.09.2026   Ereignislage +0,85   Index -0,74 Sigma
      Israel, 10.09.2026   Ereignislage  fehlt  Index -2,18 Sigma

    Gefallen ist nicht die Lage, sondern die Messung: die Ereignisdaten des
    Landes endeten am 06.09., die Ueberbrueckung lief nach drei Tagen aus. Die
    Boerse meldet weiter, also blieben drei ruhige Bausteine uebrig und der
    Index sackte um 1,44 Sigma ab -- ein Warnwerkzeug haette an diesem Tag
    Entspannung gemeldet.

    DIE UNTERSCHEIDUNG
    Dauerhaft fehlender Baustein  -> herausnormieren, der Index gilt.
    Heute fehlender Baustein      -> der Tag ist NICHT beurteilbar.

    Unterschieden wird ueber die Karenzzeit: ein Baustein gilt an Tag t als
    erwartet, wenn er innerhalb der letzten KARENZ_TAGE Tage mindestens einmal
    belegt war. Damit faellt Russlands Aktienbaustein nach einem Monat ohne
    Notierung sauber aus der Erwartung heraus, waehrend Israels Ereignisbaustein
    nach zwei Tagen Pause noch erwartet wird.
    """
    da = [b for b in BAUSTEINE if b in d.columns and gewichte.get(b)]
    if not da:
        return pd.Series(False, index=d.index)
    vorhanden = d[da].notna()
    erwartet = vorhanden.rolling(karenz, min_periods=1).max().astype(bool)
    return ~(erwartet & ~vorhanden).any(axis=1)


# Gemeinsame Normierung der Bausteine.
NORM_BASIS = 120     # Handelstage; dasselbe Fenster wie die Indexnormierung
NORM_MIN = 60


def normieren(d: pd.DataFrame, fenster: int = NORM_BASIS,
              min_periods: int = NORM_MIN) -> pd.DataFrame:
    """Bringt die Bausteine auf EINE Skala: rollender z-Wert je Baustein.

    WARUM DAS NOETIG IST -- DIE BAUSTEINE WAREN NICHT VERGLEICHBAR
    Gemessen ueber alle Laender und Tage des Bestandes, vor dieser Normierung:

      Baustein      Mittel   StdAbw   Anteil >= 2,0
      ereignis       +0,60     0,77       5,3 %
      waehrung        0,00     0,78       2,2 %
      markt           0,00     1,00       4,9 %
      geopolitik     +0,83     1,14      11,2 %

    Drei verschiedene Bezugsbasen hatten sich eingeschlichen: Waehrung und
    Markt waren ueber die GESAMTE eigene Reihe standardisiert, der GPR ueber
    seine gesamte Historie (und liegt in der Gegenwart systematisch ueber
    diesem Mittel), die Ereignislage rollend ueber 60 Tage und zusaetzlich als
    MAXIMUM dreier z-Werte -- ein Maximum hat auch dann einen positiven
    Erwartungswert, wenn jeder einzelne Wert bei null liegt.

    Drei Folgen, alle drei schaedlich:
    1. Ein gewichtetes MITTEL aus Groessen mit verschiedenen Nullpunkten ist
       nicht in Standardabweichungen lesbar, obwohl die Oberflaeche es so
       beschriftet.
    2. Die Eskalationsklausel (0,7 x groesster Baustein) greift bevorzugt bei
       den beiden nach oben verschobenen Bausteinen -- also regelmaessig beim
       globalen GPR, der zwischen Laendern gar nicht trennt.
    3. Die Gewichte konnten nicht leisten, was von ihnen erwartet wurde: wer
       "Geopolitik hoeher gewichten" sagt, meint nicht "den Nullpunkt
       verschieben".

    ZUSAETZLICH BESEITIGT: EIN BLICK IN DIE ZUKUNFT
    Die Standardisierung ueber die gesamte Reihe benutzt Mittelwert und
    Streuung des GANZEN Zeitraums, also auch der Tage NACH t. Fuer die
    GDELT-Merkmale war genau das von Anfang an ausgeschlossen ("alle Merkmale
    nutzen ausschliesslich Information bis einschliesslich Tag t",
    gdelt_merkmale.py); fuer die Marktbausteine galt es nicht. Der rollende
    z-Wert stellt beide Seiten auf dieselbe Regel.
    """
    aus = d.copy()
    for b in BAUSTEINE:
        if b not in aus.columns:
            continue
        r = pd.to_numeric(aus[b], errors="coerce")
        mu = r.rolling(fenster, min_periods=min_periods).mean()
        sd = r.rolling(fenster, min_periods=min_periods).std(ddof=0)
        aus[b] = (r - mu) / sd.replace(0, np.nan)
    return aus
