from __future__ import annotations

import copy

BIOPROCESS_VOCABULARY: dict[str, list[str]] = {
    "dissolved_oxygen": [
        "DO",
        "dO2",
        "DO_%",
        "dissolved_oxygen",
        "pO2",
        "DO_sat",
        "DO_pct",
        "dissolved_O2",
    ],
    "ph": [
        "pH",
        "PH",
        "ph_value",
        "pH_value",
    ],
    "temperature": [
        "temp",
        "temperature",
        "T",
        "temp_C",
        "reactor_temp",
        "T_C",
        "temp_K",
        "jacket_temp",
    ],
    "biomass": [
        "OD",
        "OD600",
        "optical_density",
        "cell_density",
        "biomass",
        "DCW",
        "dry_cell_weight",
        "OD_600",
    ],
    "glucose": [
        "glucose",
        "glc",
        "sugar",
        "carbon_source",
        "glucose_g_L",
        "Glc",
        "residual_glucose",
    ],
    "volume": [
        "volume",
        "vol",
        "working_volume",
        "V",
        "reactor_volume",
        "vol_L",
    ],
    "feed_rate": [
        "feed",
        "feed_rate",
        "feed_pump",
        "F_rate",
        "feed_flow",
    ],
    "agitation": [
        "rpm",
        "agitation",
        "stirrer",
        "stir_speed",
        "RPM",
        "stirrer_speed",
    ],
    "airflow": [
        "air",
        "airflow",
        "aeration",
        "vvm",
        "gas_flow",
        "air_flow",
        "sparge",
    ],
    "lactate": [
        "lactate",
        "lac",
        "lactic_acid",
    ],
    "ammonia": [
        "ammonia",
        "NH3",
        "NH4",
        "ammonium",
    ],
    "glutamine": [
        "glutamine",
        "gln",
        "Gln",
    ],
    "glutamate": [
        "glutamate",
        "glu",
        "Glu",
    ],
    "viability": [
        "viability",
        "cell_viability",
        "viab",
        "viable_pct",
    ],
    "product_titer": [
        "titer",
        "product",
        "mAb",
        "product_titer",
        "IgG",
    ],
}


def get_vocabulary(
    custom_vocab: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Return the bioprocess vocabulary, optionally merged with custom entries.

    Custom vocabulary entries are merged: if a key already exists, the custom
    aliases are appended. If a key is new, it is added as-is.
    """
    if custom_vocab is None:
        return copy.deepcopy(BIOPROCESS_VOCABULARY)

    merged = copy.deepcopy(BIOPROCESS_VOCABULARY)
    for key, aliases in custom_vocab.items():
        if key in merged:
            merged[key] = merged[key] + aliases
        else:
            merged[key] = list(aliases)
    return merged
