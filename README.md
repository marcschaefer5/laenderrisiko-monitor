# Länderrisiko-Monitor

Tagesaktuelles Länderrisiko für 14 Länder aus Währungsdruck, Marktvolatilität und
geopolitischer Spannung — mit Auffälligkeitserkennung, Kurzfristprognose und
Nachrichtenkontext aus GDELT.

Entstanden als Weiterentwicklung der Bachelorarbeit *„Entwicklung eines
länderspezifischen Frühwarnansatzes zur ereignisbasierten Analyse geopolitischer
und wirtschaftspolitischer Unsicherheit auf Basis von GDELT"* (DHBW Mannheim).

## Was der Monitor zeigt — und was bewusst nicht

| Baustein | Grundlage | Anspruch |
|---|---|---|
| **Risikostand** | Währung, Aktienvolatilität, GPR | beschreibend |
| **Auffälligkeit** | Abweichung vom eigenen Normalzustand | Messung der Gegenwart |
| **Prognose 7 Tage** | Eigenhistorie des Risikoindex | Vorhersage, Güte je Land ausgewiesen |
| **Nachrichten** | GDELT 2.1 | Kontext, **keine** Prognose |

**Keine Monatsprognose.** Auf 21 Tage Vorlauf liegt selbst das beste Modell auf
Zufallsniveau. Eine solche Anzeige wäre eine Behauptung ohne Deckung.

**GDELT liefert keine Prognose.** In 47 geprüften Konstellationen — vier externe
Unsicherheitsindizes, Horizonte von 3 bis 60 Tagen, 19 Länder, Tages- und
Monatsauflösung, jeweils mit fairer Baseline und Konfidenzintervall — war kein
Prognosebeitrag von GDELT nachweisbar. Der Risikoindex enthält deshalb keine
GDELT-Merkmale.

## Länderauswahl

Aufgenommen wird ein Land nur, wenn seine Währung frei gehandelt und marktgestellt
ist. Ausgeschlossen sind feste Bindungen (CFA-Franc an den Euro, irakischer Dinar
an den Dollar) und amtlich gestellte Kurse (Libanon, Syrien, Jemen, Sudan, Somalia,
Iran, Venezuela, Myanmar) — deren Kurse bilden die Ankerwährung oder eine
Verwaltungsentscheidung ab, nicht das Landesrisiko.

Israel · Russland · Ukraine · Nigeria · Pakistan · Taiwan · Türkei · Brasilien ·
Südafrika · Indien · Mexiko · Ägypten · USA · Deutschland

## Aufbau

```
skripte/config.py           Länder, Symbole, Parameter
skripte/aktualisieren.py    täglicher Lauf
skripte/erstbefuellung.py   einmaliger Transfer der Historie
daten/                      abgeleitete Daten (klein, versioniert)
docs/                       das Dashboard für GitHub Pages
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

## Grenzen

Prototyp im Rahmen einer Bachelorarbeit. Keine Anlage- oder Risikoberatung.
Die Nachrichtenüberschriften sind aus Quell-URLs abgeleitet und daher eine
Näherung. Wechselkurse aus frei verfügbaren Quellen können bei kleineren
Währungen ungenau sein.
