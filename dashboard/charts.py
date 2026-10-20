"""Constructeurs de figures Plotly : des fonctions pures (données de l'API + thème -> figure)."""

import plotly.graph_objects as go

UNITS = {
    "ah": ("Capacité (Ah)", "Ah", 3),
    "soh_nominal": ("SOH vs capacité nominale (%)", "%", 1),
    "soh_peak": ("SOH vs pic de capacité (%)", "%", 1),
}
UNIT_LABELS = {"ah": "Capacité (Ah)", "soh_nominal": "SOH / nominale (%)", "soh_peak": "SOH / pic (%)"}
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def factor(unit: str, ref: dict) -> float:
    return {"ah": 1.0, "soh_nominal": 100 / ref["nominal_capacity_ah"], "soh_peak": 100 / ref["peak_smooth_ah"]}[unit]


def _base(fig: go.Figure, t: dict, height: int, hovermode: str = "x unified") -> go.Figure:
    axis = dict(showgrid=True, gridcolor=t["grid"], gridwidth=1, zeroline=False, linecolor=t["axis"],
                ticks="", tickfont=dict(color=t["muted"], size=12), title_font=dict(color=t["text2"], size=13))
    fig.update_layout(
        height=height, margin=dict(l=8, r=24, t=24, b=8), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, color=t["text2"]), separators=", ",
        hovermode=hovermode, hoverdistance=32,
        hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["axis"], font=dict(color=t["text"], family=FONT)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=t["text2"], size=12)),
        xaxis=dict(**axis, showspikes=hovermode == "x unified", spikemode="across", spikethickness=1,
                   spikecolor=t["axis"], spikedash="solid"),
        yaxis=dict(**axis),
    )
    return fig


def _smooth_at(points: list[dict], age: float) -> float:
    return min(points, key=lambda p: abs(p["age_index"] - age))["capacity_smooth_ah"]


def _note(fig, x, y, text, t, yshift=14, xanchor="center"):
    # Pas de fond : un fond masquerait la portion de courbe qu'il recouvre. C'est au placement
    # d'éviter les données (ou à l'appelant de renoncer à l'étiquette).
    fig.add_annotation(x=x, y=y, text=text, showarrow=False, yshift=yshift, xanchor=xanchor,
                       font=dict(color=t["text2"], size=12, family=FONT))


def cell_figure(soh: dict, rul: dict, unit: str, t: dict) -> go.Figure:
    """Trajectoire d'une cellule : mesures, médiane glissante, pic, seuil de fin de vie, projection."""
    ref, pts = soh["reference"], soh["points"]
    f = factor(unit, ref)
    _, suffix, nd = UNITS[unit]
    s0, s1 = t["series"][0], t["series"][1]
    x = [p["age_index"] for p in pts]
    fmt = f"%{{y:.{nd}f}} {suffix}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=[p["capacity_ah"] * f for p in pts], mode="markers", name="Mesure",
        marker=dict(size=6, color=t["muted"], opacity=0.8), hovertemplate=fmt + "<extra>Mesure</extra>"))
    fig.add_trace(go.Scatter(
        x=x, y=[p["capacity_smooth_ah"] * f for p in pts], mode="lines", name="Médiane glissante (5)",
        line=dict(color=s0, width=2),  # tracé linéaire : un spline inventerait une courbure entre les points
        hovertemplate=fmt + "<extra>Médiane glissante</extra>"))

    peak_x = ref["peak_age_index"]
    fig.add_trace(go.Scatter(
        x=[peak_x], y=[ref["peak_smooth_ah"] * f], mode="markers", name="Pic de capacité",
        marker=dict(size=10, color=s0, line=dict(color=t["surface"], width=2)),
        hovertemplate=fmt + "<extra>Pic de capacité</extra>"))
    if peak_x > 2:
        fig.add_vrect(x0=min(x) - 0.5, x1=peak_x, fillcolor=t["muted"], opacity=0.10, line_width=0, layer="below")
        _note(fig, (min(x) + peak_x) / 2, ref["peak_smooth_ah"] * f, "avant le pic", t, yshift=-26)

    thr = rul.get("eol_threshold_ah")
    last = pts[-1]
    if thr is not None:
        fig.add_hline(y=thr * f, line=dict(color=t["text2"], width=1), layer="below")
        basis = "seuil NASA" if rul["eol_basis"] == "nasa_absolute" else "relatif au pic"
        # À gauche, au-dessus du trait : c'est là que la courbe est la plus haute, donc la zone est libre
        _note(fig, min(x), thr * f, f"Seuil de fin de vie ({basis})", t, yshift=14, xanchor="left")

    if rul.get("observed_eol_age_index"):
        ex = rul["observed_eol_age_index"]
        fig.add_trace(go.Scatter(
            x=[ex], y=[thr * f], mode="markers", name="Fin de vie observée",
            marker=dict(size=11, color=t["text"], line=dict(color=t["surface"], width=2)),
            hovertemplate=f"décharge {ex}<extra>Fin de vie observée</extra>"))
        # Au-dessus à droite : la courbe descend, cet espace est libre (sous le marqueur, elle passerait dessus)
        _note(fig, ex, thr * f, f"fin de vie : décharge {ex}", t, yshift=18, xanchor="left")

    pred = rul.get("prediction")
    if pred:
        px = pred["eol_age_index"]
        fig.add_trace(go.Scatter(
            x=[last["age_index"], px], y=[last["capacity_smooth_ah"] * f, thr * f], mode="lines",
            name="Projection linéaire", line=dict(color=s0, width=2, dash="dash"), hoverinfo="skip"))
        hi = pred["interval_high"]
        fig.add_trace(go.Scatter(
            x=[px], y=[thr * f], mode="markers", name="Fin de vie prévue",
            marker=dict(size=10, symbol="circle-open", color=s0, line=dict(color=s0, width=2)),
            error_x=dict(type="data", symmetric=False, array=[(hi - px) if hi is not None else 0],
                         arrayminus=[px - pred["interval_low"]], color=s0, thickness=2, width=6),
            hovertemplate=f"décharge {px:.0f} (intervalle {pred['interval_low']:.0f} à "
                          f"{'∞' if hi is None else format(hi, '.0f')})<extra>Fin de vie prévue</extra>"))
        _note(fig, px, thr * f, "prévue (intervalle trop étroit)", t, yshift=24)

    knee = rul.get("knee")
    if knee:
        kx = knee["age_index"]
        fig.add_trace(go.Scatter(
            x=[kx], y=[_smooth_at(pts, kx) * f], mode="markers", name="Genou",
            marker=dict(size=11, symbol="diamond", color=s1, line=dict(color=t["surface"], width=2)),
            hovertemplate=f"décharge {kx:.0f}<extra>Genou (perte qui s'accélère)</extra>"))
        _note(fig, kx, _smooth_at(pts, kx) * f, "genou", t, yshift=-20)

    _base(fig, t, 460)
    fig.update_xaxes(title_text="Rang de la décharge (condition principale)")
    fig.update_yaxes(title_text=UNITS[unit][0])
    return fig


def compare_figure(series: dict[str, dict], slots: dict[str, int], unit: str, since_peak: bool, t: dict) -> go.Figure:
    """Courbes lissées de plusieurs cellules (4 au plus). Couleur = cellule, jamais le rang."""
    fig = go.Figure()
    ends = []
    curves: dict[str, tuple[list, list]] = {}
    for cell_id, soh in series.items():
        ref = soh["reference"]
        pts = [p for p in soh["points"] if p["is_post_peak"] or not since_peak]
        if not pts:
            continue
        f = factor(unit, ref)
        _, suffix, nd = UNITS[unit]
        x = [p["age_index"] - (ref["peak_age_index"] if since_peak else 0) for p in pts]
        y = [p["capacity_smooth_ah"] * f for p in pts]
        color = t["series"][slots[cell_id]]
        sizes = [0] * (len(x) - 1) + [8]  # seul le dernier point est marqué
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name=cell_id, line=dict(color=color, width=2),
            marker=dict(size=sizes, color=color, line=dict(color=t["surface"], width=2)),
            hovertemplate=f"%{{y:.{nd}f}} {suffix}<extra>{cell_id}</extra>"))
        ends.append((cell_id, x[-1], y[-1]))
        curves[cell_id] = (x, y)

    if ends:
        all_x = [v for xs, _ in curves.values() for v in xs]
        all_y = [v for _, ys in curves.values() for v in ys]
        span_x = (max(all_x) - min(all_x)) or 1.0
        span_y = (max(all_y) - min(all_y)) or 1.0

        def on_another_curve(cell_id: str, ex: float, ey: float) -> bool:
            """L'étiquette (placée à droite du dernier point) recouvrirait-elle la courbe d'une autre série ?"""
            return any(
                ex <= px <= ex + 0.10 * span_x and abs(py - ey) < 0.04 * span_y
                for other, (ox, oy) in curves.items() if other != cell_id for px, py in zip(ox, oy, strict=True)
            )

        placed = []
        for cell_id, ex, ey in sorted(ends, key=lambda e: e[2]):
            # Étiquette seulement si elle est lisible ; sinon la légende et l'info-bulle identifient la série
            if all(abs(ey - p) > 0.06 * span_y for p in placed) and not on_another_curve(cell_id, ex, ey):
                _note(fig, ex, ey, cell_id, t, yshift=0, xanchor="left")
                fig.layout.annotations[-1].update(xshift=10)
                placed.append(ey)

    _base(fig, t, 440)
    fig.update_layout(showlegend=len(series) >= 2, margin=dict(l=8, r=70, t=24, b=8))
    fig.update_xaxes(title_text="Décharges depuis le pic" if since_peak else "Rang de la décharge")
    fig.update_yaxes(title_text=UNITS[unit][0])
    return fig


def fade_bar_figure(items: list[dict], t: dict, include_weak: bool) -> go.Figure:
    """Perte (% du nominal pour 100 décharges) par cellule. Seuls les ajustements fiables sont en couleur."""
    keep = [b for b in items if b["fade_pct_per_100_discharges"] is not None
            and (b["fade_estimate_quality"] == "reliable" or (include_weak and b["fade_estimate_quality"] == "weak"))]
    keep.sort(key=lambda b: b["fade_pct_per_100_discharges"])
    fig = go.Figure()
    groups = [("reliable", "Ajustement fiable", t["series"][0]), ("weak", "Ajustement faible (indicatif)", t["muted"])]
    for quality, label, color in groups:
        rows = [b for b in keep if b["fade_estimate_quality"] == quality]
        if not rows:
            continue
        fig.add_trace(go.Bar(
            y=[b["cell_id"] for b in rows], x=[b["fade_pct_per_100_discharges"] for b in rows], orientation="h",
            name=label, marker=dict(color=color), text=[f"{b['fade_pct_per_100_discharges']:.1f}" for b in rows],
            textposition="outside", cliponaxis=False, textfont=dict(color=t["text2"], size=11),
            customdata=[[b["temp_c"], b["peak_current_a"], b["discharge_profile"]] for b in rows],
            hovertemplate="<b>%{x:.1f} %</b> pour 100 décharges<br>%{customdata[0]} °C · %{customdata[1]} A "
                          "· %{customdata[2]}<extra>%{y}</extra>"))
    _base(fig, t, max(260, 22 * len(keep) + 90), hovermode="closest")
    fig.update_layout(bargap=0.4, margin=dict(l=8, r=40, t=36, b=8))
    fig.update_xaxes(title_text="Perte (% de la capacité nominale pour 100 décharges)", rangemode="tozero")
    fig.update_yaxes(showgrid=False, type="category", categoryorder="array",
                     categoryarray=[b["cell_id"] for b in keep])
    return fig


def backtest_figure(rows: list[dict], t: dict) -> go.Figure:
    """Fin de vie prévue contre réelle, pour chaque part de vie observée (3 séries au plus)."""
    fig = go.Figure()
    fractions = sorted({r["observed_fraction"] for r in rows})
    # Axes bornés sur les points eux-mêmes : une borne d'intervalle très haute (ex. 500 pour une fin de
    # vie réelle de 150) écraserait tout le reste. La barre sort alors du cadre ; sa valeur est dans le tableau.
    vals = [r[k] for r in rows for k in ("actual_eol_age_index", "predicted_eol_age_index", "interval_low")]
    lo, hi = min(vals) * 0.9, max(vals) * 1.15
    fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="Prévision parfaite",
                             line=dict(color=t["axis"], width=1), hoverinfo="skip"))
    for i, frac in enumerate(fractions):
        part = [r for r in rows if r["observed_fraction"] == frac]
        color = t["series"][i]
        fig.add_trace(go.Scatter(
            x=[r["actual_eol_age_index"] for r in part], y=[r["predicted_eol_age_index"] for r in part],
            mode="markers", name=f"{frac:.0%} de la vie observée",
            marker=dict(size=10, color=color, line=dict(color=t["surface"], width=2)),
            error_y=dict(type="data", symmetric=False, color=color, thickness=1, width=4,
                         array=[(r["interval_high"] - r["predicted_eol_age_index"]) if r["interval_high"] is not None
                                else 0 for r in part],
                         arrayminus=[r["predicted_eol_age_index"] - r["interval_low"] for r in part]),
            customdata=[[r["cell_id"], r["error_discharges"]] for r in part],
            hovertemplate="réel %{x:.0f} · prévu %{y:.0f}<br>écart %{customdata[1]:+.0f} décharges"
                          "<extra>%{customdata[0]}</extra>"))
    _base(fig, t, 460, hovermode="closest")
    fig.update_xaxes(title_text="Fin de vie réelle (rang de la décharge)", range=[lo, hi])
    # Pas de scaleanchor : forcer un repère carré dilatait les axes bien au-delà des données
    fig.update_yaxes(title_text="Fin de vie prévue", range=[lo, hi])
    return fig
