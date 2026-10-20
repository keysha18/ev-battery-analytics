"""Détection du "genou" d'une courbe de capacité : le point où la perte s'accélère."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Knee:
    x: float  # position du genou (indice d'âge)
    slope_before: float
    slope_after: float
    sse_ratio: float  # SSE(hinge) / SSE(droite) : plus c'est bas, plus la cassure est nette


def _sse_line(x: np.ndarray, y: np.ndarray) -> float:
    a = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    r = y - a @ coef
    return float(r @ r)


def detect_knee(
    x, y, min_segment: int = 8, min_slope_ratio: float = 1.5, max_sse_ratio: float = 0.8
) -> Knee | None:
    """Régression "hinge" continue y = a + b*x + c*max(0, x - xk), avec xk balayé sur toute la courbe.

    Un genou est retenu si la pente après xk est négative et au moins `min_slope_ratio` fois plus
    raide qu'avant, et si le modèle à cassure réduit l'erreur d'au moins 1 - max_sse_ratio par rapport
    à une droite. Le balayage choisit le meilleur xk parmi beaucoup de candidats : le gain d'erreur est
    donc optimiste, d'où des seuils volontairement exigeants.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    if n < 2 * min_segment + 1:
        return None
    sse_line = _sse_line(x, y)
    if sse_line < 1e-12:  # déjà parfaitement linéaire
        return None

    best = None
    for k in range(min_segment, n - min_segment):
        a = np.column_stack([np.ones(n), x, np.maximum(0.0, x - x[k])])
        coef, *_ = np.linalg.lstsq(a, y, rcond=None)
        r = y - a @ coef
        sse = float(r @ r)
        if best is None or sse < best[0]:
            best = (sse, float(x[k]), coef)

    sse, xk, (_, b, c) = best
    before, after = float(b), float(b + c)
    ratio = sse / sse_line
    steeper = after < 0 and (before >= 0 or after <= min_slope_ratio * before)
    if ratio <= max_sse_ratio and steeper:
        return Knee(x=xk, slope_before=before, slope_after=after, sse_ratio=ratio)
    return None
