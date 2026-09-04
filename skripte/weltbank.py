"""Steckbriefdaten von der Weltbank -- Kennzahlen mit Jahresangabe.

Warum die Weltbank und nicht fest hinterlegte Zahlen: Bevoelkerung, BIP pro
Kopf, Wachstum und Inflation aendern sich, und eine Zahl ohne Quelle und
Jahr ist im Zweifel eine Behauptung. Der Preis dafuer ist eine weitere
externe Abhaengigkeit im taeglichen Lauf -- deshalb drei Vorkehrungen:

1. Abgefragt wird hoechstens alle PROFIL_ALTER_TAGE Tage. Es sind
   Jahresdaten; taeglich zu fragen waere sinnlos und unhoeflich.
2. Faellt die API aus, bleibt die letzte gespeicherte Fassung stehen. Ein
   Ausfall der Weltbank darf den Risikomonitor nicht anhalten.
3. Jede Zahl traegt ihr Berichtsjahr. Die Weltbank liefert je nach Land
   unterschiedlich aktuelle Staende -- ohne Jahr steht auf der Seite eine
   Zahl, deren Alter niemand kennt.

Zu Taiwan: Taiwan ist kein Mitglied der Weltbank und kommt in ihrer
Datenbank nicht vor. Statt die Luecke zu kaschieren, wird sie ausgewiesen.
Eigene Zahlen aus anderer Quelle einzusetzen und sie neben Weltbankzahlen
zu stellen, waere die schlechtere Loesung: dann stuenden auf derselben
Seite Werte unterschiedlicher Erhebungsmethodik, ohne dass man es sieht.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import ISO2, LAENDER, PROFIL_ALTER_TAGE, WB_INDIKATOREN, WB_URL

WURZEL = Path(__file__).resolve().parent.parent
PFAD = WURZEL / "daten" / "laender_profil.json"


def log(m): print(m, flush=True)


def _holen(url: str):
    from aktualisieren import holen
    roh = holen(url, versuche=3, timeout=60)
    if roh is None:
        return None
    try:
        d = json.loads(roh)
    except Exception:
        return None
    # v2 liefert [meta, daten]; bei Fehlern stattdessen {"message": [...]}
    if not isinstance(d, list) or len(d) < 2 or not isinstance(d[1], list):
        return None
    return d[1]


def profil(erzwingen: bool = False) -> dict:
    """Liest das gespeicherte Profil und frischt es bei Bedarf auf."""
    alt = json.loads(PFAD.read_text()) if PFAD.exists() else {}
    stand = alt.get("_stand")
    if stand and not erzwingen:
        alter = (dt.date.today() - dt.date.fromisoformat(stand)).days
        if alter < PROFIL_ALTER_TAGE:
            log(f"      Steckbrief aktuell ({alter} Tage alt) -- keine Abfrage")
            return alt

    codes = ";".join(sorted({ISO2[c] for c in LAENDER if c in ISO2}))
    neu = {c: dict(alt.get(c, {})) for c in LAENDER}
    fehlend = []
    for schluessel, (ind, _) in WB_INDIKATOREN.items():
        # mrnev=1: je Land der juengste Wert, der nicht leer ist.
        zeilen = _holen(f"{WB_URL}/country/{codes}/indicator/{ind}"
                        f"?format=json&per_page=1000&mrnev=1")
        if zeilen is None:
            fehlend.append(ind)
            continue
        nach_iso = {}
        for z in zeilen:
            iso = (z.get("country") or {}).get("id")
            if iso and z.get("value") is not None:
                nach_iso[iso] = (z["value"], z.get("date"))
        for code in LAENDER:
            iso = ISO2.get(code)
            if iso in nach_iso:
                wert, jahr = nach_iso[iso]
                neu[code][schluessel] = {"wert": float(wert), "jahr": jahr}
        log(f"      {ind}: {len(nach_iso)} von {len(LAENDER)} Ländern")

    if fehlend:
        log(f"      [WARN] nicht abrufbar: {', '.join(fehlend)} "
            f"-- vorhandene Werte bleiben stehen")
        if len(fehlend) == len(WB_INDIKATOREN) and alt:
            return alt   # Totalausfall: alten Stand behalten, Datum nicht setzen

    neu["_stand"] = dt.date.today().isoformat()
    neu["_quelle"] = "Weltbank, World Development Indicators"
    PFAD.write_text(json.dumps(neu, ensure_ascii=False, indent=1))
    ohne = [c for c in LAENDER if not any(k in neu.get(c, {}) for k in WB_INDIKATOREN)]
    if ohne:
        log(f"      [INFO] ohne Weltbankdaten: {', '.join(ohne)} "
            f"(nicht in der Datenbank enthalten)")
    return neu


if __name__ == "__main__":
    p = profil(erzwingen="--erzwingen" in sys.argv)
    for code, (name, _, _) in LAENDER.items():
        d = p.get(code, {})
        teile = [f"{k}={d[k]['wert']:,.1f} ({d[k]['jahr']})"
                 for k in WB_INDIKATOREN if k in d]
        print(f"{name:<12} {' | '.join(teile) if teile else '— keine Daten'}")
