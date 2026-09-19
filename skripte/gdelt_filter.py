"""
gdelt_filter.py -- welche GDELT-Zeile zaehlt fuer welches Land.

DER BEFUND, DER DIESE DATEI AUSGELOEST HAT
Deutschlands Episoden "Bewaffneter Konflikt" liessen sich nachpruefen. In einer
Stichprobe von 434.204 Ereigniszeilen aus dem Bestand der Arbeit trafen 15.341
Zeilen Deutschland. Von den darin als CAMEO 18-20 codierten Ereignissen lagen
211 von 740 -- 28 Prozent -- mit ihrem HANDLUNGSORT ausserhalb Deutschlands
(USA, Russland, Polen, Israel, Ukraine). Sie trafen nur zu, weil Deutschland in
einem anderen Geofeld auftauchte. Unter den nach Goldstein negativsten
Ereignissen standen ausserdem "Remembering Auschwitz 80 years on", ein
Weltkriegswrack vor Brasilien und ein Schulattentat in Schweden: historische
Bezuege und Auslandsmeldungen mit deutscher Erwaehnung, keine Lage in
Deutschland.

Und derselbe Artikel erschien mehrfach: die Mirror-Meldung fuenfmal, der
Auschwitz-Text dreimal. GDELT gibt eine Zeile je Erwaehnung aus, nicht je
Ereignis. Genau das ist die Kritik, die Schrodt (2012) an maschinell codierten
Ereignisdaten formuliert -- in der Arbeit zitiert, aber in der Verarbeitung
nicht umgesetzt.

DREI STUFEN, EINZELN ABSCHALTBAR
  Handlungsort   ActionGeo muss das Land sein, nicht irgendeines der drei
                 Geofelder. Faengt die Auslandsmeldung mit deutscher
                 Erwaehnung.
  Akteur         zusaetzlich muss Actor1 oder Actor2 das Land sein. Faengt die
                 Meldung, die im Land spielt, aber niemanden aus dem Land
                 betrifft.
  Duplikate      eine Zeile je (Ereignistag, Quell-URL, CAMEO-Wurzel). Halbiert
                 den Bestand -- und zwar den Teil, der bisher als "mehr
                 Ereignisse" gezaehlt wurde.

WIRKUNG, GEMESSEN
  Deutschland  15.341 -> 3.000 Zeilen (-80 %), Konfliktanteil 4,82 -> 5,87 %
  USA         384.562 -> 117.968 Zeilen (-69 %), Konfliktanteil 7,57 -> 8,39 %

Der ANTEIL bewegt sich also kaum -- die Merkmale der Arbeit, die auf Anteilen
beruhen, sind gegen diese Verzerrung weitgehend robust. Was sich stark aendert,
sind die MENGE und die Auswahl der angezeigten Ueberschriften. Beides gehoert
zu dem, was der Monitor behauptet, also wird beides korrigiert.

WICHTIG: NIVEAUBRUCH
Der Filter wirkt auf neu geladene Tage. Solange die Historie nicht mit
demselben Filter neu geladen ist (gdelt_historie.py), hat die Ereigniszahl an
seinem Einsatztag einen Sprung nach unten. Der Lauf schreibt das Datum in
daten/filterwechsel.json, damit der Bruch benannt und nicht entdeckt werden
muss.
"""
from __future__ import annotations

import pandas as pd

# FIPS 10-4 (GDELT-Geofelder) -> ISO 3166-1 alpha-3 (GDELT-Akteursfelder).
# Zwei Schemata in derselben Datei, wie schon bei FIPS gegen ISO2 in config.py.
ISO3 = {"IS": "ISR", "RS": "RUS", "UP": "UKR", "NI": "NGA", "PK": "PAK",
        "TW": "TWN", "TU": "TUR", "BR": "BRA", "SF": "ZAF", "IN": "IND",
        "MX": "MEX", "EG": "EGY", "US": "USA", "GM": "DEU",
        "MY": "MYS", "ID": "IDN", "SP": "ESP", "SA": "SAU"}

# Anzeigefilter fuer Ueberschriften. Er wirkt AUSSCHLIESSLICH auf die Auswahl
# der angezeigten Meldungen, nie auf die Messung -- eine Kennzahl, die von
# einer Stichwortliste abhaengt, waere nicht mehr nachvollziehbar. Getroffen
# werden historische Rueckblicke und Unterhaltung, die als Konfliktereignis
# codiert werden, weil der Text Gewalt beschreibt.
SLUG_AUS = (
    "auschwitz", "holocaust", "wwii", "ww2", "world-war", "weltkrieg",
    "nazi-era", "remembering", "anniversary", "obituary", "death-row",
    "true-crime", "cold-case", "documentary", "movie", "film-review",
    "trailer", "lyrics", "interview", "recipe", "podcast", "episode-",
    "throwback", "on-this-day", "years-ago", "history-of",
)


def zeilen_filtern(t: pd.DataFrame, code: str, *, handlungsort: bool = True,
                   akteur: bool = True, duplikate: bool = True,
                   sp_action: str = "G3", sp_a1: str = "C7", sp_a2: str = "C17",
                   sp_url: str = "surl", sp_tag: str = "C1",
                   sp_root: str = "C28") -> pd.DataFrame:
    """Verengt die Zeilen eines Tages auf die, die dem Land zuzurechnen sind.

    Erwartet den bereits auf das Land vorgefilterten Ausschnitt (irgendeines
    der drei Geofelder trifft) und die benannten Spalten des Monitorbestands.
    Fehlt eine Spalte, wird die zugehoerige Stufe uebersprungen statt zu
    scheitern -- ein aelterer Bestand ohne Akteursspalten soll weiter laufen,
    nur eben ohne diese Verengung.
    """
    if t.empty:
        return t
    behalten = pd.Series(True, index=t.index)

    if handlungsort and sp_action in t.columns:
        behalten &= t[sp_action].fillna("").astype(str).eq(code)

    if akteur and code in ISO3 and sp_a1 in t.columns and sp_a2 in t.columns:
        iso = ISO3[code]
        a1 = t[sp_a1].fillna("").astype(str)
        a2 = t[sp_a2].fillna("").astype(str)
        behalten &= (a1.eq(iso) | a2.eq(iso))

    aus = t.loc[behalten]
    if duplikate and len(aus):
        # Schluessel: Ereignistag, Quelle, CAMEO-Wurzel. NICHT die
        # GlobalEventID -- die ist je Erwaehnung verschieden und wuerde nichts
        # entfernen.
        schluessel = [c for c in (sp_tag, sp_root, sp_url) if c in aus.columns]
        if len(schluessel) >= 2:
            aus = aus.drop_duplicates(subset=schluessel)
    return aus


def slug_erlaubt(url: str) -> bool:
    """Anzeigefilter fuer eine Ueberschrift. Nur Anzeige, nie Messung."""
    u = (url or "").lower()
    return not any(w in u for w in SLUG_AUS)
