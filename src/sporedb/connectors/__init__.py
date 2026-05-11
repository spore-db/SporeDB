"""SporeDB external system connectors.

Provides a plugin-style connector architecture for pulling data from
external systems (InfluxDB, OSIsoft PI, LabVantage LIMS, SciNote ELN)
into SporeDB batches.

Connector implementations are conditionally imported so that
``from sporedb.connectors import BaseConnector`` works even without
optional connector dependencies installed.
"""

import contextlib

from sporedb.connectors.base import BaseConnector
from sporedb.connectors.config import (
    ConnectorConfig,
    FieldMapping,
    SchemaMapping,
    load_config,
    load_mapping,
)
from sporedb.connectors.result import PullResult

# Conditionally import concrete connector implementations.
# These require optional dependencies (influxdb-client, pi-web-sdk, etc.)
# so we wrap in try/except to allow the base connector infrastructure
# to be used without installing all deps.

with contextlib.suppress(ImportError):
    from sporedb.connectors.influxdb import InfluxDBConnector

with contextlib.suppress(ImportError):
    from sporedb.connectors.osisoft_pi import OSIsoftPIConnector

with contextlib.suppress(ImportError):
    from sporedb.connectors.labvantage import LabVantageLIMSConnector

with contextlib.suppress(ImportError):
    from sporedb.connectors.scinote import SciNoteELNConnector

# Registry of connector type strings to classes.
# Only populated for connectors whose dependencies are installed.
CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {}

if "InfluxDBConnector" in dir():
    CONNECTOR_REGISTRY["influxdb"] = InfluxDBConnector
if "OSIsoftPIConnector" in dir():
    CONNECTOR_REGISTRY["osisoft_pi"] = OSIsoftPIConnector
if "LabVantageLIMSConnector" in dir():
    CONNECTOR_REGISTRY["labvantage"] = LabVantageLIMSConnector
if "SciNoteELNConnector" in dir():
    CONNECTOR_REGISTRY["scinote"] = SciNoteELNConnector

__all__ = [
    "BaseConnector",
    "CONNECTOR_REGISTRY",
    "ConnectorConfig",
    "FieldMapping",
    "LabVantageLIMSConnector",
    "OSIsoftPIConnector",
    "InfluxDBConnector",
    "PullResult",
    "SchemaMapping",
    "SciNoteELNConnector",
    "load_config",
    "load_mapping",
]
