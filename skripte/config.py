"""
config.py -- zentrale Konfiguration des Laenderrisiko-Monitors.

LAENDERAUSWAHL
Aufgenommen wird ein Land nur, wenn seine Waehrung frei gehandelt und
marktgestellt ist. Feste Bindungen (CFA-Franc an den Euro, irakischer Dinar
an den Dollar) und amtlich gestellte Kurse (Libanon, Syrien, Iran, Venezuela)
bilden kein Landesrisiko ab -- sie zeigen die Ankerwaehrung oder eine
Verwaltungsentscheidung. Die Pruefung dazu steht in D35.

Die Laendercodes folgen FIPS 10-4, weil GDELT dieses Schema verwendet:
Deutschland ist GM (nicht DE), Suedafrika SF, die Ukraine UP.
"""

# code -> (Anzeigename, FX-Symbol, Aktien-Symbol oder None)
LAENDER = {
    # Konflikt- und Schwellenlaender der urspruenglichen Untersuchung
    "IS": ("Israel",       "USDILS=X", "^TA125.TA"),
    "RS": ("Russland",     "USDRUB=X", "IMOEX.ME"),
    "UP": ("Ukraine",      "USDUAH=X", None),
    "NI": ("Nigeria",      "USDNGN=X", None),
    "PK": ("Pakistan",     "USDPKR=X", None),
    "TW": ("Taiwan",       "USDTWD=X", "^TWII"),
    # Erweiterung: grosse Schwellenlaender mit frei gehandelter Waehrung
    "TU": ("Türkei",       "USDTRY=X", "XU100.IS"),
    "BR": ("Brasilien",    "USDBRL=X", "^BVSP"),
    "SF": ("Südafrika",    "USDZAR=X", "^J203.JO"),
    "IN": ("Indien",       "USDINR=X", "^BSESN"),
    "MX": ("Mexiko",       "USDMXN=X", "^MXX"),
    "EG": ("Ägypten",      "USDEGP=X", "^CASE30"),
    # Referenzlaender: Waehrung entfaellt, Marktvolatilitaet traegt
    "US": ("USA",          None,       "^GSPC"),
    "GM": ("Deutschland",  None,       "^GDAXI"),
}

GPR_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
GDELT_MASTER = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"

# CAMEO-Rootcodes der Eskalationsleiter
ESKALATION = {14: "Protest", 15: "Machtdemonstration", 16: "Beziehungsabbruch",
              17: "Zwang", 18: "Angriff", 19: "Kampf", 20: "Massengewalt"}

VOL_FENSTER = 21          # Handelstage fuer Volatilitaet und Abwertung
NORM_FENSTER = 120        # Handelstage fuer den Normalzustand (z-Wert)
PROGNOSE_HORIZONT = 5     # Handelstage
PROGNOSE_SCHWELLE = 1.0   # z-Wert, ab dem als "erhoeht" gilt
AUFF_BEWEGUNG = 2.5       # Vielfaches der ueblichen Tagesstreuung
AUFF_NIVEAU = 1.5         # z-Wert, ab dem der Status "hoch" lautet
                          # (steuert die Statusanzeige, nicht die Auffaelligkeit)
MAX_BAUSTEIN_ALTER = 30   # Baustein gilt als tot, wenn er so lange nicht mehr fortgeschrieben wurde
MIN_BAUSTEIN_TAGE = 250   # Mindesthistorie, damit ein Baustein verwendet wird
                          # (Yahoo fuehrt manche Symbole ohne Historie)
FFILL_TAGE = 5            # Tage, ueber die ein fehlender Baustein fortgeschrieben wird
                          # (Feiertage, Veroeffentlichungsverzoegerung des GPR)
TAGE_ANZEIGE = 200
NEWS_TAGE = 45
NACHLAUF_TAGE = 4         # GDELT-Tage, die je Lauf nachgeladen werden


# ---------------------------------------------------------------- Steckbrief
# FIPS 10-4 (GDELT) -> ISO 3166-1 alpha-2 (Weltbank). Die beiden Systeme
# stimmen bei den meisten Laendern NICHT ueberein -- Deutschland ist bei
# GDELT "GM", bei der Weltbank "DE"; Russland "RS" gegen "RU". Ohne diese
# Tabelle zieht man Daten des falschen Landes, und zwar lautlos.
ISO2 = {"IS": "IL", "RS": "RU", "UP": "UA", "NI": "NG", "PK": "PK",
        "TW": "TW", "TU": "TR", "BR": "BR", "SF": "ZA", "IN": "IN",
        "MX": "MX", "EG": "EG", "US": "US", "GM": "DE"}

# Kurzeinordnung: worauf die Wirtschaft des Landes ruht und was sie
# verwundbar macht. Bewusst fest hinterlegt und nicht generiert -- eine
# Beschreibung, die sich taeglich aendert, ist keine Einordnung.
UEBERBLICK = {
    "IS": "Hoch entwickelte, technologiegetriebene Volkswirtschaft mit starkem "
          "Export- und Rüstungssektor. Das wirtschaftliche Risiko ist weniger "
          "strukturell als sicherheitspolitisch: regionale Eskalation schlägt "
          "unmittelbar auf Schekel und Kapitalzuflüsse durch.",
    "RS": "Rohstoffexporteur mit starker Abhängigkeit von Öl- und Gaseinnahmen. "
          "Seit 2022 weitgehend vom westlichen Finanzsystem abgeschnitten; "
          "Wechselkurs und Kapitalverkehr werden administrativ gesteuert, "
          "wodurch Marktpreise nur eingeschränkt Risiko abbilden.",
    "UP": "Kriegswirtschaft mit hoher Abhängigkeit von externer Finanzierung. "
          "Agrarexporte und die Verfügbarkeit der Schwarzmeerrouten bestimmen "
          "einen großen Teil der Deviseneinnahmen.",
    "NI": "Größte Volkswirtschaft Afrikas, stark ölabhängig bei gleichzeitig "
          "breiter informeller Wirtschaft. Devisenknappheit und wiederholte "
          "Naira-Abwertungen sind das zentrale Unternehmensrisiko.",
    "PK": "Chronische Zahlungsbilanzprobleme, wiederkehrende IWF-Programme und "
          "hohe Inflation. Politische Instabilität und Sicherheitslage im "
          "Grenzgebiet wirken direkt auf Investitionsklima und Rupie.",
    "TW": "Zentrum der globalen Halbleiterfertigung und damit ein singulärer "
          "Knotenpunkt internationaler Lieferketten. Das dominierende Risiko "
          "ist geopolitisch, nicht wirtschaftlich.",
    "TU": "Große Schwellenvolkswirtschaft mit Industrie- und Tourismusstandbein. "
          "Unorthodoxe Geldpolitik und wiederkehrende Lira-Krisen machen "
          "Währungsrisiko zum bestimmenden Faktor.",
    "BR": "Rohstoff- und Agrarexporteur mit großem Binnenmarkt. Fiskalpolitik "
          "und Zinsniveau treiben die Real-Volatilität; politische Zyklen "
          "schlagen deutlich auf die Kapitalmärkte durch.",
    "SF": "Industrialisierteste Volkswirtschaft Afrikas mit Bergbau als "
          "Exportbasis. Strukturprobleme — Stromversorgung, Arbeitslosigkeit, "
          "Staatsunternehmen — begrenzen das Wachstum dauerhaft.",
    "IN": "Schnell wachsende Volkswirtschaft mit starkem Dienstleistungssektor "
          "und wachsender Fertigung. Energieimportabhängigkeit und "
          "Kapitalflussvolatilität sind die Hauptkanäle externer Schocks.",
    "MX": "Eng mit der US-Wirtschaft verflochten (USMCA); Fertigung und "
          "Nearshoring tragen das Wachstum. Sicherheitslage und "
          "US-Handelspolitik sind die beiden großen Unsicherheitsquellen.",
    "EG": "Bevölkerungsreichstes Land der arabischen Welt, abhängig von "
          "Suezkanal-Einnahmen, Tourismus und Überweisungen. Wiederholte "
          "Abwertungen und hohe Inflation prägen das Unternehmensumfeld.",
    "US": "Größte Volkswirtschaft der Welt und Referenzpunkt für globale "
          "Kapitalmärkte. Risiko wirkt hier weniger als Länderrisiko denn als "
          "Ausstrahlung: US-Zins- und Handelspolitik bewegt alle anderen.",
    "GM": "Exportorientierte Industrievolkswirtschaft mit Schwerpunkt "
          "Automobil, Maschinenbau und Chemie. Verwundbar über Energiepreise, "
          "Lieferketten und die Nachfrage aus China.",
}

# Weltbank-Indikatoren fuer den Steckbrief.
WB_INDIKATOREN = {
    "bevoelkerung": ("SP.POP.TOTL", "Bevölkerung"),
    "flaeche": ("AG.SRF.TOTL.K2", "Fläche"),
    "bip_kopf": ("NY.GDP.PCAP.CD", "BIP pro Kopf"),
    "wachstum": ("NY.GDP.MKTP.KD.ZG", "BIP-Wachstum"),
    "inflation": ("FP.CPI.TOTL.ZG", "Inflation"),
}
WB_URL = "https://api.worldbank.org/v2"
PROFIL_ALTER_TAGE = 30   # Jahresdaten -- oefter abzufragen waere sinnlos
