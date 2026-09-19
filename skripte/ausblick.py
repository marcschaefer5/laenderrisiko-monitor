"""
ausblick.py -- Kurzfristprognose je Zeitreihe, ausdruecklich NACHRANGIG.

WOFUER DIESES MODUL DA IST
Der Monitor ist zuerst ein Warnwerkzeug: er meldet, was gerade eingetreten
ist. Der Ausblick ist die zweite Ebene. Er beantwortet eine engere Frage als
die Bachelorarbeit -- nicht "sagen Nachrichten kuenftige Anspannung voraus",
sondern "wie laeuft eine Reihe fort, wenn man nur ihre eigene Vergangenheit
kennt". Das ist eine Fortschreibung, keine Ereignisvorhersage.

KONSTRUKTION
Jede Reihe wird einzeln fortgeschrieben: ein autoregressives Modell der
Ordnung P auf dem letzten FENSTER, per kleinster Quadrate geschaetzt und
HORIZONT Schritte iteriert. Das Modell hat damit genau die Information, die
in der Reihe selbst steckt -- Niveau, Traegheit, Rueckkehr zum Mittel.

Die GDELT-Variante bekommt zusaetzlich die aktuellen Ereignismerkmale. Genau
das ist die Stelle, an der sich zeigen muss, ob gelesene Nachrichten den
naechsten Tagen etwas hinzufuegen: steigt die Konfliktberichterstattung,
muesste die Fortschreibung frueher anziehen als die reine Eigenhistorie.

WARUM IMMER MIT PRUEFWERT
Zu jeder Prognose wird ein Ruecktest ausgewiesen: derselbe Ablauf, rollend
ueber die juengste Vergangenheit, gemessen als mittlerer absoluter Fehler --
und daneben der Fehler der einfachsten denkbaren Regel, den letzten Wert
einfach beizubehalten. Eine Prognose, die diese Regel nicht schlaegt, ist
keine Leistung. Der Monitor weist das aus, statt es zu verschweigen; das ist
dieselbe Konsequenz, die in der zugrunde liegenden Arbeit gefehlt hat und
dort in der Limitationsdiskussion benannt ist.
"""
from __future__ import annotations

import numpy as np

P = 5              # Ordnung des autoregressiven Modells
FENSTER = 250      # Beobachtungen, auf denen geschaetzt wird
HORIZONT = 5       # Prognoseschritte
PRUEF = 120        # Ursprungspunkte des rollenden Ruecktests
MIN_TAGE = 120     # weniger Historie -> keine Prognose


def _entwurf(y: np.ndarray, p: int, X: np.ndarray | None = None):
    """Baut Designmatrix und Zielvektor fuer ein AR(p)-Modell mit Konstante."""
    n = len(y)
    if n <= p + 10:
        return None, None
    zeilen = [np.ones(n - p)]
    for k in range(1, p + 1):
        zeilen.append(y[p - k:n - k])
    if X is not None:
        for j in range(X.shape[1]):
            zeilen.append(X[p:n, j])
    A = np.column_stack(zeilen)
    return A, y[p:]


def _schaetzen(y: np.ndarray, p: int, X: np.ndarray | None = None):
    A, ziel = _entwurf(y, p, X)
    if A is None:
        return None, None
    gilt = np.isfinite(A).all(axis=1) & np.isfinite(ziel)
    if gilt.sum() < p + 20:
        return None, None
    beta, *_ = np.linalg.lstsq(A[gilt], ziel[gilt], rcond=None)
    rest = ziel[gilt] - A[gilt] @ beta
    return beta, float(np.std(rest, ddof=len(beta)) if len(rest) > len(beta) else np.nan)


def _fortschreiben(y: np.ndarray, beta: np.ndarray, p: int, h: int,
                   x_letzt: np.ndarray | None = None) -> np.ndarray:
    """Iteriert das geschaetzte Modell h Schritte vorwaerts.

    Die Ereignismerkmale werden dabei auf ihrem letzten beobachteten Stand
    festgehalten. Das ist die ehrliche Variante: sie zu extrapolieren hiesse,
    eine Prognose auf eine zweite Prognose zu stuetzen.
    """
    hist = list(y[-p:])
    aus = []
    for _ in range(h):
        teile = [1.0] + [hist[-k] for k in range(1, p + 1)]
        if x_letzt is not None:
            teile += list(x_letzt)
        w = float(np.dot(beta, np.array(teile)))
        aus.append(w)
        hist.append(w)
    return np.array(aus)


def _mae(y: np.ndarray, X: np.ndarray | None, p: int, h: int,
         fenster: int, pruef: int) -> tuple[float | None, float | None]:
    """Rollender Ruecktest: Modellfehler und Fehler der Beibehaltungsregel.

    Bewertet wird der Wert am Ende des Horizonts, also genau die Groesse, die
    im Dashboard steht. Geschaetzt wird ausschliesslich auf Daten vor dem
    Ursprungspunkt -- ein Blick nach vorn waere hier besonders verfuehrerisch
    und besonders wertlos.
    """
    n = len(y)
    start = max(p + 40, n - pruef - h)
    f_modell, f_naiv = [], []
    for t in range(start, n - h + 1):
        y_bis = y[max(0, t - fenster):t]
        ziel = y[t + h - 1]
        if not np.isfinite(ziel) or len(y_bis) < p + 30:
            continue
        Xb = X[max(0, t - fenster):t] if X is not None else None
        beta, _ = _schaetzen(y_bis, p, Xb)
        if beta is None:
            continue
        x_letzt = X[t - 1] if X is not None else None
        if x_letzt is not None and not np.isfinite(x_letzt).all():
            continue
        w = _fortschreiben(y_bis, beta, p, h, x_letzt)[-1]
        if not np.isfinite(w):
            continue
        f_modell.append(abs(w - ziel))
        f_naiv.append(abs(y_bis[-1] - ziel))
    if len(f_modell) < 20:
        return None, None
    return round(float(np.mean(f_modell)), 3), round(float(np.mean(f_naiv)), 3)


def _saeubern(werte) -> np.ndarray:
    y = np.asarray([np.nan if v is None else float(v) for v in werte], dtype=float)
    # Kurze Luecken schliessen; eine Reihe mit Loechern laesst sich sonst nicht
    # autoregressiv schaetzen, und die Loecher stammen aus Feiertagen, nicht
    # aus fehlendem Risiko.
    for i in range(1, len(y)):
        if not np.isfinite(y[i]) and np.isfinite(y[i - 1]):
            y[i] = y[i - 1]
    return y[np.isfinite(y)] if not np.isfinite(y).all() else y


def fortschreibung(werte, merkmale=None, horizont: int = HORIZONT,
                   p: int = P, fenster: int = FENSTER) -> dict | None:
    """Fortschreibung einer Reihe samt Unsicherheitsband und Ruecktest.

    merkmale: optionale Matrix gleichzeitiger Zusatzgroessen (im Monitor die
    GDELT-Ereignismerkmale). Ohne sie ist es die reine Eigenhistorie.
    """
    y = _saeubern(werte)
    if len(y) < MIN_TAGE:
        return None
    X = None
    if merkmale is not None:
        X = np.asarray(merkmale, dtype=float)
        if X.ndim != 2 or len(X) != len(werte):
            return None
        X = X[-len(y):] if len(X) > len(y) else X
        if len(X) != len(y) or not np.isfinite(X[-1]).all():
            return None
        # Spalten ohne durchgehende Belegung fliegen raus, statt die ganze
        # Prognose scheitern zu lassen.
        behalten = [j for j in range(X.shape[1])
                    if np.isfinite(X[-fenster:, j]).mean() > 0.9]
        if not behalten:
            return None
        X = np.nan_to_num(X[:, behalten], nan=0.0)

    y_f = y[-fenster:]
    X_f = X[-fenster:] if X is not None else None
    beta, sigma = _schaetzen(y_f, p, X_f)
    if beta is None or not np.isfinite(sigma):
        return None
    pfad = _fortschreiben(y_f, beta, p, horizont, X[-1] if X is not None else None)
    if not np.isfinite(pfad).all():
        return None

    # Band: der Fehler waechst mit dem Horizont. Naeherung ueber die Wurzel
    # des Schrittes -- exakt waere die Varianz der iterierten AR-Vorhersage,
    # die Naeherung liegt darunter und wird deshalb NICHT als
    # Konfidenzaussage bezeichnet, sondern als Streuungsband.
    band = [[round(float(v - 1.28 * sigma * np.sqrt(i + 1)), 3),
             round(float(v + 1.28 * sigma * np.sqrt(i + 1)), 3)]
            for i, v in enumerate(pfad)]
    mae, mae_naiv = _mae(y, X, p, horizont, fenster, PRUEF)
    return {
        "punkte": [round(float(v), 3) for v in pfad],
        "band": band,
        "horizont": horizont,
        "letzter": round(float(y[-1]), 3),
        "mae": mae,
        "mae_naiv": mae_naiv,
        "besser_als_naiv": (None if mae is None or mae_naiv is None
                            else bool(mae < mae_naiv)),
        "vorsprung": (None if mae is None or mae_naiv is None or not mae_naiv
                      else round((mae_naiv - mae) / mae_naiv, 3)),
    }
