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
AUFF_NIVEAU = 1.5         # z-Wert
TAGE_ANZEIGE = 200
NEWS_TAGE = 45
NACHLAUF_TAGE = 4         # GDELT-Tage, die je Lauf nachgeladen werden
