"""Calcule genou et fin de vie à partir des marts dbt, puis écrit marts.cell_lifetime / rul_backtest."""

from collections import defaultdict
from pathlib import Path

import psycopg

from .eol import backtest, forecast_eol
from .knee import detect_knee

SQL_DIR = Path(__file__).resolve().parents[2] / "sql" / "20_analytics"
KNEE_MIN_POINTS = 30  # en dessous, la détection de cassure n'est pas fiable


def _load(conn):
    traj = defaultdict(lambda: ([], []))
    for cell_id, age, smooth in conn.execute(
        "SELECT cell_id, age_index, capacity_smooth_ah FROM marts.fact_degradation "
        "WHERE is_post_peak ORDER BY cell_id, age_index"
    ):
        traj[cell_id][0].append(age)
        traj[cell_id][1].append(smooth)
    summary = conn.execute(
        "SELECT cell_id, eol_threshold_ah, eol_basis, reached_eol, eol_age_index, last_age_index, "
        "fade_estimate_quality FROM marts.cell_degradation_summary ORDER BY cell_id"
    ).fetchall()
    return traj, summary


def analyze_cell(cell_id, x, y, thr, basis, reached, eol_idx, last_idx, quality):
    """Retourne (ligne cell_lifetime, lignes rul_backtest) pour une cellule."""
    knee = detect_knee(x, y) if len(x) >= KNEE_MIN_POINTS else None
    row = {
        "cell_id": cell_id, "fade_estimate_quality": quality,
        "knee_detected": knee is not None,
        "knee_age_index": knee.x if knee else None,
        "knee_slope_before": knee.slope_before if knee else None,
        "knee_slope_after": knee.slope_after if knee else None,
        "knee_sse_ratio": knee.sse_ratio if knee else None,
        "eol_basis": basis, "eol_threshold_ah": thr,
        "observed_eol_age_index": eol_idx, "predicted_eol_age_index": None,
        "predicted_eol_low": None, "predicted_eol_high": None, "rul_discharges": None,
        "last_age_index": last_idx,
    }
    bt = []
    if thr is None:
        row["forecast_status"] = "no_threshold"
    elif reached:
        row["forecast_status"] = "observed"
        bt = backtest(x, y, eol_idx, thr)
    else:
        fc = forecast_eol(x, y, thr, min_points=10)
        if fc is None:
            row["forecast_status"] = "insufficient_data" if len(x) < 10 else "not_degrading"
        elif quality != "reliable" or fc.eol_x - last_idx > len(x):
            # Ajustement médiocre, ou fin de vie prévue plus loin que la durée déjà observée :
            # le backtest montre déjà ~30 % d'erreur quand l'horizon égale la durée observée.
            row["forecast_status"] = "unreliable_forecast"
        else:
            row.update(
                forecast_status="extrapolated", predicted_eol_age_index=fc.eol_x,
                predicted_eol_low=fc.low, predicted_eol_high=fc.high,
                # prévue avant la dernière mesure sans seuil franchi sur la courbe lissée : imminente
                rul_discharges=max(fc.eol_x - last_idx, 0.0),
            )
    return row, bt


def run(conninfo: str) -> dict[str, int]:
    with psycopg.connect(conninfo) as conn:
        for f in sorted(SQL_DIR.glob("*.sql")):
            conn.execute(f.read_text(encoding="utf-8"))
        traj, summary = _load(conn)

        lifetime, backtests = [], []
        for cell_id, thr, basis, reached, eol_idx, last_idx, quality in summary:
            x, y = traj[cell_id]
            row, bt = analyze_cell(cell_id, x, y, thr, basis, reached, eol_idx, last_idx, quality)
            lifetime.append(row)
            backtests += [(cell_id, b) for b in bt]

        conn.execute("DELETE FROM marts.rul_backtest")
        conn.execute("DELETE FROM marts.cell_lifetime")
        cols = list(lifetime[0])
        conn.cursor().executemany(
            f"INSERT INTO marts.cell_lifetime ({', '.join(cols)}) VALUES ({', '.join('%(' + c + ')s' for c in cols)})",
            lifetime,
        )
        conn.cursor().executemany(
            "INSERT INTO marts.rul_backtest VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [(c, b.fraction, b.cutoff_x, b.predicted, b.actual, b.error, abs(b.error) / b.actual * 100,
              b.low, b.high, b.covered) for c, b in backtests],
        )
    return {"cells": len(lifetime), "knees": sum(r["knee_detected"] for r in lifetime),
            "backtest_rows": len(backtests)}
