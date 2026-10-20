import pytest

from dashboard import charts, theme

T = theme.LIGHT


def soh(n=40, peak=2, nominal=2.0, cap0=1.9, step=0.01):
    pts = [{"age_index": i, "discharge_number": i, "elapsed_days": float(i), "capacity_ah": cap0 - step * i,
            "capacity_smooth_ah": cap0 - step * i, "soh_nominal": 0.0, "soh_smooth_nominal": 0.0, "soh_peak": 0.0,
            "is_post_peak": i >= peak} for i in range(1, n + 1)]
    ref = {"nominal_capacity_ah": nominal, "peak_smooth_ah": cap0 - step * peak, "peak_age_index": peak,
           "temp_c": 24, "peak_current_a": 2}
    return {"cell_id": "B0001", "reference": ref, "points": pts}


def rul(**kw):
    base = {"status": "no_threshold", "eol_threshold_ah": None, "eol_basis": None, "observed_eol_age_index": None,
            "prediction": None, "knee": None}
    return base | kw


def names(fig):
    return [tr.name for tr in fig.data]


# --- couleurs stables ----------------------------------------------------------------------------------

def test_assign_slots_gives_distinct_colors():
    slots = theme.assign_slots(["B0005", "B0006", "B0018"], {})
    assert sorted(slots.values()) == [0, 1, 2]


def test_assign_slots_survivors_keep_their_color_when_one_is_removed():
    before = theme.assign_slots(["B0005", "B0006", "B0018"], {})
    after = theme.assign_slots(["B0006", "B0018"], before)
    assert after == {c: before[c] for c in ("B0006", "B0018")}


def test_assign_slots_reuses_a_freed_slot_without_repainting_others():
    before = theme.assign_slots(["A", "B", "C"], {})
    after = theme.assign_slots(["A", "C", "D"], before)
    assert after["A"] == before["A"] and after["C"] == before["C"] and after["D"] == before["B"]


def test_assign_slots_refuses_more_cells_than_colors():
    with pytest.raises(ValueError, match="plus de 4"):
        theme.assign_slots(["A", "B", "C", "D", "E"], {})


def test_palettes_have_same_slot_count_in_both_modes():
    assert len(theme.LIGHT["series"]) == len(theme.DARK["series"]) == theme.MAX_COMPARED == 4


# --- figure d'une cellule ------------------------------------------------------------------------------

def test_cell_figure_without_threshold_has_only_measurements():
    fig = charts.cell_figure(soh(), rul(), "ah", T)
    assert names(fig) == ["Mesure", "Médiane glissante (5)", "Pic de capacité"]


def test_cell_figure_marks_observed_end_of_life_at_threshold():
    fig = charts.cell_figure(soh(), rul(status="observed", eol_threshold_ah=1.5, eol_basis="nasa_absolute",
                                        observed_eol_age_index=30), "ah", T)
    eol = next(tr for tr in fig.data if tr.name == "Fin de vie observée")
    assert list(eol.x) == [30] and list(eol.y) == [1.5]


def test_cell_figure_draws_dashed_projection_and_interval():
    pred = {"eol_age_index": 60.0, "interval_low": 55.0, "interval_high": 66.0, "rul_discharges": 20.0}
    fig = charts.cell_figure(soh(), rul(status="extrapolated", eol_threshold_ah=1.0, eol_basis="nasa_absolute",
                                        prediction=pred), "ah", T)
    line = next(tr for tr in fig.data if tr.name == "Projection linéaire")
    assert line.line.dash == "dash" and list(line.x) == [40, 60.0]
    point = next(tr for tr in fig.data if tr.name == "Fin de vie prévue")
    assert list(point.error_x.array) == [6.0] and list(point.error_x.arrayminus) == [5.0]


def test_cell_figure_open_ended_interval_has_no_upper_bar():
    pred = {"eol_age_index": 60.0, "interval_low": 55.0, "interval_high": None, "rul_discharges": 20.0}
    fig = charts.cell_figure(soh(), rul(status="extrapolated", eol_threshold_ah=1.0, eol_basis="nasa_absolute",
                                        prediction=pred), "ah", T)
    point = next(tr for tr in fig.data if tr.name == "Fin de vie prévue")
    assert list(point.error_x.array) == [0]


def test_cell_figure_converts_units_consistently():
    s = soh()
    ah = charts.cell_figure(s, rul(), "ah", T)
    pct = charts.cell_figure(s, rul(), "soh_nominal", T)
    assert pct.data[1].y[0] == pytest.approx(ah.data[1].y[0] / 2.0 * 100)
    peak = charts.cell_figure(s, rul(), "soh_peak", T)
    assert max(peak.data[1].y) == pytest.approx(100 * max(ah.data[1].y) / s["reference"]["peak_smooth_ah"])


def test_cell_figure_has_a_single_y_axis():
    fig = charts.cell_figure(soh(), rul(), "ah", T)
    assert not hasattr(fig.layout, "yaxis2") or fig.layout.yaxis2.title.text is None


def test_threshold_follows_the_selected_unit():
    fig = charts.cell_figure(soh(), rul(status="observed", eol_threshold_ah=1.0, eol_basis="relative_to_peak",
                                        observed_eol_age_index=30), "soh_nominal", T)
    assert fig.layout.shapes[0].y0 == pytest.approx(50.0)  # 1,0 Ah sur 2,0 Ah nominal


# --- comparaison ---------------------------------------------------------------------------------------

def test_compare_figure_uses_assigned_colors_and_legend_for_several_series():
    data = {"A": soh(cap0=1.9), "B": soh(cap0=1.7)}
    fig = charts.compare_figure(data, {"A": 0, "B": 2}, "ah", False, T)
    assert [tr.line.color for tr in fig.data] == [T["series"][0], T["series"][2]]
    assert fig.layout.showlegend is True


def test_compare_figure_single_series_has_no_legend():
    fig = charts.compare_figure({"A": soh()}, {"A": 0}, "ah", False, T)
    assert fig.layout.showlegend is False


def test_compare_since_peak_keeps_only_post_peak_points_aligned_on_zero():
    fig = charts.compare_figure({"A": soh(peak=5)}, {"A": 0}, "ah", True, T)
    assert min(fig.data[0].x) == 0 and len(fig.data[0].x) == 36


def test_compare_skips_an_end_label_that_would_cover_another_curve():
    # A finit à 40 sur la courbe de B (qui continue jusqu'à 60 à la même hauteur) : pas d'étiquette pour A
    a = soh(n=40, cap0=1.9, step=0.01)
    b = soh(n=60, cap0=1.9, step=0.0067)  # même valeur autour du rang 40, mais s'étend plus loin
    fig = charts.compare_figure({"A": a, "B": b}, {"A": 0, "B": 1}, "ah", False, T)
    labels = [an.text for an in fig.layout.annotations]
    assert "A" not in labels and "B" in labels


def test_compare_labels_are_not_drawn_on_a_background():
    fig = charts.compare_figure({"A": soh(cap0=1.9), "B": soh(cap0=1.2)}, {"A": 0, "B": 1}, "ah", False, T)
    assert all(an.bgcolor is None for an in fig.layout.annotations)  # un fond masquerait la courbe dessous


def test_compare_marks_only_the_last_point():
    fig = charts.compare_figure({"A": soh()}, {"A": 0}, "ah", False, T)
    sizes = list(fig.data[0].marker.size)
    assert sizes[-1] == 8 and not any(sizes[:-1])


# --- barres et backtest --------------------------------------------------------------------------------

def battery(cell, fade, quality, temp=24):
    return {"cell_id": cell, "fade_pct_per_100_discharges": fade, "fade_estimate_quality": quality,
            "temp_c": temp, "peak_current_a": 2, "discharge_profile": "constant"}


def test_fade_bars_only_color_reliable_fits_unless_weak_requested():
    items = [battery("A", 20.0, "reliable"), battery("B", 5.0, "weak"), battery("C", None, "insufficient")]
    assert names(charts.fade_bar_figure(items, T, include_weak=False)) == ["Ajustement fiable"]
    both = charts.fade_bar_figure(items, T, include_weak=True)
    assert names(both) == ["Ajustement fiable", "Ajustement faible (indicatif)"]
    assert both.data[1].marker.color == T["muted"]


def test_fade_bars_never_show_insufficient_fits():
    items = [battery("C", -712.0, "insufficient")]
    assert len(charts.fade_bar_figure(items, T, include_weak=True).data) == 0


def test_backtest_figure_has_diagonal_and_one_series_per_fraction():
    rows = [{"cell_id": c, "observed_fraction": f, "predicted_eol_age_index": 100.0 + i, "actual_eol_age_index": 110.0,
             "error_discharges": -10.0 + i, "interval_low": 95.0, "interval_high": 105.0 if i else None,
             "interval_covers_actual": False} for i, (c, f) in enumerate([("A", 0.5), ("B", 0.5), ("A", 0.7)])]
    fig = charts.backtest_figure(rows, T)
    assert names(fig) == ["Prévision parfaite", "50% de la vie observée", "70% de la vie observée"]
    first = fig.data[1]
    assert list(first.error_y.array) == [0, 4.0]  # 1re borne haute absente ; 2e : 105 - 101


def test_backtest_axes_fit_the_points_and_not_a_huge_interval():
    rows = [{"cell_id": "A", "observed_fraction": 0.5, "predicted_eol_age_index": 200.0, "actual_eol_age_index": 125.0,
             "error_discharges": 75.0, "interval_low": 180.0, "interval_high": 500.0, "interval_covers_actual": False}]
    fig = charts.backtest_figure(rows, T)
    lo, hi = fig.layout.yaxis.range
    assert lo <= 125.0 and hi >= 200.0  # tous les points sont visibles
    assert hi < 300.0  # la borne d'intervalle à 500 n'écrase pas l'échelle
    assert fig.layout.yaxis.scaleanchor is None  # un repère carré forcé dilatait les axes


def test_cell_figure_line_is_linear_not_spline():
    fig = charts.cell_figure(soh(), rul(), "ah", T)
    assert fig.data[1].line.shape in (None, "linear")
