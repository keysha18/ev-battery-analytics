import numpy as np
import pytest

from src.analytics.eol import backtest, forecast_eol
from src.analytics.knee import detect_knee
from src.analytics.run import analyze_cell


def curve(n=100, knee_at=None, before=-0.002, after=-0.010, start=2.0, noise=0.0, seed=0):
    x = np.arange(1, n + 1, dtype=float)
    y = start + before * (x - 1)
    if knee_at is not None:
        y = y + (after - before) * np.maximum(0, x - knee_at)
    return x, y + np.random.default_rng(seed).normal(0, noise, n)


# --- genou ---------------------------------------------------------------------------------------

def test_knee_found_at_known_position():
    x, y = curve(knee_at=60, noise=0.003)
    k = detect_knee(x, y)
    assert k is not None
    assert abs(k.x - 60) <= 5
    assert k.slope_after < k.slope_before < 0
    assert k.slope_after / k.slope_before == pytest.approx(5, rel=0.3)


def test_no_knee_on_straight_line():
    x, y = curve(noise=0.003)
    assert detect_knee(x, y) is None


def test_no_knee_when_loss_slows_down():
    # perte rapide puis lente : cassure, mais pas un genou (la perte ne s'accélère pas)
    x, y = curve(knee_at=50, before=-0.010, after=-0.002, noise=0.002)
    assert detect_knee(x, y) is None


def test_no_knee_on_too_short_curve():
    x, y = curve(n=10, knee_at=5)
    assert detect_knee(x, y) is None


# --- prévision de fin de vie ----------------------------------------------------------------------

def test_forecast_recovers_known_crossing():
    x, y = curve(n=80, before=-0.005, noise=0.0)  # 2.0 - 0.005*(x-1)
    fc = forecast_eol(x, y, threshold=1.4)
    assert fc.eol_x == pytest.approx(121.0)  # 2.0 - 0.005*(x-1) = 1.4  ->  x = 121
    assert fc.low <= fc.eol_x <= fc.high or fc.high is None


def test_forecast_returns_none_when_not_degrading():
    x = np.arange(1, 30, dtype=float)
    assert forecast_eol(x, np.full_like(x, 1.8) + 0.001 * x, threshold=1.4) is None


def test_forecast_returns_none_with_too_few_points():
    assert forecast_eol([1, 2, 3], [2.0, 1.9, 1.8], threshold=1.4) is None


def test_forecast_interval_is_wider_with_noise():
    x, clean = curve(n=60, before=-0.005)
    _, noisy = curve(n=60, before=-0.005, noise=0.03)
    a = forecast_eol(x, clean + 1e-9 * np.sin(x), 1.4)
    b = forecast_eol(x, noisy, 1.4)
    assert (b.high - b.low) > (a.high - a.low)


def test_backtest_accurate_on_linear_curve():
    x, y = curve(n=130, before=-0.005)
    rows = backtest(x, y, actual_eol_x=121.0, threshold=1.4)
    assert [r.fraction for r in rows] == [0.5, 0.7, 0.9]
    assert all(abs(r.error) < 1 for r in rows)


def test_backtest_shows_bias_when_loss_accelerates():
    # courbe qui s'accélère : une extrapolation linéaire sur le début voit une fin de vie trop lointaine
    x, y = curve(n=140, knee_at=60, before=-0.002, after=-0.012)
    actual = float(x[np.argmax(y <= 1.4)])
    rows = backtest(x, y, actual_eol_x=actual, threshold=1.4)
    early = next(r for r in rows if r.fraction == 0.5)
    assert early.error > 10  # prévu bien après le réel
    assert not early.covered


# --- assemblage par cellule -------------------------------------------------------------------------

def test_analyze_cell_without_threshold():
    x, y = curve(n=40)
    row, bt = analyze_cell("B0001", x, y, None, None, False, None, 40, "reliable")
    assert row["forecast_status"] == "no_threshold" and bt == []


def test_analyze_cell_observed_eol_is_backtested():
    x, y = curve(n=130, before=-0.005)
    row, bt = analyze_cell("B0002", x, y, 1.4, "nasa_absolute", True, 121, 130, "reliable")
    assert row["forecast_status"] == "observed" and row["observed_eol_age_index"] == 121
    assert len(bt) == 3


def test_analyze_cell_extrapolates_when_eol_not_reached():
    x, y = curve(n=70, before=-0.005)  # fin de vie à 121, soit 51 décharges après la dernière mesure
    row, _ = analyze_cell("B0003", x, y, 1.4, "nasa_absolute", False, None, 70, "reliable")
    assert row["forecast_status"] == "extrapolated"
    assert row["predicted_eol_age_index"] == pytest.approx(121.0, abs=1)
    assert row["rul_discharges"] == pytest.approx(51.0, abs=1)


def test_analyze_cell_refuses_forecast_when_fit_is_weak():
    x, y = curve(n=70, before=-0.005)
    row, _ = analyze_cell("B0005", x, y, 1.4, "nasa_absolute", False, None, 70, "weak")
    assert row["forecast_status"] == "unreliable_forecast"
    assert row["predicted_eol_age_index"] is None and row["rul_discharges"] is None


def test_analyze_cell_refuses_forecast_beyond_observed_window():
    # 30 points seulement mais fin de vie prévue ~90 décharges plus loin : plus long que ce qu'on a observé
    x, y = curve(n=30, before=-0.005)
    row, _ = analyze_cell("B0006", x, y, 1.4, "nasa_absolute", False, None, 30, "reliable")
    assert row["forecast_status"] == "unreliable_forecast"
    assert row["rul_discharges"] is None


def test_analyze_cell_clips_negative_rul_to_zero():
    # la droite franchit le seuil avant la dernière mesure alors que la courbe lissée ne l'a pas fait
    x, y = curve(n=60, before=-0.005)
    row, _ = analyze_cell("B0007", x, y, 1.8, "nasa_absolute", False, None, 60, "reliable")
    assert row["forecast_status"] == "extrapolated"
    assert row["predicted_eol_age_index"] < 60
    assert row["rul_discharges"] == 0.0


def test_analyze_cell_flags_non_degrading():
    x = np.arange(1, 40, dtype=float)
    row, _ = analyze_cell("B0004", x, 1.8 + 0.001 * x, 1.4, "nasa_absolute", False, None, 39, "weak")
    assert row["forecast_status"] == "not_degrading"
