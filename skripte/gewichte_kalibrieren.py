"""
gewichte_kalibrieren.py -- die Indexgewichte an extern datierten Krisen prüfen.

DIE FRAGE
Wie viel soll die Ereignislage im Index zählen, wie viel Währungsdruck,
Marktvolatilität, globales Umfeld? Geraten wäre beliebig, und "geopolitisch
höher gewichten" ist beim globalen GPR-Baustein wirkungslos, weil er zwischen
Ländern nicht trennt. Also braucht die Gewichtung einen Maßstab von AUSSEN.

DER MASSSTAB
daten/ankerereignisse.json enthält extern datierte Landeskrisen -- Zeitfenster,
die aus Nachrichtenchronologie stammen und NICHT aus den Daten abgeleitet sind,
die sie prüfen sollen. Gefragt wird: trennt der Index Ankertage von den übrigen
Tagen DESSELBEN Landes? Gemessen als ROC-AUC je Land, gemittelt über Länder
(nicht über Tage -- sonst dominieren Länder mit vielen Ankertagen).

Das ist dasselbe Prüfmuster wie die Ankervalidierung der zugrunde liegenden
Arbeit (D18), hier nur zur Kalibrierung statt zur Bestätigung.

WARUM DREI PRÜFUNGEN UND NICHT NUR DAS BESTE ERGEBNIS
Vier Gewichte auf zwanzig Ankerepisoden zu optimieren ist eine Einladung zum
Überanpassen. Deshalb:

  Gitter        Gewichte nur in 0,05-Schritten, jedes zwischen 0,05 und 0,60.
                Ein gröberes Raster kann weniger überanpassen als eine feine
                Optimierung -- und die Gewichte bleiben nennbar.
  Auslassung    Leave-one-country-out: kalibriert auf allen Ländern außer
                einem, gemessen auf dem ausgelassenen. Nur wenn das hält, ist
                die Gewichtung übertragbar und nicht an diese Länder angepasst.
  Placebo       Dieselbe Rechnung mit zeitlich verschobenen Ankerfenstern. Ein
                Ergebnis, das auch mit falsch datierten Krisen entsteht, misst
                nicht die Krisen, sondern die Form des Index.

Zusätzlich ausgewiesen: Gleichgewichtung, die alte Dreikomponentenfassung ohne
Ereignislage, und die zehn besten Gewichtsvektoren -- wenn deren Ergebnisse
dicht beieinander liegen, ist die genaue Wahl innerhalb dieser Gruppe
gleichgültig, und das ist eine ehrlichere Aussage als eine Stelle hinter dem
Komma.

Aufruf:  python3 skripte/gewichte_kalibrieren.py [--schreiben] [--placebo 200]
         Ohne --schreiben wird nur berichtet, daten/gewichte.json bleibt unberührt.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

WURZEL = Path(__file__).resolve().parent.parent
DATEN = WURZEL / "daten"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from index_gewichte import (BAUSTEINE, GEWICHTE_VORGABE, KLAUSEL_ANTEIL,
                            ereignislage, zusammensetzen)

# Die schweren Abhaengigkeiten (Konfiguration, Tageslauf) werden erst in
# panel() geladen. Damit laesst sich die Bewertungsmechanik dieses Skripts
# einzeln pruefen, ohne einen vollstaendigen Datenbestand zu brauchen -- und
# ein Fehler in der Konfiguration bricht nicht schon den Import.
NORM_FENSTER = 120

SCHRITT = 0.05
MIN_G, MAX_G = 0.05, 0.60
MIN_ANKERTAGE = 5

# Die Eskalationsklausel wird MITKALIBRIERT, nicht gesetzt. Grund steht im
# Bericht: je stärker die Klausel greift, desto weniger hängt das Ergebnis
# überhaupt von den Gewichten ab -- bei Anteil 1,0 ist der Index der größte
# Baustein und die Gewichte sind wirkungslos. Beides zusammen zu bestimmen ist
# deshalb keine Feinheit, sondern notwendig, damit die Aussage "diese Gewichte
# sind kalibriert" überhaupt einen Inhalt hat.
KLAUSEL_GITTER = [0.0, 0.4, 0.5, 0.6, 0.7, 0.8]


def log(m): print(m, flush=True)


def panel() -> dict[str, pd.DataFrame]:
    """Baut je Land die Bausteinreihe -- ueber DIESELBE Funktion wie der Tageslauf.

    Hier stand einmal ein Nachbau der Schritte aus aktualisieren.main(). Er
    lief still auseinander: die Tagesgueltigkeit (unvollstaendige Erntetage)
    und die gemeinsame Normierung der Bausteine fehlten ihm, er haette also
    Gewichte fuer einen Index bestimmt, den es im Betrieb nicht mehr gibt.
    """
    global NORM_FENSTER
    from config import LAENDER, NORM_FENSTER as NF
    import aktualisieren as A
    NORM_FENSTER = NF
    gpr = pd.read_excel(DATEN / "gpr.xls")[["date", "GPRD"]].rename(columns={"GPRD": "gpr"})
    gpr["date"] = pd.to_datetime(gpr.date)
    gpr["geopolitik"] = (gpr.gpr - gpr.gpr.mean()) / gpr.gpr.std()
    gpr = gpr[["date", "geopolitik"]]
    gd = pd.read_csv(DATEN / "gdelt_tagesaggregate.csv", sep=";", parse_dates=["date"])

    aus = {}
    for code in LAENDER:
        d, _g, _q = A.bausteinreihe(code, gpr, gd)
        if d is None:
            continue
        aus[code] = d[["date"] + [b for b in BAUSTEINE if b in d.columns]]
    return aus


def anker_laden() -> tuple[list[dict], bool]:
    pfad = DATEN / "ankerereignisse.json"
    if not pfad.exists():
        log("[FEHLER] daten/ankerereignisse.json fehlt.")
        raise SystemExit(1)
    alle = json.loads(pfad.read_text())["anker"]
    geprueft = [a for a in alle if a.get("geprueft")]
    if geprueft:
        return geprueft, True
    log(f"[WARN] Kein Anker ist als geprüft markiert. Es wird mit allen {len(alle)} "
        f"gerechnet -- das Ergebnis ist bis zur Prüfung der Datierungen vorläufig.")
    return alle, False


def label(d: pd.DataFrame, anker: list[dict], code: str,
          verschiebung: int = 0) -> np.ndarray:
    y = np.zeros(len(d), dtype=bool)
    for a in anker:
        if a["land"] != code:
            continue
        von = pd.Timestamp(a["von"]) + pd.Timedelta(days=verschiebung)
        bis = pd.Timestamp(a["bis"]) + pd.Timedelta(days=verschiebung)
        y |= ((d.date >= von) & (d.date <= bis)).to_numpy()
    return y


def guete(P: dict[str, pd.DataFrame], anker: list[dict], gewichte: dict,
          laender: list[str] | None = None, verschiebung: int = 0,
          klausel: float = KLAUSEL_ANTEIL) -> tuple[float | None, dict]:
    """Mittlere Trennschärfe über die Länder mit Ankertagen."""
    je_land = {}
    for code, d in P.items():
        if laender is not None and code not in laender:
            continue
        y = label(d, anker, code, verschiebung)
        if y.sum() < MIN_ANKERTAGE or (~y).sum() < 30:
            continue
        roh = zusammensetzen(d, gewichte, klausel)
        mu = roh.rolling(NORM_FENSTER, min_periods=60).mean()
        sd = roh.rolling(NORM_FENSTER, min_periods=60).std(ddof=0)
        z = ((roh - mu) / sd.replace(0, np.nan)).to_numpy()
        gilt = np.isfinite(z)
        if y[gilt].sum() < MIN_ANKERTAGE or len(np.unique(y[gilt])) < 2:
            continue
        je_land[code] = float(roc_auc_score(y[gilt], z[gilt]))
    if not je_land:
        return None, {}
    return float(np.mean(list(je_land.values()))), je_land


def gitter() -> list[dict]:
    stufen = [round(x * SCHRITT, 2) for x in range(int(MIN_G / SCHRITT), int(MAX_G / SCHRITT) + 1)]
    aus = []
    for kombi in itertools.product(stufen, repeat=len(BAUSTEINE)):
        if abs(sum(kombi) - 1.0) > 1e-9:
            continue
        aus.append(dict(zip(BAUSTEINE, kombi)))
    return aus


def kurz(g: dict) -> str:
    return " ".join(f"{b[:4]}={g[b]:.2f}" for b in BAUSTEINE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schreiben", action="store_true")
    ap.add_argument("--placebo", type=int, default=200)
    a = ap.parse_args()

    log("[1/5] Bausteinreihen aufbauen ...")
    P = panel()
    anker, sind_geprueft = anker_laden()
    mit_ankern = sorted({x["land"] for x in anker} & set(P))
    log(f"      {len(P)} Länder, {len(anker)} Anker in {len(mit_ankern)} davon: {', '.join(mit_ankern)}")
    ohne_ereignis = [c for c in P if "ereignis" not in P[c].columns or not np.isfinite(P[c].ereignis).any()]
    if ohne_ereignis:
        log(f"      [INFO] ohne Ereignislage (zu kurze GDELT-Historie): {', '.join(sorted(ohne_ereignis))}")

    log("[2/5] Vergleichsmaßstäbe ...")
    alt3 = {"waehrung": 1/3, "markt": 1/3, "geopolitik": 1/3, "ereignis": 0.0}
    for name, g, kl in (("alte Fassung, 3 Bausteine, Mittelwert", alt3, 0.0),
                        ("Gleichgewichtung, 4 Bausteine", {b: 0.25 for b in BAUSTEINE}, KLAUSEL_ANTEIL),
                        ("Vorgabe", GEWICHTE_VORGABE, KLAUSEL_ANTEIL)):
        auc, _ = guete(P, anker, g, klausel=kl)
        log(f"      {name:42s} AUC {auc if auc is None else round(auc, 3)}   [{kurz(g)}]")

    log("[3/5] Gitter durchrechnen: Gewichte und Eskalationsklausel gemeinsam ...")
    G = gitter()
    ergebnis, je_klausel = [], {}
    for kl in KLAUSEL_GITTER:
        auswertung = []
        for g in G:
            auc, je = guete(P, anker, g, klausel=kl)
            if auc is not None:
                auswertung.append((auc, g, je, kl))
        if not auswertung:
            continue
        auswertung.sort(key=lambda x: -x[0])
        je_klausel[kl] = {"best": auswertung[0][0], "schlechtest": auswertung[-1][0],
                          "gewichte": auswertung[0][1]}
        ergebnis += auswertung
    ergebnis.sort(key=lambda x: -x[0])

    log("      Wie stark hängt das Ergebnis überhaupt von den Gewichten ab?")
    for kl, v in je_klausel.items():
        sp = v["best"] - v["schlechtest"]
        log(f"        Klausel {kl:.1f}: bester {v['best']:.3f}, schlechtester "
            f"{v['schlechtest']:.3f}, Spanne {sp:.3f}"
            + ("   — Gewichte praktisch wirkungslos" if sp < 0.01 else ""))

    log("      Die zehn besten Kombinationen:")
    for auc, g, _, kl in ergebnis[:10]:
        log(f"        AUC {auc:.3f}   {kurz(g)}  Klausel {kl:.1f}")
    beste, beste_klausel = ergebnis[0][1], ergebnis[0][3]
    spanne = ergebnis[0][0] - ergebnis[min(9, len(ergebnis) - 1)][0]
    log(f"      Spanne zwischen Platz 1 und 10: {spanne:.3f}"
        + ("  — innerhalb dieser Gruppe ist die genaue Wahl gleichgültig" if spanne < 0.02 else ""))

    log("[4/5] Auslassungsprüfung (leave-one-country-out) ...")
    loco = []
    for code in mit_ankern:
        rest = [c for c in P if c != code]
        _, best_rest, best_kl = max(
            ((guete(P, anker, g, laender=rest, klausel=kl)[0] or 0, g, kl)
             for kl in KLAUSEL_GITTER for g in G), key=lambda x: x[0])
        auc, _ = guete(P, anker, best_rest, laender=[code], klausel=best_kl)
        if auc is not None:
            loco.append((code, auc, best_rest, best_kl))
            log(f"      {code}: AUC {auc:.3f} mit außerhalb kalibrierten Gewichten "
                f"[{kurz(best_rest)} Klausel {best_kl:.1f}]")
    loco_mittel = float(np.mean([x[1] for x in loco])) if loco else None
    log(f"      Mittel über ausgelassene Länder: "
        f"{'—' if loco_mittel is None else round(loco_mittel, 3)}")

    log(f"[5/5] Placebo: {a.placebo} zufällig verschobene Ankersätze ...")
    rng = np.random.default_rng(20260910)
    pl = []
    for _ in range(a.placebo):
        v = int(rng.integers(90, 600)) * int(rng.choice([-1, 1]))
        auc, _ = guete(P, anker, beste, verschiebung=v, klausel=beste_klausel)
        if auc is not None:
            pl.append(auc)
    if pl:
        anteil = float(np.mean([x >= ergebnis[0][0] for x in pl]))
        log(f"      Placebo-AUC: Mittel {np.mean(pl):.3f}, 95. Perzentil "
            f"{np.percentile(pl, 95):.3f} | echtes Ergebnis {ergebnis[0][0]:.3f}")
        log(f"      Anteil der Placebos, die das echte Ergebnis erreichen: {anteil:.3f}"
            + ("  — bestanden" if anteil < 0.05 else "  — NICHT bestanden, die Gewichtung"
               " misst nicht die Krisen"))
    else:
        anteil = None

    bericht = {
        "stand": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "gewichte": beste,
        "klausel_anteil": beste_klausel,
        "klausel_vorgabe": KLAUSEL_ANTEIL,
        "gewichtswirkung": {str(k): round(v["best"] - v["schlechtest"], 4)
                            for k, v in je_klausel.items()},
        "auc_kalibriert": round(ergebnis[0][0], 4),
        "auc_je_land": {k: round(v, 3) for k, v in ergebnis[0][2].items()},
        "auc_gleichgewicht": round(guete(P, anker, {b: 0.25 for b in BAUSTEINE})[0] or 0, 4),
        "auc_alte_fassung": round(guete(P, anker, alt3, klausel=0.0)[0] or 0, 4),
        "loco_mittel": None if loco_mittel is None else round(loco_mittel, 4),
        "placebo_anteil": anteil,
        "spanne_top10": round(spanne, 4),
        "anker_geprueft": sind_geprueft,
        "anker_anzahl": len(anker),
        "top10": [{"auc": round(x[0], 4), "gewichte": x[1], "klausel": x[3]}
                  for x in ergebnis[:10]],
    }
    (DATEN / "gewichte_bericht.json").write_text(
        json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")

    if a.schreiben:
        if anteil is not None and anteil >= 0.05:
            log("\n[ABBRUCH] Placebo nicht bestanden -- daten/gewichte.json bleibt unverändert. "
                "Eine Gewichtung, die auch mit falsch datierten Krisen entsteht, gehört nicht "
                "in den Betrieb.")
            return 1
        (DATEN / "gewichte.json").write_text(
            json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"\n[OK] daten/gewichte.json geschrieben: {kurz(beste)}")
    else:
        log(f"\n[OK] Nur Bericht geschrieben (daten/gewichte_bericht.json). "
            f"Zum Übernehmen mit --schreiben starten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
