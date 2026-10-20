from datetime import datetime

import pytest

from src.ingest.mat_reader import datevec_to_datetime, discharge_samples, read_cell, summarize_cycle
from tests import synthetic


def test_datevec_to_datetime_keeps_fractional_seconds():
    dt = datevec_to_datetime([2008, 4, 2, 13, 8, 17.921])
    assert dt == datetime(2008, 4, 2, 13, 8, 17, 921000)


def test_discharge_summary():
    r = summarize_cycle(1, synthetic.discharge(capacity=1.8))
    assert r["cycle_type"] == "discharge"
    assert r["capacity_ah"] == pytest.approx(1.8)
    assert r["n_samples"] == 4
    assert r["duration_s"] == pytest.approx(300.0)
    assert (r["v_min"], r["v_max"]) == (pytest.approx(2.7), pytest.approx(4.2))
    assert r["i_median"] == pytest.approx(-2.0)
    assert r["t_mean"] == pytest.approx(25.5)
    assert r["re_ohm"] is None


def test_empty_capacity_becomes_none_not_zero():
    assert summarize_cycle(3, synthetic.discharge(capacity=None))["capacity_ah"] is None


def test_charge_has_no_capacity():
    r = summarize_cycle(0, synthetic.charge())
    assert r["capacity_ah"] is None and r["n_samples"] == 5


def test_impedance_summary():
    r = summarize_cycle(2, synthetic.impedance())
    assert r["cycle_type"] == "impedance"
    assert (r["re_ohm"], r["rct_ohm"]) == (pytest.approx(0.0446), pytest.approx(0.0694))
    assert r["n_samples"] == 3 and r["v_min"] is None


def test_real_re_rct_have_no_imaginary_part():
    r = summarize_cycle(2, synthetic.impedance())
    assert r["re_imag_ohm"] is None and r["rct_imag_ohm"] is None


def test_complex_re_rct_keep_both_parts_without_warning():
    # filterwarnings=error dans pyproject : un ComplexWarning ferait échouer ce test
    r = summarize_cycle(2, synthetic.impedance(complex_re_rct=True))
    assert (r["re_ohm"], r["re_imag_ohm"]) == (pytest.approx(0.0499), pytest.approx(-0.0293))
    assert (r["rct_ohm"], r["rct_imag_ohm"]) == (pytest.approx(0.0499), pytest.approx(0.0293))


def test_unknown_cycle_type_rejected():
    bad = synthetic.charge()
    bad["type"] = "rest"
    with pytest.raises(ValueError, match="type inconnu"):
        summarize_cycle(0, bad)


def test_discharge_samples_rows_and_lengths():
    rows = list(discharge_samples(1, synthetic.discharge()))
    assert len(rows) == 4
    assert rows[0][:2] == (1, 0) and rows[-1][:2] == (1, 3)
    assert len(rows[0]) == 8  # cycle_idx, sample_idx + 6 mesures


def test_discharge_samples_rejects_ragged_series():
    c = synthetic.discharge()
    c["data"]["Voltage_load"] = c["data"]["Voltage_load"][:2]
    with pytest.raises(ValueError, match="longueurs"):
        list(discharge_samples(0, c))


def test_read_cell_roundtrip(tmp_path):
    p = synthetic.write_mat(tmp_path / "B9001.mat", "B9001", synthetic.make_cycles())
    cell_id, cycles = read_cell(p)
    assert cell_id == "B9001"
    assert [c["type"] for c in cycles] == ["charge", "discharge", "impedance", "discharge"]
    assert summarize_cycle(1, cycles[1])["capacity_ah"] == pytest.approx(1.8)
    assert summarize_cycle(3, cycles[3])["capacity_ah"] is None


def test_read_cell_wrong_variable_name(tmp_path):
    p = synthetic.write_mat(tmp_path / "B9002.mat", "B0000", synthetic.make_cycles())
    with pytest.raises(ValueError, match="absente"):
        read_cell(p)
