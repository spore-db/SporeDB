"""Base connector abstract class for SporeDB external system integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sporedb.connectors.config import ConnectorConfig, SchemaMapping
from sporedb.connectors.result import PullResult
from sporedb.storage.engine import StorageEngine


class BaseConnector(ABC):
    """Abstract base for all SporeDB external system connectors.

    Subclasses implement four methods:
    - connect(): establish connection to external system
    - discover(): list available data sources (tags, measurements, samples)
    - pull(): extract data and persist to SporeDB
    - map_schema(): apply YAML mapping to transform external schema
    """

    def __init__(self, config: ConnectorConfig, engine: StorageEngine) -> None:
        self.config = config
        self.engine = engine
        self._connected = False

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the external system. Raises on failure."""
        ...

    @abstractmethod
    def discover(self) -> list[dict[str, Any]]:
        """List available data sources in the external system.

        Returns list of dicts describing available tags/measurements/samples.
        Used for interactive mapping setup.
        """
        ...

    @abstractmethod
    def pull(
        self,
        batch_name: str,
        mapping: SchemaMapping,
        **kwargs: Any,
    ) -> PullResult:
        """Pull data from external system and persist to SporeDB.

        Args:
            batch_name: Name for the new SporeDB batch.
            mapping: Schema mapping config (from YAML or programmatic).
            **kwargs: Connector-specific parameters (time range, filters, etc.)

        Returns:
            PullResult with import statistics and batch_id.
        """
        ...

    @abstractmethod
    def map_schema(self, mapping: SchemaMapping) -> SchemaMapping:
        """Validate and enrich a schema mapping.

        Checks that source fields exist in the external system,
        applies defaults for unmapped fields, and returns the
        finalized mapping.
        """
        ...

    def close(self) -> None:
        """Close connection. Override if cleanup is needed."""
        self._connected = False

    def __enter__(self) -> BaseConnector:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
