"""Jetons de couleur du dashboard. Valeurs issues de la palette de référence de la méthode dataviz ;
les 4 premiers slots catégoriels ont été validés (scripts/validate_palette.js) en clair et en sombre."""

LIGHT = {
    "mode": "light",
    "surface": "#fcfcfb", "text": "#0b0b0b", "text2": "#52514e", "muted": "#898781",
    "grid": "#e1e0d9", "axis": "#c3c2b7",
    "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
}
DARK = {
    "mode": "dark",
    "surface": "#1a1a19", "text": "#f0efec", "text2": "#c3c2b7", "muted": "#898781",
    "grid": "#2c2c2a", "axis": "#383835",
    "series": ["#3987e5", "#d95926", "#199e70", "#c98500"],
}

MAX_COMPARED = len(LIGHT["series"])


def current(streamlit_module=None) -> dict:
    """Thème du navigateur (clair par défaut si Streamlit ne le dit pas)."""
    try:
        kind = streamlit_module.context.theme.type
    except Exception:  # noqa: BLE001 - API absente ou hors session : on retombe sur le clair
        kind = None
    return DARK if kind == "dark" else LIGHT


def assign_slots(selected: list[str], existing: dict[str, int], n_slots: int = MAX_COMPARED) -> dict[str, int]:
    """Une couleur par cellule, stable : désélectionner une cellule ne repeint pas les autres.

    Une cellule garde son slot tant qu'elle reste sélectionnée ; un slot libéré est réutilisé
    par la prochaine cellule ajoutée, jamais plus de n_slots à la fois.
    """
    kept = {c: s for c, s in existing.items() if c in selected}
    free = [s for s in range(n_slots) if s not in kept.values()]
    for cell in selected:
        if cell not in kept:
            if not free:
                raise ValueError(f"plus de {n_slots} cellules : couleur indisponible pour {cell}")
            kept[cell] = free.pop(0)
    return kept
