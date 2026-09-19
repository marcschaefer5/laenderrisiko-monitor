# -*- coding: utf-8 -*-
"""Zwei Änderungen an docs/index.html: Rücksprung und der neue Baustein.

1. RÜCKSPRUNG. Der Zurück-Knopf der Länderseite zeigte fest auf die
   Übersicht. Wer von der Karte kam, landete deshalb nicht dort, wo er
   herkam -- und verlor die getroffene Länderauswahl aus dem Blick. Die
   Ansicht merkt sich jetzt, woher sie betreten wurde, und beschriftet den
   Knopf entsprechend.
2. BAUSTEIN EREIGNISLAGE. Neue Kategorie in Diagramm, Tabelle und Legende.
"""
import sys, pathlib
p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs/index.html")
s = p.read_text(encoding="utf-8"); o = len(s)

# ---------------------------------------------------------------- 1. Rücksprung
a = 'const KAT = {waehrung:{n:"Währungsdruck",c:"var(--s1)"},markt:{n:"Marktvolatilität",c:"var(--s2)"},geopolitik:{n:"Geopolitik",c:"var(--s3)"}};'
n = ('const KAT = {ereignis:{n:"Ereignislage",c:"var(--crit)"},'
     'waehrung:{n:"Währungsdruck",c:"var(--s1)"},'
     'markt:{n:"Marktvolatilität",c:"var(--s2)"},'
     'geopolitik:{n:"Geopolitik (global)",c:"var(--s3)"}};\n'
     '\n'
     '// Woher die aktuelle Ansicht betreten wurde. Ohne das führt der\n'
     '// Zurück-Knopf immer auf die Übersicht, auch wenn man von der Karte kam.\n'
     'let HERKUNFT = "#/";\n'
     'const ZURUECK = {"#/":"Alle Länder","#/karte":"Karte","#/historie":"Chronologie",'
     '"#/rechnungen":"Rechnungen"};')
assert a in s, "KAT-Zeile nicht gefunden"
s = s.replace(a, n, 1)

a = '''  vL.innerHTML='<div class="navbar"><button class="back" id="zurueck">‹ Alle Länder</button>'+'''
n = '''  const zurueckZiel = ZURUECK[HERKUNFT] ? HERKUNFT : "#/";
  vL.innerHTML='<div class="navbar"><button class="back" id="zurueck">‹ '+
    (ZURUECK[zurueckZiel]||"Alle Länder")+'</button>'+'''
assert a in s, "Navbar der Länderseite nicht gefunden"
s = s.replace(a, n, 1)

a = '''  document.getElementById("zurueck").onclick=()=>{location.hash="#/";};'''
n = '''  document.getElementById("zurueck").onclick=()=>{location.hash=zurueckZiel;};'''
assert a in s; s = s.replace(a, n, 1)

a = '''function route(){
  const m=location.hash.match(/^#\\/land\\/([A-Z]{2})$/);'''
n = '''function route(){
  const m=location.hash.match(/^#\\/land\\/([A-Z]{2})$/);
  // Die Herkunft wird VOR dem Umschalten festgehalten, und nur wenn die alte
  // Ansicht keine Länderseite war -- sonst würde der Knopf von Land zu Land
  // zeigen statt zurück auf die Liste oder die Karte.
  if(!m && ZURUECK[location.hash||"#/"]) HERKUNFT = location.hash || "#/";'''
assert a in s; s = s.replace(a, n, 1)

# Karte und Chronologie ebenfalls: Rücksprung auf die Übersicht bleibt richtig,
# aber die Länderauswahl soll beim Wechsel erhalten bleiben -- sie liegt im
# localStorage, also genügt der Hashwechsel.

p.write_text(s, encoding="utf-8")
print(f"[OK] {p}: {o} -> {len(s)} Zeichen")
