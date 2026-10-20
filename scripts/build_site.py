"""Génère docs/index.html : page de présentation statique, instantané des résultats servis par l'API.

Usage (API démarrée, `make api`) :  make site
Les graphiques réutilisent dashboard/charts.py avec les deux thèmes ; ils sont embarqués en JSON et
dessinés par Plotly.js dans le navigateur. Aucun serveur n'est nécessaire pour consulter la page.
"""

import html
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from plotly.offline import get_plotlyjs_version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard import charts, theme

API = os.environ.get("API_URL", "http://localhost:8000")
OUT = ROOT / "docs" / "index.html"
REPO = "https://github.com/keysha18/ev-battery-analytics"
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]


def esc(x) -> str:
    return html.escape(str(x))


def fr(x: float, nd: int = 0) -> str:
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def both_themes(build) -> str:
    """JSON {light, dark} d'une figure. '</' est échappé pour ne jamais fermer la balise <script>."""
    light, dark = build(theme.LIGHT).to_json(), build(theme.DARK).to_json()
    return ('{"light":' + light + ',"dark":' + dark + "}").replace("</", "<\\/")


def table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th scope='col'>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<div class='tablewrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def chart_block(cid: str, title: str, intro: str, fig_json: str, label: str, data_table: str, extra: str = "") -> str:
    return f"""
<section class="chart" aria-labelledby="h-{cid}">
  <h3 id="h-{cid}">{esc(title)}</h3>
  <p>{intro}</p>
  <div class="plot" data-chart="fig-{cid}" role="img" aria-label="{esc(label)}"></div>
  <script type="application/json" id="fig-{cid}">{fig_json}</script>
  {extra}
  <details><summary>Voir les données</summary>{data_table}</details>
</section>"""


def main() -> None:
    with httpx.Client(base_url=API, timeout=15) as c:
        def get(path):
            r = c.get(path)
            r.raise_for_status()
            return r.json()

        summary = get("/fleet/summary")
        backtest = get("/fleet/backtest")
        soh = {k: get(f"/batteries/{k}/soh") for k in ("B0005", "B0043", "B0006", "B0018")}
        rul = {k: get(f"/batteries/{k}/rul") for k in ("B0005", "B0043")}

    status = {x["key"]: x["n"] for x in summary["by_forecast_status"]}
    with_thr = summary["n_batteries"] - status.get("no_threshold", 0)
    bt = {b["observed_fraction"]: b for b in summary["backtest"]}
    covered = sum(r["interval_covers_actual"] for r in backtest)
    today = date.today()
    stamp = f"{today.day} {MONTHS[today.month - 1]} {today.year}"

    # ---- graphiques
    r5, r43 = rul["B0005"], rul["B0043"]
    knee = r5["knee"]
    pred = r43["prediction"]
    fig_cell = both_themes(lambda t: charts.cell_figure(soh["B0005"], r5, "ah", t))
    fig_forecast = both_themes(lambda t: charts.cell_figure(soh["B0043"], r43, "ah", t))
    slots = {"B0005": 0, "B0006": 1, "B0018": 2}
    cmp_series = {k: soh[k] for k in slots}
    fig_compare = both_themes(lambda t: charts.compare_figure(cmp_series, slots, "soh_peak", False, t))
    fig_backtest = both_themes(lambda t: charts.backtest_figure(backtest, t))

    def soh_rows(cell):
        return [[p["age_index"], round(p["capacity_ah"], 3), round(p["capacity_smooth_ah"], 3)]
                for p in soh[cell]["points"]]

    blocks = [
        chart_block(
            "cell", "Une cellule observée jusqu'à la fin de vie (B0005)",
            f"La capacité mesurée (points gris) et sa médiane glissante (bleu) baissent jusqu'à franchir le seuil de "
            f"fin de vie de la NASA (trait horizontal, {fr(r5['eol_threshold_ah'], 1)} Ah) à la <strong>décharge "
            f"{r5['observed_eol_age_index']}</strong> (point noir)."
            + (f" Le losange orange marque un genou détecté à la décharge {fr(knee['age_index'])} : la perte "
               "s'y accélère." if knee else ""),
            fig_cell, "Capacité de la cellule B0005 en fonction du rang de décharge, avec le seuil de fin de vie",
            table(["Rang de décharge", "Capacité mesurée (Ah)", "Médiane glissante (Ah)"], soh_rows("B0005"))),
        chart_block(
            "forecast", "Une prévision, et ses réserves (B0043)",
            f"Pour cette cellule la fin de vie n'est pas encore atteinte : la tendance est prolongée (pointillés) "
            f"jusqu'au seuil (trait horizontal) et donne une fin de vie vers la "
            f"<strong>décharge {fr(pred['eol_age_index'])}</strong>, intervalle "
            f"{fr(pred['interval_low'])} à {fr(pred['interval_high'])}. Cet intervalle est <strong>trop étroit</strong> : "
            "il ne reflète que l'incertitude sur la pente. C'est pourquoi l'API ne livre jamais ce chiffre sans ses réserves.",
            fig_forecast, "Capacité de la cellule B0043 avec projection linéaire jusqu'au seuil de fin de vie",
            table(["Rang de décharge", "Capacité mesurée (Ah)", "Médiane glissante (Ah)"], soh_rows("B0043")),
            extra="<ul class='caveats'>" + "".join(f"<li>{esc(x)}</li>" for x in r43["caveats"]) + "</ul>"),
        chart_block(
            "compare", "Trois cellules, mêmes conditions d'essai",
            "B0005, B0006 et B0018 (24 °C, 2 A) perdent leur capacité à des rythmes différents. L'axe vertical est "
            "la capacité rapportée à son pic.",
            fig_compare, "Capacité relative au pic de B0005, B0006 et B0018 en fonction du rang de décharge",
            table(["Cellule", "Rang de décharge", "Capacité lissée (Ah)", "SOH / pic"],
                  [[k, p["age_index"], round(p["capacity_smooth_ah"], 3), round(p["soh_peak"], 3)]
                   for k in slots for p in soh[k]["points"]])),
        chart_block(
            "backtest", "Quelle confiance accorder aux prévisions ?",
            f"On rejoue la prévision comme si l'on n'avait observé qu'une part de la vie, puis on la compare à la vraie "
            f"fin de vie : <strong>{covered} intervalles sur {len(backtest)}</strong> contiennent la vérité, sur seulement "
            f"<strong>{len({r['cell_id'] for r in backtest})} cellules</strong>. Au-dessus de la diagonale, la fin de vie "
            "est prévue trop tard ; en dessous, trop tôt.",
            fig_backtest, "Fin de vie prévue contre fin de vie réelle, pour trois parts de vie observée",
            table(["Cellule", "Part observée", "Prévu", "Réel", "Écart (décharges)", "Intervalle contient le réel"],
                  [[r["cell_id"], f"{r['observed_fraction']:.0%}", round(r["predicted_eol_age_index"]),
                    round(r["actual_eol_age_index"]), f"{r['error_discharges']:+.0f}",
                    "oui" if r["interval_covers_actual"] else "non"] for r in backtest])),
    ]

    tiles = [
        (fr(summary["n_batteries"]), "cellules étudiées", "fichiers MATLAB bruts de la NASA"),
        (fr(summary["n_valid_discharges"]), "décharges valides", f"sur {fr(summary['n_discharges'])} mesurées"),
        (str(status.get("extrapolated", 0)), "prévisions publiées",
         f"{status.get('unreliable_forecast', 0)} refusées car peu fiables"),
        (f"{fr(bt[0.7]['mean_abs_error_discharges'])} décharges", "d'erreur moyenne",
         "à 70 % de la vie observée (backtest)"),
    ]
    tiles_html = "".join(
        f"<div class='tile'><div class='tile-v'>{esc(v)}</div><div class='tile-l'>{esc(label)}</div>"
        f"<div class='tile-n'>{esc(n)}</div></div>" for v, label, n in tiles)

    page = TEMPLATE
    for key, value in {
        "PLOTLY_VERSION": get_plotlyjs_version(), "REPO": REPO, "STAMP": stamp,
        "HERO_N": str(status.get("observed", 0)), "HERO_D": str(with_thr), "TILES": tiles_html,
        "BLOCKS": "\n".join(blocks),
    }.items():
        page = page.replace(f"@@{key}@@", value)
    # Pas d'espaces en fin de ligne : le hook pre-commit les retirerait du fichier généré à chaque commit
    page = "\n".join(line.rstrip() for line in page.splitlines()) + "\n"
    OUT.write_text(page, encoding="utf-8")
    (OUT.parent / ".nojekyll").touch()
    print(f"{OUT.relative_to(ROOT)} écrit ({OUT.stat().st_size // 1024} Ko)")


TEMPLATE = (Path(__file__).with_name("site_template.html")).read_text(encoding="utf-8")

if __name__ == "__main__":
    main()
