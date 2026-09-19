# Länderrisiko-Monitor

Tagesaktuelles Länderrisiko für 14 Länder aus Währungsdruck, Marktvolatilität und
geopolitischer Spannung. Der Monitor ist zuerst ein **Warnwerkzeug**: er meldet
datiert, was in einem Land gerade eingetreten ist. Die Fortschreibung der Reihen
steht bewusst dahinter.

Entstanden als Weiterentwicklung der Bachelorarbeit *„Entwicklung eines
länderspezifischen Frühwarnansatzes zur ereignisbasierten Analyse geopolitischer
und wirtschaftspolitischer Unsicherheit auf Basis von GDELT"* (DHBW Mannheim).

## Was der Monitor zeigt — und was bewusst nicht

| Baustein | Grundlage | Anspruch |
|---|---|---|
| **Risikostand** | Ereignislage, Währung, Aktienvolatilität, GPR | beschreibend, Zustand |
| **Grundniveau** | dieselben Größen absolut, über ein Jahr | Rang innerhalb der Gruppe |
| **Auffälligkeit** | Abweichung vom eigenen Normalzustand | Messung der Gegenwart |
| **Lagemeldung** | Index, Einzelkomponenten, Ereignisdaten | eingetretener Zustand mit Anfangsdatum |
| **Ausblick** | Eigenhistorie jeder Reihe, AR(5) über 5 Tage | nachrangig, immer mit Rücktest |
| **Prognose 7 Tage** | Eigenhistorie des Risikoindex | Vorhersage, Güte je Land ausgewiesen |
| **Nachrichten** | GDELT 2.1 | Kontext, **keine** Prognose |

**Warnen vor Prognostizieren.** Diese Reihenfolge ist die Konsequenz aus dem Befund
der zugrunde liegenden Arbeit: die Gegenwart lässt sich aus Ereignisdaten
beschreiben, die nächsten Tage lassen sich daraus nicht belastbar vorhersagen.
Vier Meldearten: Sprung im Index, anhaltend erhöhtes Niveau, einzelne Komponente
außerhalb des Rahmens, laufende Episode oder auffällige Nachrichtenlage aus GDELT.
Jede Meldung trägt ihr Anfangsdatum — „seit wann" ist die eigentliche Information
eines Warnwerkzeugs.

**Zwei Indizes, getrennt aus einem Grund.** Der *Zustandsindex* enthält die
Ereignislage und trägt Anzeige und Meldungen. Der *Marktindex* ist derselbe
Index ohne Ereignislage und trägt alle Prognoserechnungen. Sonst entstünde
genau der Zirkelschluss, der in der zugrunde liegenden Arbeit in den
Limitationen steht: das Ereignismodell würde teilweise seine eigene Eingabe
vorhersagen. Nachgemessen hat das die AUC des Ereignismodells um
durchschnittlich **0,022** geschmeichelt, in Nigeria um 0,096.

**Zwei Achsen statt einer.** Der Risikostand ist eine Abweichung von der
*eigenen* Normallage — richtig für eine Warnung, irreführend als Rangfolge: ein
Land im Dauerkonflikt hat eine hohe Normallage, und ein ruhiger Tag darin sah
risikoärmer aus als ein ruhiger Tag in Deutschland. Daneben steht deshalb das
**Grundniveau** (`skripte/grundniveau.py`): Rangmittel aus Gewalt- und
Zwangsanteil, Tonlage, Währungs- und Marktvolatilität über ein Jahr, gerechnet
als Rang *innerhalb* der überwachten Länder. Die Stufe ist das **Viertel** der
Gruppe, nicht eine Schwelle auf der Punkteskala: die Punkte sind ein Mittel aus
Rangprozenten und liegen fast zwangsläufig in der Mitte — mit festen Schwellen
hießen zehn von siebzehn Ländern „erhöht". Auf der Karte trägt die Fläche das
Grundniveau, die Marke die heutige Meldelage.

**Welche Ereignisse zählen.** Eine Prüfung an 434.204 Ereigniszeilen ergab: 28 %
der Deutschland zugeordneten Konfliktereignisse hatten ihren Handlungsort
außerhalb Deutschlands, und derselbe Artikel erschien mehrfach, weil GDELT eine
Zeile je *Erwähnung* ausgibt — die Kritik von Schrodt (2012), in der Arbeit
zitiert, in der Verarbeitung bis dahin nicht umgesetzt. `skripte/gdelt_filter.py`
verlangt jetzt Handlungsort im Land, einen Akteur des Landes, und entfernt
Duplikate je Quelle: Deutschland 15.341 → 3.000 Zeilen, USA 384.562 → 117.968,
bei nahezu unverändertem Konfliktanteil. Der Filter wirkt auf neu geladene Tage;
`daten/filterwechsel.json` hält fest, ab wann.

**Karte für den Lieferkettenfall.** Eine Weltkarte (`#/karte`) färbt die überwachten
Länder nach ihrer dringlichsten Meldung und legt die großen Seewege darüber. Ein
Nadelöhr gilt als betroffen, wenn eines seiner Anrainerländer im Monitor liegt und
dort eine Meldung offen ist; wo kein Anrainer überwacht wird, bleibt es grau — eine
Abdeckungslücke, ausdrücklich keine Entwarnung. Die Ländergeometrie liegt separat in
`docs/weltkarte.json` (Natural Earth 110 m, vereinfacht), damit die Datendatei des
täglichen Laufs klein bleibt.

**Rechnungen getrennt vom Lagebild.** Die Lageansichten zeigen Ergebnisse. Jede
Prüfzahl — Rücktestfehler, AUC, Nullmodell — steht gesammelt auf einer eigenen
Seite (`#/rechnungen`), damit im Monitor das Ergebnis steht und nicht der
Rechenweg.

**Jede Fortschreibung mit Messlatte.** Zu jeder Reihe wird der mittlere absolute
Fehler der Fortschreibung ausgewiesen und daneben derselbe Fehler für die
einfachste denkbare Regel: den letzten Wert beibehalten. Eine Fortschreibung, die
diese Regel nicht schlägt, wird als solche gekennzeichnet.

**Keine Monatsprognose.** Auf 21 Tage Vorlauf liegt selbst das beste Modell auf
Zufallsniveau. Eine solche Anzeige wäre eine Behauptung ohne Deckung.

**GDELT liefert keine Prognose.** In 47 geprüften Konstellationen — vier externe
Unsicherheitsindizes, Horizonte von 3 bis 60 Tagen, 19 Länder, Tages- und
Monatsauflösung, jeweils mit fairer Baseline und Konfidenzintervall — war kein
Prognosebeitrag von GDELT nachweisbar. Die **Fortschreibung** enthält deshalb
keine GDELT-Merkmale.

**Im Zustand aber schon.** Der Risikoindex beschreibt die heutige Lage
gegenüber der eigenen Normallage; das ist eine Zustandsgröße, keine Prognose.
Ereignisdaten können das belegbar leisten, und ohne sie war der Index blind für
genau die Fälle, für die es ihn gibt: Nigeria stand am 09.09.2026 bei −0,76,
während der Anteil der Zwangsereignisse 2,19 Standardabweichungen über der
Normallage lag. Der Index hat deshalb vier Bausteine — Ereignislage,
Währungsdruck, Marktvolatilität, globales Umfeld — mit kalibrierten Gewichten
(`skripte/gewichte_kalibrieren.py`) und einer Eskalationsklausel, damit ein
einzelner ausbrechender Baustein nicht weggemittelt wird.

## Länderauswahl

Aufgenommen wird ein Land nur, wenn seine Währung frei gehandelt und marktgestellt
ist. Ausgeschlossen sind feste Bindungen (CFA-Franc an den Euro, irakischer Dinar
an den Dollar) und amtlich gestellte Kurse (Libanon, Syrien, Jemen, Sudan, Somalia,
Iran, Venezuela, Myanmar) — deren Kurse bilden die Ankerwährung oder eine
Verwaltungsentscheidung ab, nicht das Landesrisiko.

Israel · Russland · Ukraine · Nigeria · Pakistan · Taiwan · Türkei · Brasilien ·
Südafrika · Indien · Mexiko · Ägypten · USA · Deutschland · Malaysia · Indonesien ·
Spanien · Saudi-Arabien

Die letzten vier kamen für die Kartenansicht dazu, als Anrainer von Malakka-,
Sunda- und Gibraltarstraße sowie des Roten Meeres. Bei Spanien und
Saudi-Arabien entfällt der Währungsbaustein — Euro beziehungsweise fester
Dollar-Anker —, sie tragen wie Deutschland und die USA über die
Marktvolatilität. Panama (US-Dollar), Jemen und Dschibuti (amtlich gestellt
beziehungsweise gebunden) und Marokko (Korbbindung) bestehen die
Währungsregel **nicht**; Panamakanal, Bab el-Mandeb und Hormus bleiben auf der
Karte deshalb grau.

## Aufbau

```
skripte/config.py           Länder, Symbole, Parameter
skripte/aktualisieren.py    täglicher Lauf
skripte/gdelt_filter.py     welche Ereigniszeile einem Land zuzurechnen ist
skripte/tagesgueltigkeit.py welche Tage überhaupt messbar sind (GDELT und Kurse)
skripte/grundniveau.py      Grundrisiko je Land (langsame Achse)
skripte/index_gewichte.py   Bausteine, Gewichte, Aggregation des Index
skripte/gewichte_kalibrieren.py  Gewichte an extern datierten Krisen prüfen
skripte/warnungen.py        Lagemeldungen (erste Ebene)
skripte/meldungen_versenden.py   versandfertige Warnung mit Gedächtnis
skripte/ausblick.py         Fortschreibung je Reihe (zweite Ebene, nachrangig)
skripte/krisen.py           Episodenerkennung in den Ereignisdaten
skripte/erstbefuellung.py   einmaliger Transfer der Historie
daten/                      abgeleitete Daten (klein, versioniert)
docs/                       das Dashboard für GitHub Pages
docs/weltkarte.json         Ländergeometrie der Karte (einmalig, unveränderlich)
.github/workflows/          Zeitplan
```

Der GDELT-Rohbestand von 2,1 GB liegt **nicht** im Repository. Der tägliche Lauf
lädt die letzten Tage frisch, verdichtet sie sofort auf Land-Tag-Aggregate und
verwirft die Rohdateien. Versioniert werden nur die abgeleiteten Dateien.

## Einrichtung

```bash
python3 skripte/erstbefuellung.py     # einmalig, übernimmt die Historie
python3 skripte/aktualisieren.py      # Testlauf
cd docs && python3 -m http.server     # lokal ansehen unter localhost:8000
```

Danach in den Repository-Einstellungen unter **Pages** als Quelle den Branch
`main` und den Ordner `/docs` wählen. Der Workflow läuft täglich um 04:00 UTC
und lässt sich unter *Actions* auch von Hand starten.

### E-Mail bei Auffälligkeiten (optional)

Drei Secrets unter *Settings → Secrets and variables → Actions* anlegen:
`MAIL_USER`, `MAIL_PASSWORT` (bei Gmail ein App-Passwort, nicht das
Kontopasswort), `MAIL_EMPFAENGER`. Fehlen sie, überspringt der Workflow den
Schritt und gilt trotzdem als erfolgreich.

## Datenquellen

- **GDELT 2.1** — Ereignisdaten, CAMEO-kodiert
- **Yahoo Finance** — Wechselkurse und Aktienindizes
- **Geopolitical Risk Index** — Caldara & Iacoviello, täglich
- **UCDP GED** — Konfliktdaten (in der Untersuchung, nicht im laufenden Monitor)

## Datenqualität: welche Tage überhaupt zählen

Die Prüfung steht in `skripte/tagesgueltigkeit.py` und gilt für beide Quellen.
Sie ist nicht kosmetisch — vor ihrer Einführung gingen sechs von neun offenen
Lagemeldungen auf Datenfehler zurück.

**Ereignistage.** Die Ereignisanteile sind Quotienten: Gewaltanteil ist
(CAMEO 18+19+20) geteilt durch alle Ereignisse des Tages. Wird ein Tag nur
teilweise geerntet — der laufende Tag, ausgefallene Einzeldateien, ein Ausfall
bei GDELT —, schrumpft der **Nenner** und der Anteil steigt, ohne dass im Land
etwas passiert ist. Gemessen im eigenen Bestand: dünne Tage stellen 0,94 % aller
Tage, aber 2,29 % aller Überschreitungen von zwei Standardabweichungen, also das
2,4-fache ihres Anteils. Saudi-Arabien wies an solchen Tagen einen mittleren
Gewaltanteil von 70 % aus gegenüber 4,1 % an normalen Tagen.

Ein Tag gilt als gemessen, wenn er mindestens 30 Ereignisse und mindestens 40 %
der üblichen Menge **desselben Wochentags** enthält (Median der letzten acht).
Der Vergleich je Wochentag ist nötig, weil die Tagesmenge stark davon abhängt —
USA Donnerstag 50.945, Samstag 29.107, Sonntag 20.916 Ereignisse im Median. Ein
Maßstab aus allen Tagen hätte bei den USA 184 statt 27 Tagen verworfen, fast nur
Wochenenden. Ein verworfener Tag wird auf *nicht gemessen* gesetzt, nicht auf
null: null hieße „heute ist nichts passiert" und würde die Normallage senken.

**Kursreihen.** Dieselbe Frage auf der Marktseite. Im Bestand stehen 80 Tage in
33.863 (0,24 %), an denen sich eine große Tagesbewegung am Folgetag wieder
auflöst — der südafrikanische Aktienindex mit +631 %, der Rubel mit +272 %, die
pakistanische Rupie mit +14,9 % im täglichen Zickzack zwischen 277 und 269.
Verlangt werden beide Bedingungen: außergewöhnliche Größe **und** Rückkehr am
Folgetag. Eine Abwertung, die Bestand hat, bleibt erhalten. Bestätigte
Fehlnotierungen werden interpoliert; eine Bewegung am **letzten** Tag ist noch
nicht entscheidbar, dieser Tag gilt deshalb als nicht beurteilbar und löst keine
Meldung aus. Ein Tag Verzug gegen einen Fehlalarm ist für ein Warnwerkzeug der
richtige Tausch.

**Fehlt ein Baustein nur heute**, wird der Index nicht aus den übrigen
hochgerechnet. Israel stand am 09.09.2026 bei −0,74 σ mit einer Ereignislage von
+0,85 und am 10.09. bei −2,18 σ, nachdem die Ereignisdaten ausgelaufen waren:
gefallen war nicht die Lage, sondern die Messung. Unterschieden wird über eine
Karenz von 30 Tagen — ein dauerhaft fehlender Baustein (die Ukraine hat keinen
brauchbaren Aktienindex) wird herausnormiert, ein heute fehlender macht den Tag
unlesbar. Der Zustandswert bezieht sich dann auf den letzten Tag mit
vollständigen Bausteinen, und die Oberfläche nennt Datum und Grund.

**Die Erntequote.** GDELT veröffentlicht 96 Dateien je Tag im Viertelstundentakt.
Schlägt ein Teil der Abrufe fehl, wurde der Tag früher trotzdem geschrieben. Der
Nachweis steckte im eigenen Bestand: derselbe Kalendertag ergab in zwei
Ladesitzungen verschiedene Werte — Deutschland 1.883 Ereignisse am 08.09.2026
gegen 120 bis 437 an Nachbartagen aus einer anderen Sitzung, bei identischer
Masterliste mit 96 Dateien für jeden Tag. Das Niveau hing daran, *wann* geladen
wurde. Jeder Tag führt jetzt seine Quote im Manifest mit; unter 95 % gilt er
nicht als geladen und wird beim nächsten Lauf erneut geholt. Der tägliche Lauf
übernimmt einen Tag unter dieser Schwelle gar nicht erst. Die Historie lädt mit
vier statt acht parallelen Abrufen und fünf statt drei Versuchen, weil die
Fehlschläge gebündelt bei hoher Parallelität auftraten.

**Ein echter Bruch in der Quelle.** Anfang Dezember 2024 sinkt die
Ereignismenge von GDELT dauerhaft, im Median um den Faktor 4,7. Das ist kein
Verarbeitungsfehler: eine unvollständige Ernte trifft alle Länder mit demselben
Faktor, hier reicht er von 2,9 (USA) bis 10,7 (Südafrika) bei einer Streuung von
1,73 — und die CAMEO-Anteile bleiben nahezu unverändert (Gewaltanteil 8,21 %
davor, 7,60 % danach). Das ist die Handschrift einer veränderten
Quellenzusammensetzung, nicht einer veränderten Zurechnung. Belege und
Einordnung in `daten/abdeckungsbruch.json`. Absolute Ereigniszahlen sind über
diesen Bruch hinweg nicht vergleichbar; rollende z-Werte und Anteile sind es,
sobald das Referenzfenster vollständig auf einer Seite liegt.

## Eine Skala für alle Bausteine

Die vier Bausteine hatten drei verschiedene Bezugsbasen: Währung und Markt waren
über die **gesamte** eigene Reihe standardisiert, der globale GPR über seine
Historie, die Ereignislage rollend über 60 Tage und zusätzlich als Maximum
dreier z-Werte. Gemessen über den ganzen Bestand lagen die Mittelwerte bei 0,00 /
0,00 / +0,83 / +0,60 und die Anteile der Tage über 2 σ bei 2,2 / 4,9 / 11,2 /
5,3 %. Ein gewichtetes Mittel daraus ist nicht in Standardabweichungen lesbar,
und die Eskalationsklausel griff bevorzugt beim globalen GPR — dem einen
Baustein, der zwischen Ländern gar nicht trennt.

Alle vier werden jetzt vor der Gewichtung rollend über 120 Handelstage normiert
(`index_gewichte.normieren`); die Anteile über 2 σ liegen danach bei 6,6 / 8,9 /
4,7 / 4,6 %. Nebeneffekt: die Standardisierung über die gesamte Reihe benutzte
Mittelwert und Streuung auch der Tage **nach** t. Für die GDELT-Merkmale war das
von Anfang an ausgeschlossen, für die Marktbausteine nicht — jetzt gilt für
beide dieselbe Regel.

Daraus folgt auch, dass Lagemeldung, Kurve und Index dieselbe Zahl nennen. Vorher
rechnete `warnungen.py` einen eigenen z-Wert auf den Baustein und meldete für die
Türkei „Währungsdruck außergewöhnlich hoch, +2,26 σ", während dieselbe Kurve auf
derselben Seite bei −0,32 σ lag.

**Was σ hier nicht heißt.** Die Schwellen sind Quantile dieser Reihen, keine
Wahrscheinlichkeiten aus einer Normalverteilung. Der Gesamtindex liegt in 9,5 %
der Tage über 1,5 σ und in 2,6 % über 2,5 σ; unter Normalverteilung wären 6,7 %
und 0,6 % zu erwarten. Volatilitäts- und Anteilsreihen haben schwere Ränder.

## Grenzen

Prototyp im Rahmen einer Bachelorarbeit. Keine Anlage- oder Risikoberatung.
Die Nachrichtenüberschriften sind aus Quell-URLs abgeleitet und daher eine
Näherung. Wechselkurse aus frei verfügbaren Quellen können bei kleineren
Währungen ungenau sein.
