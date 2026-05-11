from __future__ import annotations

import pytest


@pytest.fixture
def sample_csv_headers() -> list[str]:
    return ["time_h", "pH", "DO_%", "temp_C", "OD600", "glucose_g_L", "my_custom_col"]


@pytest.fixture
def sample_data_rows() -> list[list[str]]:
    return [
        ["0.0", "7.2", "95.3", "37.0", "0.15", "20.0", "abc"],
        ["0.5", "7.1", "88.7", "36.9", "0.25", "18.5", "def"],
        ["1.0", "6.9", "82.1", "37.1", "0.40", "16.2", "ghi"],
    ]
