"""
meldungen_versenden.py -- aus den Lagemeldungen eine versandfertige Meldung bauen.

WARUM DAS EIN EIGENER SCHRITT IST
Der taegliche Lauf erzeugt die Lagemeldungen. Ob eine Meldung VERSANDT werden
soll, ist aber eine andere Frage als ob sie besteht: ein seit sechzig Tagen
laufender Konflikt ist jeden Tag eine gueltige Meldung und nur an einem Tag
eine Nachricht. Ein Warnwerkzeug, das jeden Morgen denselben Zustand meldet,
wird nach einer Woche nicht mehr gelesen -- und ist damit als Warnwerkzeug
kaputt, voellig unabhaengig davon, wie gut es messt.

Deshalb fuehrt dieses Skript ein Gedaechtnis: daten/gemeldet.json haelt fest,
welche Meldung wann und mit welcher Stufe hinausgegangen ist. Versandt wird
nur, was neu ist -- und erneut, wenn sich eine bestehende Lage VERSCHAERFT.
Der Schluessel ist (Land, Meldeart, Anfangsdatum): dieselbe Lage behaelt ihn
ueber Tage hinweg, eine neue Episode bekommt einen neuen.

AUSGABE
  benachrichtigung.json   strukturiert, fuer weitere Verarbeitung
  benachrichtigung.md     Betreffzeile in der ersten Ueberschrift, darunter
                          der Text -- direkt als E-Mail-Rumpf verwendbar
Rueckgabewert 0, wenn etwas zu melden ist, sonst 2. Der Workflow kann daran
entscheiden, ob er ueberhaupt eine Mail schickt, ohne die Datei zu lesen.

Aufruf:  python3 skripte/meldungen_versenden.py [--trocken] [--alles]
         --trocken schreibt nichts ins Gedaechtnis (Probelauf)
         --alles   ignoriert das Gedaechtnis (einmalige Vollmeldung)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
DATEN, DOCS = WURZEL / "daten", WURZEL / "docs"
GEDAECHTNIS = DATEN / "gemeldet.json"

RANG = {"kritisch": 3, "hoch": 2, "beachten": 1}
ZEICHEN = {"kritisch": "!!", "hoch": "!", "beachten": "·"}

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import SEITE_URL
except Exception:                                    # Konfiguration ohne URL
    SEITE_URL = ""


def schluessel(m: dict) -> str:
    return f"{m['code']}|{m['art']}|{m.get('seit') or m['datum']}"


def laden() -> dict:
    pfad = DOCS / "dashboard_data.json"
    if not pfad.exists():
        print("[FEHLER] docs/dashboard_data.json fehlt -- erst aktualisieren.py laufen lassen")
        raise SystemExit(1)
    return json.loads(pfad.read_text())


def auswaehlen(meldungen: list[dict], gedaechtnis: dict, alles: bool
               ) -> tuple[list[dict], list[dict]]:
    """Teilt die Meldungen in neu und verschaerft."""
    neu, schaerfer = [], []
    for m in meldungen:
        k = schluessel(m)
        bekannt = gedaechtnis.get(k)
        if alles or not bekannt:
            neu.append(m)
        elif RANG.get(m["stufe"], 1) > RANG.get(bekannt.get("stufe"), 1):
            schaerfer.append(m | {"vorher": bekannt.get("stufe")})
    return neu, schaerfer


def betreff(stand: str, neu: list[dict], schaerfer: list[dict]) -> str:
    krit = sum(1 for m in neu + schaerfer if m["stufe"] == "kritisch")
    tag = ".".join(reversed(stand.split("-")))
    laender = sorted({m["land"] for m in neu + schaerfer})
    # Neu und verschaerft sind zwei verschiedene Nachrichten. Sie in einer
    # Zahl zusammenzuziehen liest sich falsch: eine Verschaerfung ist keine
    # neue Lage, sondern eine bekannte, die schlimmer geworden ist.
    stuecke = []
    if neu:
        stuecke.append(f"{len(neu)} neue Meldung" + ("en" if len(neu) != 1 else ""))
    if schaerfer:
        stuecke.append(f"{len(schaerfer)} verschärft")
    kopf = f"Länderrisiko {tag}: " + ", ".join(stuecke)
    if krit:
        kopf += f", davon {krit} kritisch"
    # Laender in den Betreff, solange es wenige sind -- eine Betreffzeile, die
    # nur eine Zahl nennt, zwingt zum Oeffnen, um zu erfahren, ob es einen
    # angeht.
    if len(laender) <= 3:
        kopf += " — " + ", ".join(laender)
    else:
        kopf += f" — {len(laender)} Länder"
    return kopf


def block(m: dict, verschaerft: bool = False) -> str:
    z = ZEICHEN.get(m["stufe"], "·")
    kopf = f"{z} **{m['land']} — {m['titel']}**"
    if verschaerft:
        kopf += f"  (verschärft: {m.get('vorher')} → {m['stufe']})"
    else:
        kopf += f"  ({m['stufe']})"
    zeilen = [kopf]
    seit = m.get("seit")
    if seit:
        tage = m.get("tage") or 0
        zeilen.append(f"Seit {'.'.join(reversed(seit.split('-')))}"
                      + (f", {tage} Tage" if tage > 1 else "") + ".")
    zeilen.append(m["text"])
    if SEITE_URL:
        zeilen.append(f"[{m['land']} im Monitor]({SEITE_URL.rstrip('/')}/#/land/{m['code']})")
    return "\n".join(zeilen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--alles", action="store_true")
    a = ap.parse_args()

    d = laden()
    stand = d.get("stand", "")
    meldungen = (d.get("lage") or {}).get("meldungen") or []
    gedaechtnis = json.loads(GEDAECHTNIS.read_text()) if GEDAECHTNIS.exists() else {}

    neu, schaerfer = auswaehlen(meldungen, gedaechtnis, a.alles)
    ordnung = lambda m: (RANG.get(m["stufe"], 1), m.get("seit") or m["datum"])
    neu.sort(key=ordnung, reverse=True)
    schaerfer.sort(key=ordnung, reverse=True)

    if not neu and not schaerfer:
        # Bewusst keine Datei schreiben: der Workflow soll dann gar keine Mail
        # bauen, statt eine leere zu schicken.
        for p in (WURZEL / "benachrichtigung.json", WURZEL / "benachrichtigung.md"):
            if p.exists():
                p.unlink()
        print(f"[OK] Stand {stand}: nichts Neues zu melden "
              f"({len(meldungen)} Meldungen bestehen, alle bereits versandt)")
        return 2

    teile = [f"# {betreff(stand, neu, schaerfer)}", ""]
    if neu:
        teile += ["## Neu", ""] + [block(m) + "\n" for m in neu]
    if schaerfer:
        teile += ["## Verschärft", ""] + [block(m, True) + "\n" for m in schaerfer]

    bestehend = len(meldungen) - len(neu)
    teile += [
        "---", "",
        f"Stand {stand}. {len(meldungen)} Meldungen bestehen insgesamt, "
        f"{bestehend} davon bereits früher versandt.",
        "",
        "Gemeldet wird ein eingetretener Zustand, jeweils mit Anfangsdatum — keine Prognose. "
        "Die Schwellen und die Prüfzahlen zu jeder Größe stehen im Monitor unter "
        "„Rechnungen“.",
    ]
    if SEITE_URL:
        teile += ["", f"[Monitor öffnen]({SEITE_URL})"]

    (WURZEL / "benachrichtigung.md").write_text("\n".join(teile), encoding="utf-8")
    (WURZEL / "benachrichtigung.json").write_text(json.dumps(
        {"stand": stand, "betreff": betreff(stand, neu, schaerfer),
         "neu": neu, "verschaerft": schaerfer,
         "bestehend": bestehend, "gesamt": len(meldungen)},
        ensure_ascii=False, indent=1), encoding="utf-8")

    if not a.trocken:
        for m in neu + schaerfer:
            gedaechtnis[schluessel(m)] = {"stufe": m["stufe"], "gemeldet_am": stand,
                                          "land": m["land"], "titel": m["titel"]}
        # Gedaechtnis begrenzen: die 400 jüngsten Einträge reichen, und die
        # Datei bleibt lesbar.
        if len(gedaechtnis) > 400:
            gedaechtnis = dict(sorted(gedaechtnis.items(),
                                      key=lambda kv: kv[1].get("gemeldet_am", ""),
                                      reverse=True)[:400])
        GEDAECHTNIS.write_text(json.dumps(gedaechtnis, ensure_ascii=False, indent=1),
                               encoding="utf-8")

    print(f"[OK] {betreff(stand, neu, schaerfer)}")
    for m in neu:
        print(f"   neu        {m['land']}: {m['titel']} (seit {m.get('seit')})")
    for m in schaerfer:
        print(f"   verschärft {m['land']}: {m['titel']} ({m.get('vorher')} → {m['stufe']})")
    if a.trocken:
        print("   [trocken] Gedächtnis unverändert")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
