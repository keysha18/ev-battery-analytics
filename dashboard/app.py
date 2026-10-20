import html
import sys
from pathlib import Path

import httpx
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # permet `from dashboard import ...`

from dashboard import charts, client, theme

STATUS = {
    "observed": ("✔", "Fin de vie observée"),
    "extrapolated": ("◔", "Prévision par extrapolation"),
    "unreliable_forecast": ("⚠", "Prévision refusée (peu fiable)"),
    "not_degrading": ("→", "Pas de dégradation observée"),
    "insufficient_data": ("…", "Données insuffisantes"),
    "no_threshold": ("∅", "Pas de critère de fin de vie"),
}
QUALITY = {"reliable": "fiable", "weak": "faible", "insufficient": "insuffisant"}
PLOT_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}

CSS = """
<style>
.tile {border: 1px solid rgba(128,128,128,.28); border-radius: 8px; padding: 14px 16px; height: 100%;}
.tile-label {font-size: 13px; opacity: .72;}
.tile-value {font-size: 28px; font-weight: 600; line-height: 1.25; margin-top: 2px;}
.tile-note {font-size: 12px; opacity: .65; margin-top: 2px;}
.hero-value {font-size: 56px; font-weight: 600; line-height: 1.05;}
.hero-label {font-size: 14px; opacity: .75; margin-top: 4px;}
</style>
"""


def esc(x) -> str:
    return html.escape(str(x))


def fr(x: float, nd: int = 1) -> str:
    """Nombre à la française : espace insécable pour les milliers, virgule décimale."""
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def tile(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f'<div class="tile"><div class="tile-label">{esc(label)}</div>'
        f'<div class="tile-value">{esc(value)}</div><div class="tile-note">{esc(note)}</div></div>',
        unsafe_allow_html=True,
    )


def status_label(status: str) -> str:
    icon, text = STATUS[status]
    return f"{icon} {text}"


def cell_label(b: dict) -> str:
    return f"{b['cell_id']} · {b['temp_c']} °C · {b['peak_current_a']} A · {b['discharge_profile']}"


st.set_page_config(page_title="EV Battery Analytics", page_icon="🔋", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
t = theme.current(st)

st.title("Dégradation de batteries Li-ion NASA")
st.caption("34 cellules · données du NASA Ames Prognostics Center · tout ce qui suit est lu via l'API, "
           "jamais directement dans la base.")

try:
    items = client.batteries()
    summary = client.fleet_summary()
except httpx.HTTPError as exc:
    st.error(f"API injoignable ({client.API_URL}) : {exc}. Lancer `make api`, puis recharger.")
    st.stop()

by_id = {b["cell_id"]: b for b in items}
ids = list(by_id)
status_n = {x["key"]: x["n"] for x in summary["by_forecast_status"]}
with_threshold = summary["n_batteries"] - status_n.get("no_threshold", 0)

tab_overview, tab_cell, tab_compare, tab_trust = st.tabs(
    ["Vue d'ensemble", "Une cellule", "Comparer", "Fiabilité des prévisions"]
)

# ------------------------------------------------------------------ Vue d'ensemble
with tab_overview:
    hero, *tiles = st.columns([2, 1.2, 1.2, 1.2])
    with hero:
        st.markdown(
            f'<div class="hero-value">{status_n.get("observed", 0)} / {with_threshold}</div>'
            '<div class="hero-label">cellules ont franchi leur seuil de fin de vie</div>',
            unsafe_allow_html=True,
        )
    with tiles[0]:
        tile("Décharges valides", f"{fr(summary['n_valid_discharges'], 0)}",
             f"sur {fr(summary['n_discharges'], 0)} mesurées")
    with tiles[1]:
        refused = status_n.get("unreliable_forecast", 0)
        tile("Prévisions publiées", str(status_n.get("extrapolated", 0)), f"{refused} refusées car peu fiables")
    with tiles[2]:
        bt70 = next((b for b in summary["backtest"] if b["observed_fraction"] == 0.7), None)
        tile("Erreur de prévision", f"{fr(bt70['mean_abs_error_discharges'], 0)} décharges" if bt70 else "n/d",
             "en moyenne, à 70 % de la vie observée" if bt70 else "")
    st.info("Une prévision de fin de vie n'est publiée que si l'ajustement est fiable et si elle reste dans "
            "la durée déjà observée. Le backtest ne porte que sur quelques cellules : lire l'onglet "
            "« Fiabilité des prévisions » avant de s'appuyer sur un chiffre.")

    # Une seule rangée de filtres, au-dessus de ce qu'elle pilote (graphique et tableau)
    st.subheader("Perte de capacité par cellule")
    f1, f2, f3 = st.columns([1, 1, 1.4])
    profile = f1.selectbox("Profil de décharge", ["Tous", "constant", "square_wave", "multi_level"], key="ov_profile")
    temps = ["Toutes"] + sorted({b["temp_c"] for b in items})
    temp = f2.selectbox("Température", temps, key="ov_temp", format_func=lambda v: v if v == "Toutes" else f"{v} °C")
    weak = f3.checkbox("Inclure les ajustements faibles (indicatifs)", key="ov_weak")

    shown = [b for b in items
             if (profile == "Tous" or b["discharge_profile"] == profile) and (temp == "Toutes" or b["temp_c"] == temp)]
    st.caption("Pente de la capacité après son pic. Les cellules à moins de 10 points après le pic n'ont pas de "
               "pente publiée ; les ajustements faibles sont en gris.")
    if any(b["fade_estimate_quality"] == "reliable" or (weak and b["fade_estimate_quality"] == "weak") for b in shown):
        st.plotly_chart(charts.fade_bar_figure(shown, t, weak), width="stretch", config=PLOT_CONFIG)
    else:
        st.info("Aucune cellule avec un ajustement exploitable dans cette sélection.")
    with st.expander("Voir les données"):
        st.dataframe(
            [{"Cellule": b["cell_id"], "Profil": b["discharge_profile"], "T (°C)": b["temp_c"],
              "Courant (A)": b["peak_current_a"], "Décharges valides": b["n_valid_discharges"],
              "Perte (% / 100 décharges)": b["fade_pct_per_100_discharges"],
              "Ajustement": QUALITY[b["fade_estimate_quality"]], "Statut": status_label(b["forecast_status"]),
              "Fin de vie observée (décharge)": b["observed_eol_age_index"]} for b in shown],
            hide_index=True, width="stretch")

# ------------------------------------------------------------------ Une cellule
with tab_cell:
    c1, c2 = st.columns([3, 2])
    cell = c1.selectbox("Cellule", ids, key="cell_pick", format_func=lambda c: cell_label(by_id[c]))
    unit = c2.radio("Unité", list(charts.UNIT_LABELS), key="cell_unit", horizontal=True,
                    format_func=charts.UNIT_LABELS.get)

    detail, series, rul = client.battery(cell), client.soh(cell), client.rul(cell)
    st.markdown(f"**{status_label(rul['status'])}** — {rul['message']}")

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        tile("Pic de capacité", f"{fr(detail['peak_smooth_ah'], 2)} Ah",
             f"{detail['soh_nominal_at_peak']:.0%} du nominal, décharge {detail['peak_age_index']}")
    with k2:
        tile("Capacité actuelle", f"{detail['soh_nominal_at_end']:.0%} du nominal",
             f"après {detail['last_age_index']} décharges")
    with k3:
        fade = detail["fade_pct_per_100_discharges"]
        tile("Perte", f"{fr(fade, 1)} %" if fade is not None else "non publiée",
             f"pour 100 décharges · ajustement {QUALITY[detail['fade_estimate_quality']]}")
    with k4:
        pred = rul["prediction"]
        if rul["observed_eol_age_index"]:
            tile("Fin de vie", f"décharge {rul['observed_eol_age_index']}", "franchissement observé")
        elif pred:
            hi = "∞" if pred["interval_high"] is None else f"{pred['interval_high']:.0f}"
            tile("Fin de vie prévue", f"≈ décharge {pred['eol_age_index']:.0f}",
                 f"intervalle {pred['interval_low']:.0f} à {hi} (trop étroit)")
        else:
            tile("Fin de vie", "non publiée", rul["message"][:60])

    st.plotly_chart(charts.cell_figure(series, rul, unit, t), width="stretch", config=PLOT_CONFIG)
    shaded = " Zone grisée : phase de conditionnement avant le pic." if detail["peak_age_index"] > 2 else ""
    st.caption("Points gris : mesures. Courbe : médiane glissante sur 5 décharges." + shaded +
               " Seules les décharges valides de la condition principale "
               f"({detail['temp_c']} °C, {detail['peak_current_a']} A) sont tracées.")

    with st.expander("Réserves sur ce résultat", expanded=rul["status"] == "extrapolated"):
        for line in rul["caveats"]:
            st.markdown(f"- {line}")
    with st.expander("Voir les données"):
        st.dataframe(series["points"], hide_index=True, width="stretch")

# ------------------------------------------------------------------ Comparer
with tab_compare:
    default = [c for c in ("B0005", "B0006", "B0018") if c in by_id]
    chosen = st.multiselect(f"Cellules ({theme.MAX_COMPARED} au plus)", ids, default=default, key="cmp_cells",
                            max_selections=theme.MAX_COMPARED, format_func=lambda c: cell_label(by_id[c]))
    g1, g2 = st.columns(2)
    since_peak = g1.radio("Axe horizontal", [False, True], key="cmp_x", horizontal=True,
                          format_func=lambda v: "Décharges depuis le pic" if v else "Rang de la décharge")
    cmp_unit = g2.radio("Unité", list(charts.UNIT_LABELS), index=2, key="cmp_unit", horizontal=True,
                        format_func=charts.UNIT_LABELS.get)
    if not chosen:
        st.info("Choisir au moins une cellule.")
    else:
        # Une couleur par cellule, conservée tant qu'elle reste sélectionnée
        slots = theme.assign_slots(chosen, st.session_state.get("cmp_slots", {}))
        st.session_state["cmp_slots"] = slots
        data = {c: client.soh(c) for c in chosen}
        st.plotly_chart(charts.compare_figure(data, slots, cmp_unit, since_peak, t), width="stretch",
                        config=PLOT_CONFIG)
        st.caption("Les cellules n'ont pas toutes les mêmes conditions d'essai (température, courant, tension de "
                   "coupure) : un écart entre deux courbes n'est pas forcément un effet de la température.")
        with st.expander("Voir les données"):
            st.dataframe(
                [{"Cellule": c, "Rang": p["age_index"], "Capacité lissée (Ah)": p["capacity_smooth_ah"],
                  "SOH / nominal": p["soh_smooth_nominal"], "SOH / pic": p["soh_peak"],
                  "Après le pic": p["is_post_peak"]}
                 for c, s in data.items() for p in s["points"]],
                hide_index=True, width="stretch")

# ------------------------------------------------------------------ Fiabilité
with tab_trust:
    rows = client.fleet_backtest()
    st.markdown(
        "On rejoue la prévision comme si l'on n'avait observé qu'une part de la vie de la cellule, puis on compare "
        "à la fin de vie réelle. Seules les cellules ayant atteint leur seuil peuvent servir à ce test."
    )
    covered = sum(r["interval_covers_actual"] for r in rows)
    cells = len({r["cell_id"] for r in rows})
    m1, m2, m3 = st.columns(3)
    with m1:
        tile("Cellules testées", str(cells), "effectif très réduit")
    with m2:
        tile("Intervalles justes", f"{covered} sur {len(rows)}",
             "l'intervalle annoncé contient la vraie fin de vie")
    with m3:
        tile("Erreur relative moyenne", f"{fr(sum(abs(r['error_discharges']) / r['actual_eol_age_index'] for r in rows) / len(rows) * 100, 0)} %",
             "toutes parts de vie confondues")

    st.plotly_chart(charts.backtest_figure(rows, t), width="stretch", config=PLOT_CONFIG)
    st.caption("Sur la diagonale, la prévision est exacte. Au-dessus, la fin de vie est prévue trop tard ; "
               "en dessous, trop tôt. Les barres verticales sont les intervalles annoncés ; une barre qui sort "
               "du cadre est un intervalle très large (valeurs exactes dans le tableau du backtest).")
    st.dataframe(
        [{"Part de vie observée": f"{b['observed_fraction']:.0%}", "Cellules": b["n_cells"],
          "Erreur absolue moyenne (décharges)": round(b["mean_abs_error_discharges"], 1),
          "Erreur relative moyenne (%)": round(b["mean_abs_pct_error"]),
          "Intervalles justes (%)": round(b["interval_coverage"] * 100)} for b in summary["backtest"]],
        hide_index=True, width="stretch")
    for note in summary["notes"]:
        st.markdown(f"- {note}")
    with st.expander("Voir les données du backtest"):
        st.dataframe(rows, hide_index=True, width="stretch")
