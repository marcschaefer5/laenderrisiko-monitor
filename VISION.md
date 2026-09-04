# Länderrisiko-Monitor — Zielbild und Leitplanken

Stand: 03.09.2026. Diese Datei hält fest, wohin das Produkt soll und welche
Regeln dabei nicht verhandelbar sind. Sie ist der Bezugspunkt für jede
spätere Entscheidung — auch wenn der Gesprächsverlauf längst vergessen ist.

## 1. Was das Produkt ist

Ein Frühwarn- und Lagebild für Länderrisiko, auf **Tagesebene**, für
**Unternehmen** gedacht (Lieferketten, Absatzmärkte, Standortentscheidungen).
Nicht nur Konflikt: wirtschaftliche Schwäche, Inflation, Währungsdruck,
Marktstress gehören gleichrangig dazu.

Drei Dinge muss es können:

1. **Überblick geben** — alle Länder auf einen Blick, sortierbar nach Lage.
2. **Warnen** — wenn irgendwo etwas plötzlich passiert, ungefragt melden.
3. **Prognostizieren** — nicht nur beschreiben, was ist, sondern was kommt.

Zugriff über das Handy wie eine App. Der Betrieb läuft ohne eigenen Rechner
(GitHub Actions, täglich).

## 2. Zielbild der Länderseite

Reihenfolge von oben nach unten:

1. **Steckbrief** — drei bis vier Kennzahlen in gedämpftem Grau, klein:
   Fläche, Bevölkerung, BIP pro Kopf, Währung. Kein Blickfang, nur Kontext.
2. **Kurzüberblick** — zwei, drei Sätze: was für ein Land ist das, wovon
   hängt es wirtschaftlich ab.
3. **Krisen** — welche Lagen laufen gerade? Bewaffneter Konflikt, Proteste,
   Währungskrise, Inflationsschub, politische Instabilität. Jeweils mit
   Beginn, Intensität und Quelle. **Das ist die Kategorie, für die GDELT
   tatsächlich taugt** (siehe Abschnitt 4).
4. **Prognosen** — mehrere nebeneinander, jede mit ihrer gemessenen Güte:
   - Länderrisiko (Markt) — vorhanden
   - Länderrisiko (Ereignisse/GDELT) — vorhanden
   - Wirtschaftswachstum — offen
   - Inflation — offen
   - weitere, teils eingesammelt (IWF, Weltbank, Consensus), teils selbst
     gerechnet. Eingesammelte und eigene Prognosen sind **immer als solche
     gekennzeichnet**.
5. **Historie** — zu jeder Prognose der Verlauf. Eine Prognose ohne Historie
   lässt sich nicht beurteilen; erst der Rückblick zeigt, ob das Modell in
   der Vergangenheit recht hatte.
6. **Aktuelle Ereignisse** — die einflussreichsten Meldungen je Tag.

## 3. Leitplanken (nicht verhandelbar)

- **Tagesauflösung.** Monatsdaten sind kein Frühwarnsystem.
- **Jede Prognose trägt ihre Güte.** Eine Prozentzahl ohne AUC daneben ist
  eine Behauptung. Liegt die Güte auf Zufallsniveau, wird das im Dashboard
  ausdrücklich hingeschrieben, nicht versteckt.
- **Jede Prognose trägt ihre Messlatte.** Verglichen wird immer gegen das
  Nullmodell (Persistenz: „morgen wie heute"). Ein Modell, das die Messlatte
  nicht schlägt, hat nichts gelernt — egal wie hoch seine AUC absolut ist.
- **Zeitgeordnete Validierung.** Expandierendes Fenster, kein Shuffle, keine
  Zukunft im Training. Und: **überall dieselbe Methode.** Zwei verschiedene
  Zahlen für dasselbe Modell an zwei Stellen sind ein Fehler, kein Detail.
- **Kein Zirkelschluss.** Zielvariable und Merkmale dürfen nicht aus
  derselben Quelle durch Transformation auseinander hervorgehen. Das war der
  Kernfehler der Bachelorarbeit und darf sich nicht wiederholen.
- **Ein leeres Ergebnis ist verdächtig.** Ein Filter, der nichts durchlässt,
  muss laut sein. Lautlose Nullen haben hier zwei Fehler wochenlang
  verdeckt (siehe CHANGELOG-Abschnitt unten).
- **Relativ ist nicht absolut.** Der Risikoindex misst Abweichung von der
  landeseigenen Normallage. Russland kann „ruhiger als normal" sein und
  trotzdem Kriegsgebiet. Beide Achsen gehören ins Bild.

## 4. Was GDELT kann — und was nicht

### Der Endstand der Messung (04.09.2026)

Grundlage: 14 Länder, tägliche GDELT-Daten ab 01.02.2023, **6.683 bewertete
Ländertage**, zeitgeordnetes expandierendes Fenster, gepaartes
Bootstrap-Konfidenzintervall über 2.000 Ziehungen.

| Merkmalsvariante | AUC des reinen Ereignismodells | Beitrag über das Marktmodell hinaus |
|---|---|---|
| roh (7 Merkmale) | Mittel **0,497**, Median **0,500**, Spanne 0,379–0,592 | Median **−0,016**, in 7 von 14 Ländern signifikant negativ, in **0** signifikant positiv |
| geglättet (16 Merkmale) | Mittel **0,506**, Median 0,516, Spanne 0,372–0,623 | Median **−0,032**, in 9 von 14 signifikant negativ, in **0** signifikant positiv |

Der Mittelwert 0,497 ist die aussagekräftigste Zahl des ganzen Projekts:
**exakt Münzwurf.** Nicht „schwach", nicht „uneindeutig", nicht „zu wenig
Daten" — sondern kein Effekt, gemessen mit einer Präzision, die keinen Raum
für einen versteckten übrig lässt. Die Werte streuen symmetrisch um 0,5; es
gibt auch keinen umgekehrten Zusammenhang, den man ausnutzen könnte.

### Der Modellklassen-Test (04.09.2026)

Alle bisherigen Konstellationen benutzten logistische Regression. Damit war
streng genommen nur gezeigt: EIN LINEARES Modell findet nichts. Der Einwand
— ein Ereigniseffekt könnte nichtlinear wirken, erst ab einer Schwelle oder
nur im Zusammenspiel von Gewaltanteil und Ton — wurde mit Gradient Boosting
geprüft (`vergleich_modellklasse.py`, `D38_modellklasse_eskalation.py`):
gleiche Tage, gleiche Merkmale, gleiche zeitgeordnete Validierung,
konservativ parametriert (Tiefe 3, Lernrate 0,05, L2-Regularisierung).

| | logistisch | Gradient Boosting |
|---|---|---|
| GDELT allein, Median über 14 Länder | 0,500 | **0,475** |
| Marktmodell allein, Median | 0,841 | 0,825 |
| GDELT-Beitrag, Median | −0,016 | **−0,027** (0 von 14 positiv) |
| Eskalationsziel: GDELT allein | 0,487 | **0,445** |
| Eskalationsziel: C − B | −0,019 [−0,042, +0,001] | **−0,064 [−0,114, −0,015]** |

Die flexiblere Modellklasse macht es in **beiden** Aufgaben schlechter, nicht
besser. Das ist das erwartete Muster, wenn kein Signal vorhanden ist: mehr
Flexibilität heisst dann nur mehr Möglichkeiten, Trainingsrauschen
auswendig zu lernen. Auch das Marktmodell verliert leicht (0,841 → 0,825) --
ein Beleg dafür, dass die Parametrierung nicht zu schwach gewählt war,
sondern die Datenmenge die Grenze setzt.

**Damit ist der Einwand erledigt: es liegt nicht an der Modellklasse.**

### Gesamtbilanz

Zusammen mit der früheren Prüfreihe (47 Konstellationen: fünf
Zielkonstruktionen, Horizonte von einem Tag bis drei Monaten, 19 Länder),
den 28 Konstellationen im jetzigen Tagesdesign und den 16 des
Modellklassen-Tests sind das **91 geprüfte Konstellationen — zwei
Zielgrössen aus getrennten Datenwelten, zwei Modellklassen, Horizonte von
einem Tag bis drei Monaten, bis zu 21 Länder — ohne einen einzigen positiven
Befund.**

Der zweite Befund gehört daneben, weil er sonst untergeht: das Marktmodell
schlägt die Persistenzregel im Median um **+0,009** und nur in 1 von 14
Ländern signifikant. Auch das bessere Modell weiß kaum mehr als „morgen ist
wie heute". Das ist keine Schwäche der Arbeit, sondern eine Eigenschaft von
Finanzzeitreihen — entscheidend ist, dass es gemessen und ausgewiesen wird.

**Wofür GDELT taugt:** Ereignisse *erkennen und einordnen*, während sie
passieren. Das ist eine Nowcast-Aufgabe, keine Prognoseaufgabe. Konkret:

- **Krisenerkennung** aus der CAMEO-Zusammensetzung: erhöhter Gewaltanteil
  (18/19/20), Protestwelle (14), Repression (17) — je Land, je Tag, gegen
  die eigene Normallage normiert.
- **Ereignis-Anomalien** als eigenständiges Warnsignal, unabhängig vom
  Marktindex. Wenn beide gleichzeitig ausschlagen, ist das ein stärkeres
  Signal als jedes für sich.
- **Belegkette**: zu jedem Ausschlag die konkreten Meldungen, die ihn
  ausgelöst haben.

Das ist die ehrliche Nutzung: GDELT liefert die Kategorie **Krisen** und die
**Ereignis-Warnung**, nicht die Marktprognose.

## 5. Erledigt / offen

Erledigt:
- Tägliche Pipeline (GDELT + Yahoo + GPR), GitHub Actions
- Risikoindex aus Währungsdruck, Marktvolatilität, GPR; Auffälligkeitsregel
- Zwei Prognosen mit Güte und Persistenz-Messlatte
- Nachrichten aus Quell-URLs, Kennungs-Slugs gefiltert
- Modellvergleich `vergleich_gdelt.py` mit gepaartem Bootstrap-KI
- Krisenerkennung `krisen.py` (Episoden mit Hysterese) auf der Länderseite
- Modellklassen-Test (logistisch gegen Gradient Boosting), beide Zielgrössen
- GDELT-Historie für alle 14 Länder ab 01.02.2023

### Datengrundlage GDELT (Stand 04.09.2026)

Alle 14 Länder: tägliche Aggregate ab 01.02.2023, rückwirkend geladen mit
`gdelt_historie.py`.

**Validierung gegen die Bestandsdaten der Bachelorarbeit** (10.376 gemeinsame
Tag/Land-Paare): Korrelation der Ereigniszahlen **0,9973**, Korrelation des
Gewaltanteils **0,9738**, mittlere absolute Abweichung des Gewaltanteils
**0,002**. Die neue Pipeline reproduziert die alte.

Die neuen Werte liegen systematisch rund 2 % unter den alten. Das ist kein
Fehler, sondern eine bewusste Regel: `gdelt_historie.py` zählt ein Ereignis
nur aus den Dateien SEINES Tages. Spät gemeldete Ereignisse, die erst am
Folgetag in den Dateien auftauchen, fehlen dadurch. Weil der Index
ausschliesslich mit rollenden z-Werten arbeitet, hebt sich eine gleichmässige
Niveauverschiebung heraus.

**Bekannte Lücke: 15.06.–01.07.2025.** GDELT hat für diese 17 Tage keine
Dateien mehr im Angebot (in der Masterliste stehen null Einträge; auch die
lokale Parquet-Ablage enthält sie nicht). Für die acht ursprünglichen Länder
liegen aus einem früheren Download noch Werte vor, für die sechs neuen nicht.
Diese Asymmetrie ist beim Ländervergleich in diesem Fenster zu beachten.

Offen:
- Steckbrief und Kurzüberblick auf der Länderseite
- Wachstums- und Inflationsprognose
- Absolutes Niveau neben der relativen Abweichung
- Länderspezifischer GPR statt des globalen Index

## 6. Behobene Fehler, die sich nicht wiederholen dürfen

| Fehler | Symptom | Lehre |
|---|---|---|
| `geo_indizes` um 2 verschoben | 96/96 Dateien geladen, null Treffer | Positionsformeln gegen echte Daten prüfen, nicht gegen Erinnerung |
| `SOURCEURL` auf `C60` festgenagelt | Nachrichten dauerhaft leer | Spalten am Inhalt erkennen, nicht an der Position |
| Tote Marktreihe (IMOEX seit 2024) | Russland auf 2024 eingefroren | Datenqualität hat zwei Achsen: Umfang **und** Aktualität |
| Wechselnde Index-Zusammensetzung | Vier falsche Auffälligkeiten | Nur vollständige Tage ausweisen |
| Einmal-Split vs. expandierendes Fenster | Zwei AUC für dasselbe Modell | Eine Methode, überall |
| `SQLDATE` ungefiltert übernommen | Streutage bis 2016 im Bestand | Ereignisdatum ist nicht Meldedatum |
| — | — | Eine neue Pipeline wird gegen die alte validiert, bevor sie sie ersetzt |
