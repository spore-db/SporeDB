from __future__ import annotations

from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from sporedb.ingestion.column_mapper import detect_columns, match_column
from sporedb.ingestion.result import ColumnMapping, ImportResult
from sporedb.ingestion.vocabulary import BIOPROCESS_VOCABULARY, get_vocabulary


class TestColumnMappingModel:
    """Test ColumnMapping Pydantic model fields."""

    def test_column_mapping_fields(self):
        cm = ColumnMapping(
            timestamp_col="time_h",
            variable_mappings={"pH": "ph"},
            unit_mappings={"temp_C": "C"},
            unmapped_cols=["custom"],
            confidence={"pH": 1.0},
        )
        assert cm.timestamp_col == "time_h"
        assert cm.variable_mappings == {"pH": "ph"}
        assert cm.unit_mappings == {"temp_C": "C"}
        assert cm.unmapped_cols == ["custom"]
        assert cm.confidence == {"pH": 1.0}

    def test_column_mapping_defaults(self):
        cm = ColumnMapping(timestamp_col="time")
        assert cm.variable_mappings == {}
        assert cm.unit_mappings == {}
        assert cm.unmapped_cols == []
        assert cm.confidence == {}


class TestImportResultModel:
    """Test ImportResult Pydantic model fields."""

    def test_import_result_fields(self):
        ir = ImportResult(
            batch_id=UUID("00000000-0000-0000-0000-000000000001"),
            rows_imported=100,
            columns_mapped={"pH": "ph"},
            units_converted={"temp": ("K", "C")},
            warnings=["Some warning"],
            elapsed_seconds=1.5,
        )
        assert ir.rows_imported == 100
        assert ir.warnings == ["Some warning"]
        assert ir.elapsed_seconds == 1.5

    def test_import_result_defaults(self):
        ir = ImportResult(
            batch_id=UUID("00000000-0000-0000-0000-000000000001"),
            rows_imported=0,
            elapsed_seconds=0.0,
        )
        assert ir.columns_mapped == {}
        assert ir.units_converted == {}
        assert ir.warnings == []


class TestBioprocessVocabulary:
    """Test vocabulary has required entries."""

    def test_vocabulary_has_at_least_50_entries(self):
        total = sum(len(aliases) for aliases in BIOPROCESS_VOCABULARY.values())
        assert total >= 50, f"Expected 50+ entries, got {total}"

    def test_vocabulary_categories(self):
        expected = {
            "dissolved_oxygen",
            "ph",
            "temperature",
            "biomass",
            "glucose",
            "volume",
            "feed_rate",
            "agitation",
            "airflow",
            "lactate",
            "ammonia",
            "glutamine",
            "glutamate",
            "viability",
            "product_titer",
        }
        assert expected.issubset(set(BIOPROCESS_VOCABULARY.keys()))

    def test_get_vocabulary_without_custom(self):
        vocab = get_vocabulary()
        assert vocab == BIOPROCESS_VOCABULARY

    def test_get_vocabulary_with_custom(self):
        custom = {"my_variable": ["myvar", "mv"]}
        vocab = get_vocabulary(custom)
        assert "my_variable" in vocab
        assert "myvar" in vocab["my_variable"]
        # original unchanged
        assert "my_variable" not in BIOPROCESS_VOCABULARY

    def test_custom_vocab_extends_existing(self):
        custom = {"ph": ["pH_extra_alias"]}
        vocab = get_vocabulary(custom)
        assert "pH_extra_alias" in vocab["ph"]
        assert "pH" in vocab["ph"]  # original still there


class TestColumnMatching:
    """Test exact and fuzzy matching."""

    def test_exact_match_ph(self):
        vocab = get_vocabulary()
        name, confidence = match_column("pH", vocab)
        assert name == "ph"
        assert confidence == 1.0

    def test_exact_match_dissolved_oxygen(self):
        vocab = get_vocabulary()
        name, confidence = match_column("dissolved_oxygen", vocab)
        assert name == "dissolved_oxygen"
        assert confidence == 1.0

    def test_fuzzy_match_do2(self):
        vocab = get_vocabulary()
        name, confidence = match_column("dO2", vocab)
        assert name == "dissolved_oxygen"
        assert confidence >= 0.7

    def test_fuzzy_match_temp_c(self):
        vocab = get_vocabulary()
        name, confidence = match_column("temp_C", vocab)
        assert name == "temperature"
        assert confidence >= 0.7

    def test_unknown_column(self):
        vocab = get_vocabulary()
        name, confidence = match_column("my_custom_col", vocab)
        assert name is None
        assert confidence == 0.0

    def test_whitespace_stripping(self):
        vocab = get_vocabulary()
        name, confidence = match_column("  pH  ", vocab)
        assert name == "ph"
        assert confidence == 1.0


class TestDetectColumns:
    """Test full pipeline column detection."""

    def test_detect_columns_basic(self, sample_csv_headers, sample_data_rows):
        cm = detect_columns(sample_csv_headers, sample_data_rows)
        assert isinstance(cm, ColumnMapping)
        assert cm.timestamp_col == "time_h"
        assert "pH" in cm.variable_mappings
        assert cm.variable_mappings["pH"] == "ph"
        assert "my_custom_col" in cm.unmapped_cols

    def test_detect_columns_custom_vocab(self, sample_csv_headers, sample_data_rows):
        custom = {"my_custom": ["my_custom_col"]}
        cm = detect_columns(
            sample_csv_headers,
            sample_data_rows,
            custom_vocab=custom,
        )
        assert "my_custom_col" not in cm.unmapped_cols
        assert cm.variable_mappings.get("my_custom_col") == "my_custom"


class TestColumnMatchingHypothesis:
    """Property-based tests for column matching."""

    @given(st.text(min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_match_column_never_crashes(self, col_name: str):
        vocab = get_vocabulary()
        result = match_column(col_name, vocab)
        assert isinstance(result, tuple)
        assert len(result) == 2
        name, confidence = result
        assert name is None or isinstance(name, str)
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0
