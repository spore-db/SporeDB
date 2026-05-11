"""SporeDB cloud client -- HTTP-based client for sporedb.cloud.

Provides a ``CloudClient`` class that implements the same method signatures
as the local ``SporeDB`` class, delegating all operations to the cloud
API via HTTP calls.  This allows transparent switching between local and
cloud modes via ``SporeDB(endpoint="https://cloud.sporedb.io", api_key="...")``.

Security:
- T-8-23: API key sent only via Authorization header (never in URL/query params).
- T-8-24: CloudClient only instantiated when explicit endpoint= is provided.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any
from uuid import UUID

import httpx
import pandas as pd

from sporedb.models.batch import (
    Batch,
    BatchLifecycle,
    BatchMetadata,
    CanonicalTimestamps,
)


class CloudClient:
    """HTTP-based SporeDB client for the cloud tier.

    Mirrors the method signatures of :class:`sporedb.client.SporeDB` so that
    switching between local and cloud mode is transparent to callers.

    Parameters
    ----------
    endpoint:
        Base URL of the SporeDB cloud instance (e.g. ``https://cloud.sporedb.io``).
    api_key:
        JWT bearer token for authentication.
    timeout:
        HTTP request timeout in seconds.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        if not self._endpoint.startswith("https://"):
            import warnings

            warnings.warn(
                f"SporeDB cloud endpoint uses insecure HTTP: {self._endpoint}. "
                "API key will be transmitted in plaintext. Use HTTPS in production.",
                UserWarning,
                stacklevel=2,
            )
        self._client = httpx.Client(
            base_url=self._endpoint + "/api/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> CloudClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise an informative error for non-2xx responses."""
        if response.is_success:
            return
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise httpx.HTTPStatusError(
            message=f"HTTP {response.status_code}: {detail}",
            request=response.request,
            response=response,
        )

    def _batch_from_response(self, data: dict[str, Any]) -> Batch:
        """Construct a ``Batch`` model from an API response dict."""
        metadata_dict = data.get("metadata") or {}
        return Batch(
            batch_id=UUID(data["id"]),
            name=data["name"],
            lifecycle=BatchLifecycle(data.get("lifecycle", "planned")),
            timestamps=CanonicalTimestamps(),
            metadata=BatchMetadata(
                strain=metadata_dict.get("strain"),
                media=metadata_dict.get("media"),
                scale_liters=metadata_dict.get("scale_liters"),
                operator=metadata_dict.get("operator"),
            ),
            tags=data.get("tags") or [],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at")
                else datetime.fromisoformat(data["created_at"])
            ),
        )

    # ------------------------------------------------------------------ #
    # Batch CRUD
    # ------------------------------------------------------------------ #

    def create_batch(
        self,
        name: str,
        *,
        strain: str | None = None,
        media: str | None = None,
        scale_liters: float | None = None,
        operator: str | None = None,
        tags: list[str] | None = None,
        inoculation: datetime | None = None,
    ) -> Batch:
        """Create a new batch via the cloud API."""
        metadata: dict[str, Any] = {}
        if strain is not None:
            metadata["strain"] = strain
        if media is not None:
            metadata["media"] = media
        if scale_liters is not None:
            metadata["scale_liters"] = scale_liters
        if operator is not None:
            metadata["operator"] = operator
        if inoculation is not None:
            metadata["inoculation"] = inoculation.isoformat()

        body: dict[str, Any] = {"name": name}
        if metadata:
            body["metadata"] = metadata
        if tags:
            body["tags"] = tags

        response = self._client.post("/batches/", json=body)
        self._raise_for_status(response)
        return self._batch_from_response(response.json())

    def get_batch(self, batch_id: UUID) -> Batch | None:
        """Retrieve a batch by ID, or ``None`` if not found."""
        response = self._client.get(f"/batches/{batch_id}")
        if response.status_code == 404:
            return None
        self._raise_for_status(response)
        return self._batch_from_response(response.json())

    def list_batches(self) -> list[Batch]:
        """Return all batches for the authenticated tenant."""
        response = self._client.get("/batches/")
        self._raise_for_status(response)
        return [self._batch_from_response(b) for b in response.json()]

    def delete_batch(self, batch_id: UUID) -> bool:
        """Delete a batch. Returns ``True`` if it existed."""
        response = self._client.delete(f"/batches/{batch_id}")
        if response.status_code == 404:
            return False
        self._raise_for_status(response)
        return True

    # ------------------------------------------------------------------ #
    # Data retrieval
    # ------------------------------------------------------------------ #

    def get_telemetry(self, batch_id: UUID) -> pd.DataFrame:
        """Return telemetry data for a batch as a pandas DataFrame."""
        response = self._client.get(f"/data/telemetry/{batch_id}")
        self._raise_for_status(response)
        return pd.read_parquet(BytesIO(response.content))

    def get_assay(self, batch_id: UUID) -> pd.DataFrame:
        """Return assay measurements for a batch as a pandas DataFrame."""
        response = self._client.get(f"/data/assay/{batch_id}")
        self._raise_for_status(response)
        return pd.read_parquet(BytesIO(response.content))

    # ------------------------------------------------------------------ #
    # Analytics
    # ------------------------------------------------------------------ #

    def detect_phases(
        self,
        batch_id: UUID,
        signal: str = "OD600",
        min_size: int = 10,
    ) -> list[Any]:
        """Run phase detection via the cloud API."""
        from sporedb.analytics.models import PhaseAnnotation

        response = self._client.post(
            "/analytics/detect-phases",
            json={
                "batch_id": str(batch_id),
                "signal": signal,
                "min_size": min_size,
            },
        )
        self._raise_for_status(response)
        return [PhaseAnnotation.model_validate(item) for item in response.json()]

    def align(
        self,
        batch_ids: list[UUID],
        signal: str = "OD600",
    ) -> pd.DataFrame:
        """Align multiple batch runs via the cloud API."""
        response = self._client.post(
            "/analytics/align",
            json={
                "batch_ids": [str(bid) for bid in batch_ids],
                "signal": signal,
            },
        )
        self._raise_for_status(response)
        return pd.DataFrame(response.json())

    def export(
        self,
        batch_id: UUID,
        format: str = "csv",
    ) -> bytes:
        """Export batch data via the cloud API.

        Args:
            batch_id: Batch to export.
            format: ``"csv"`` or ``"arrow"``.

        Returns:
            Raw bytes of the exported data.
        """
        response = self._client.get(
            f"/data/export/{batch_id}",
            params={"format": format},
        )
        self._raise_for_status(response)
        return response.content

    def compute_metrics(
        self,
        batch_id: UUID,
        signal: str = "OD600",
        min_size: int = 10,
    ) -> list[dict[str, Any]]:
        """Compute batch metrics via the cloud API.

        Returns a list of metric dicts (one per detected phase).
        """
        response = self._client.post(
            "/analytics/metrics",
            json={
                "batch_id": str(batch_id),
                "signal": signal,
                "min_size": min_size,
            },
        )
        self._raise_for_status(response)
        return response.json()["metrics"]  # type: ignore[no-any-return]

    def detect_phases_online(
        self,
        batch_id: UUID,
        signal: str = "OD600",
        *,
        hazard_rate: float = 0.004,
        threshold: float = 0.5,
    ) -> list[Any]:
        """Run BOCPD online phase detection via the cloud API."""
        response = self._client.post(
            "/analytics/detect-phases-online",
            json={
                "batch_id": str(batch_id),
                "signal": signal,
                "hazard_rate": hazard_rate,
                "threshold": threshold,
            },
        )
        self._raise_for_status(response)
        return response.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------ #
    # Query (DSL)
    # ------------------------------------------------------------------ #

    def query(self, dsl_query: str) -> pd.DataFrame:
        """Execute a bioprocess DSL query via the cloud API."""
        response = self._client.post(
            "/query/execute",
            json={"query": dsl_query},
        )
        self._raise_for_status(response)
        data = response.json()
        if isinstance(data, list):
            return pd.DataFrame(data)
        # Handle structured response with columns/rows
        if "columns" in data and "rows" in data:
            return pd.DataFrame(data["rows"], columns=data["columns"])
        return pd.DataFrame(data)
