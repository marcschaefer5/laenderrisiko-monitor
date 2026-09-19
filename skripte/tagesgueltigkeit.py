"""Welche GDELT-Tage ueberhaupt messbar sind -- eine Definition fuer alle Stellen.

WARUM DIESE DATEI EXISTIERT
Die Ereignisanteile des Monitors sind Quotienten: Gewaltanteil ist
(CAMEO 18+19+20) / alle Ereignisse des Tages. Wird ein Tag nur teilweise
geerntet, schrumpft der NENNER -- und der Anteil schiesst nach oben, ohne dass
im Land etwas passiert ist. Das ist kein theoretisches Risiko, sondern im
eigenen Bestand messbar:

  duenne Tage (unter 25 % der ueblichen Tagesmenge):   194 von 20.679  = 0,94 %
  ihr Anteil an allen Ueberschreitungen von 2 Sigma:    64 von  2.799  = 2,29 %
  Ueberrepraesentation:                                 Faktor 2,4

Beispiele aus dem Bestand: Saudi-Arabien weist an duennen Tagen einen
mittleren Gewaltanteil von 70 % aus gegenueber 4,1 % an normalen Tagen,
Nigeria 13,4 % gegenueber 7,1 %, Pakistan 12,2 % gegenueber 9,9 %. Ein
Warnwerkzeug, das solche Tage durchlaesst, meldet Erntelucken als Eskalation.

DREI URSACHEN FUER EINEN UNVOLLSTAENDIGEN TAG
  1. Der LAUFENDE Tag. GDELT veroeffentlicht 96 Dateien je Tag im
     15-Minuten-Takt. Wer mittags laeuft, sieht die Haelfte.
  2. Ausgefallene Einzeldateien. Von 96 Downloads schlagen einzelne fehl;
     der Tag wird trotzdem geschrieben.
  3. Ausfaelle bei GDELT selbst. Im Bestand stehen Tage mit vier statt
     vierzehnhundert Ereignissen fuer Deutschland.

WARUM ES GENAU HIER STEHT
Die Episodenerkennung (krisen.py) hatte diese Pruefung schon, die
Merkmalsbildung (gdelt_merkmale.py) nicht. Dieselbe Groesse wurde also an
zwei Stellen unterschiedlich streng behandelt: eine Ernteluecke konnte keine
Episode ausloesen, aber sehr wohl den Ereignisbaustein des Index und damit
eine Lagemeldung. Die Definition steht deshalb jetzt einmal hier und wird von
beiden Stellen benutzt.

EIN UNGUELTIGER TAG IST NICHT EIN RUHIGER TAG
Das ist die inhaltliche Entscheidung dahinter. Ein solcher Tag wird nicht auf
null gesetzt, sondern auf "nicht gemessen" (NaN). Null hiesse "heute ist
nichts passiert" und wuerde den Mittelwert nach unten ziehen; NaN heisst "ueber
heute ist keine Aussage moeglich" und laesst die Normallage unberuehrt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FENSTER = 8         # so viele VORHERIGE gleiche Wochentage als Vergleich
MIN_TAGE = 3        # so viele davon muessen belegt sein, sonst kein Urteil
MIN_ANTEIL = 0.40   # darunter gilt der Tag als Erntelucke, nicht als ruhiger Tag
MIN_EREIGNISSE = 30 # absolute Untergrenze -- darunter sind Anteile Rauschen
GROB_FENSTER = 28   # zweiter Massstab: letzte Tage OHNE Wochentagsbezug
GROB_MIN = 10
GROB_ANTEIL = 0.25  # tiefer als MIN_ANTEIL, weil dieser Median Wochenenden enthaelt

# WARUM DER VERGLEICH JE WOCHENTAG LAEUFT
# Die Tagesmenge haengt stark vom Wochentag ab. Gemessen im eigenen Bestand,
# Mediane je Wochentag:
#
#   USA         Do 50.945   Sa 29.107   So 20.916   -> Faktor 2,4
#   Ukraine     Do  4.225   Sa  2.695   So  2.407   -> Faktor 1,8
#   Deutschland Do  1.875   Sa  1.066   So    948   -> Faktor 2,0
#
# Ein Massstab aus ALLEN Tagen verwirft deshalb systematisch die Sonntage:
# mit dem Median aller Tage und derselben Grenze fielen bei den USA 184 Tage
# heraus statt 27, fast ausschliesslich Wochenenden. Das waere kein
# Qualitaetsfilter, sondern ein Datenverlust von rund einem Viertel der Reihe.
# Verglichen wird darum der Mittwoch mit den letzten acht Mittwochen.
#
# Die Grenze liegt bei 40 %: bei 50 % kostet sie ohne erkennbaren Gewinn
# deutlich mehr Tage (Saudi-Arabien 8 -> 29, Ukraine 28 -> 46), bei 25 %
# bleiben Halbtagsernten drin. Der Median statt des Mittelwerts ist wichtig,
# weil sonst ein einzelner Ausfall den Massstab selbst absenkt und die
# naechste Luecke durchlaesst.


def gueltig(n_events: pd.Series) -> pd.Series:
    """True fuer Tage, deren Ereignismenge eine Aussage ueber Anteile erlaubt.

    Erwartet die Tagesmengen EINES Landes in zeitlicher Ordnung, mit
    durchgehendem Tagesindex (fehlende Tage als NaN), damit der Median nicht
    ueber Luecken hinweg rechnet.

    ZWEI MASSSTAEBE, UND WARUM ZWEI NOETIG SIND
    Der Vergleich je Wochentag ist der genauere (Begruendung oben), aber er
    braucht mindestens drei belegte gleiche Wochentage. Fehlen die -- und genau
    das passiert, wenn eine Reihe ueber Wochen duenn ist --, war die Regel in
    ihrer ersten Fassung nachsichtig: ohne Massstab liess sie den Tag durch.
    Damit fiel sie aus, sobald sie am dringendsten gebraucht wurde.

    Im Bestand kam dadurch der 13.09.2026 fuer Deutschland mit 68 Ereignissen
    statt der ueblichen rund 1.400 durch. Der Protestanteil dieses Tages wurde
    mit +6,28 Standardabweichungen ausgewiesen -- aus zwei Meldungen von acht.

    Deshalb ein zweiter, gruberer Massstab, der ohne Wochentagsbezug auskommt:
    der Median der letzten 28 belegten Tage. Er ist wegen des Wochenendanteils
    naturgemaess niedriger, seine Schwelle liegt entsprechend tiefer (25 %
    statt 40 %). Ein Tag muss BEIDE Huerden nehmen, soweit sie berechenbar
    sind.
    """
    n = pd.to_numeric(n_events, errors="coerce").astype(float)
    if not isinstance(n.index, pd.DatetimeIndex):
        raise ValueError("gueltig() erwartet einen Tagesindex (date als Index)")

    # Massstab 1: gleicher Wochentag, letzte FENSTER Vorkommen.
    wt = n.index.dayofweek
    ref_wt = pd.Series(index=n.index, dtype=float)
    for _, teil in n.groupby(wt):
        ref_wt.loc[teil.index] = teil.rolling(FENSTER, min_periods=MIN_TAGE).median().shift(1)
    ref_wt = ref_wt.sort_index()

    # Massstab 2: letzte GROB_FENSTER Tage, unabhaengig vom Wochentag.
    ref_alle = n.rolling(GROB_FENSTER, min_periods=GROB_MIN).median().shift(1)

    genug = n >= MIN_EREIGNISSE
    genug &= (n >= MIN_ANTEIL * ref_wt) | ref_wt.isna()
    genug &= (n >= GROB_ANTEIL * ref_alle) | ref_alle.isna()
    return genug.fillna(False)


def bereinigen(g: pd.DataFrame, wurzeln: list[int] | None = None
               ) -> tuple[pd.DataFrame, dict]:
    """Setzt unvollstaendige Tage EINES Landes auf 'nicht gemessen'.

    Zurueck kommt der Datensatz mit durchgehendem Tagesindex und ein
    Protokoll: wie viele Tage verworfen wurden, welcher der letzte gueltige
    Tag ist und welche Tage am rechten Rand fehlen. Der letzte gueltige Tag
    ist die Angabe, die in die Oberflaeche gehoert -- ohne sie steht dort ein
    Stand, der nicht der Stand der Ereignisdaten ist.
    """
    if g is None or not len(g):
        return pd.DataFrame(), {"verworfen": 0, "stand": None, "rand": 0}
    d = (g.sort_values("date").drop_duplicates("date")
         .set_index("date").asfreq("D").reset_index())
    ok = gueltig(d.set_index("date").n_events).to_numpy()
    spalten = [c for c in d.columns if c in ("n_events", "tone_sum", "tone_cnt")
               or c.startswith("n_")]
    verworfen = int((~ok & d.n_events.notna().to_numpy()).sum())
    d.loc[~ok, spalten] = np.nan
    gueltige = d.date[ok]
    stand = gueltige.max() if len(gueltige) else None
    rand = int((d.date.max() - stand).days) if stand is not None else 0
    return d, {"verworfen": verworfen,
               "stand": None if stand is None else stand.strftime("%Y-%m-%d"),
               "rand": rand,
               "tage": int(ok.sum())}


# ---------------------------------------------------------------- Kursreihen
#
# Dasselbe Problem auf der Marktseite: einzelne falsche Notierungen.
#
# Gefunden wurden im Bestand 80 Tage in 33.863 (0,24 %), an denen sich eine
# grosse Tagesbewegung am Folgetag wieder aufloest. Die Groessenordnungen
# schliessen ein Marktgeschehen aus:
#
#   aktien_SF   +631 % und am naechsten Tag zurueck
#   fx_RS       +272 %
#   fx_PK        +14,9 %   (Rupie wechselt taeglich zwischen 277 und 269)
#   fx_NI        +13,7 %
#
# Solange die Bausteine ueber die GESAMTE Reihe standardisiert waren, gingen
# solche Tage im Nenner unter. Mit der rollenden Normierung (die richtig ist,
# siehe index_gewichte.normieren) werden sie zu mehrfachen
# Standardabweichungen: Pakistan wies am 08.09.2026 einen Waehrungsbaustein von
# +5,62 aus, am Tag davor -2,09 und am Tag danach +0,94 -- gemeldet als
# "sprunghafter Anstieg des Risikoindex" mit +5,47 Sigma. Im Kurs steht dazu
# 277,2 -> 269,3 -> 277,1 -> 268,8 -> 277,3, also ein Zickzack um denselben
# Mittelwert. Eine echte Abwertung kehrt nicht am naechsten Tag zurueck.
#
# WAS DIE REGEL NICHT TUT
# Sie kappt keine echten Bewegungen. Eine Abwertung, die Bestand hat, wird
# nicht zurueckgenommen und bleibt deshalb erhalten -- auch eine grosse. Die
# Regel verlangt beides: aussergewoehnliche Groesse UND Rueckkehr am Folgetag.
KURS_K = 4.0          # Vielfaches der robusten Streuung
KURS_MINDEST = 0.01   # mindestens 1 % Tagesbewegung, sonst kein Kandidat
KURS_RUECK = 0.40     # so weit muss die Bewegung am Folgetag zurueckgehen


def _robuste_streuung(r: pd.Series, fenster: int = 60, min_periods: int = 20) -> pd.Series:
    """Streuung aus dem Median der absoluten Abweichungen -- der Mittelwert
    waere durch genau die Ausreisser verdorben, die gefunden werden sollen."""
    return (r.rolling(fenster, min_periods=min_periods)
             .apply(lambda x: np.median(np.abs(x - np.median(x))) * 1.4826, raw=True)
             .shift(1))


def kursausreisser(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Findet falsche Notierungen in einer Kursreihe.

    Zurueck kommen zwei Masken:
      bestaetigt    Tage mit grosser Bewegung, die am Folgetag zurueckgeht --
                    behandelbar, weil der Folgetag bekannt ist.
      unbestaetigt  nur der LETZTE Tag, wenn er eine grosse Bewegung zeigt.
                    Ob sie echt ist, entscheidet erst der naechste Tag. Bis
                    dahin ist der Tag nicht beurteilbar -- dieselbe Haltung wie
                    bei einem angebrochenen GDELT-Tag: eine Zahl, deren
                    Grundlage noch nicht feststeht, loest keine Meldung aus.
    """
    r = np.log(pd.to_numeric(close, errors="coerce")).diff()
    sig = _robuste_streuung(r)
    gross = r.abs() > np.maximum(KURS_K * sig, KURS_MINDEST)
    zurueck = ((np.sign(r) != np.sign(r.shift(-1))) &
               ((r + r.shift(-1)).abs() < KURS_RUECK * r.abs()))
    bestaetigt = (gross & zurueck).fillna(False)
    unbestaetigt = pd.Series(False, index=r.index)
    if len(r) and bool(gross.iloc[-1]):
        unbestaetigt.iloc[-1] = True
    return bestaetigt, unbestaetigt


def kurse_bereinigen(d: pd.DataFrame, spalte: str = "close") -> tuple[pd.DataFrame, int, bool]:
    """Ersetzt bestaetigte Fehlnotierungen durch den interpolierten Wert.

    Interpoliert statt geloescht, weil ein fehlender Tag in der Kursreihe die
    Tagesrendite des FOLGETAGS ueber zwei Tage laufen laesst und damit einen
    zweiten falschen Ausschlag erzeugt.
    """
    d = d.copy()
    bestaetigt, unbestaetigt = kursausreisser(d[spalte])
    n = int(bestaetigt.sum())
    if n:
        d.loc[bestaetigt, spalte] = np.nan
        d[spalte] = d[spalte].interpolate(limit_direction="both")
    return d, n, bool(unbestaetigt.any())
