"""CLI commands for pulling data from external systems into SporeDB.

Provides the ``sporedb pull`` command group with subcommands for each
supported connector: influxdb, pi, labvantage, scinote.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from sporedb.cli._output import console, error_panel
from sporedb.connectors.config import ConnectorConfig, SchemaMapping, load_mapping

# Default mapping directory (shipped with the package)
_MAPPINGS_DIR = Path(__file__).resolve().parent.parent / "connectors" / "mappings"


def _format_pull_result(result: Any) -> None:
    """Display PullResult as a Rich table."""
    from rich.panel import Panel
    from rich.table import Table

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Batch ID", str(result.batch_id))
    table.add_row("Source System", result.source_system)
    table.add_row("Source Identifier", result.source_identifier)
    table.add_row("Rows Imported", str(result.rows_imported))

    mapped = ", ".join(f"{k} -> {v}" for k, v in result.columns_mapped.items())
    table.add_row("Columns Mapped", mapped or "none")

    if result.external_ids:
        ext_ids = ", ".join(f"{k}={v}" for k, v in result.external_ids.items())
        table.add_row("External IDs", ext_ids)

    table.add_row("Elapsed", f"{result.elapsed_seconds:.2f}s")

    console.print(Panel(table, title="[green]Pull Complete[/green]"))

    if result.warnings:
        for w in result.warnings:
            console.print(f"  [yellow]! {w}[/yellow]")


def _load_default_mapping(connector_type: str) -> SchemaMapping:
    """Load the built-in default mapping for a connector type."""
    default_file = _MAPPINGS_DIR / f"{connector_type}_default.yml"
    if not default_file.exists():
        raise click.ClickException(
            f"Default mapping file not found: {default_file}. Provide a --mapping path."
        )
    return load_mapping(default_file)


def _get_engine(ctx: click.Context) -> Any:
    """Extract the StorageEngine from the SporeDB facade.

    Guards against cloud mode which doesn't support direct connector pulls.
    """
    db = ctx.obj["db"]
    if db.is_cloud:
        raise click.ClickException(
            "Pull commands require local mode (not cloud endpoint). "
            "Connector pulls operate directly on the local storage engine."
        )
    return db._engine


def _load_mapping_or_default(
    mapping_path: str | None, connector_type: str
) -> SchemaMapping:
    """Load mapping from file or use built-in default."""
    if mapping_path:
        return load_mapping(Path(mapping_path))
    return _load_default_mapping(connector_type)


# --------------------------------------------------------------------------
# Pull command group
# --------------------------------------------------------------------------


@click.group()
def pull() -> None:
    """Pull data from external systems into SporeDB."""


# --------------------------------------------------------------------------
# InfluxDB subcommand
# --------------------------------------------------------------------------


@pull.command("influxdb")
@click.option(
    "--host", required=True, help="InfluxDB server URL (e.g., http://localhost:8086)"
)
@click.option(
    "--token",
    envvar="SPOREDB_INFLUXDB_TOKEN",
    default=None,
    help="InfluxDB v2 authentication token (or set SPOREDB_INFLUXDB_TOKEN)",
)
@click.option("--username", default=None, help="InfluxDB v1 username")
@click.option(
    "--password",
    envvar="SPOREDB_INFLUXDB_PASSWORD",
    default=None,
    help="InfluxDB v1 password (or set SPOREDB_INFLUXDB_PASSWORD)",
)
@click.option("--org", default="", help="InfluxDB v2 organization")
@click.option("--bucket", default=None, help="InfluxDB v2 bucket name")
@click.option("--database", default=None, help="InfluxDB v1 database name")
@click.option("--measurement", required=True, help="Measurement name to query")
@click.option("--batch-name", required=True, help="Name for the new SporeDB batch")
@click.option(
    "--mapping",
    "mapping_path",
    default=None,
    type=click.Path(exists=True),
    help="Path to YAML mapping file (default: built-in influxdb_default.yml)",
)
@click.option("--start", default="-30d", help="Start time (default: -30d)")
@click.option("--end", default="now()", help="End time (default: now())")
@click.option(
    "--version",
    "influx_version",
    default="auto",
    type=click.Choice(["1", "2", "auto"]),
    help="InfluxDB version (default: auto-detect)",
)
@click.pass_context
def pull_influxdb(
    ctx: click.Context,
    host: str,
    token: str | None,
    username: str | None,
    password: str | None,
    org: str,
    bucket: str | None,
    database: str | None,
    measurement: str,
    batch_name: str,
    mapping_path: str | None,
    start: str,
    end: str,
    influx_version: str,
) -> None:
    """Pull data from InfluxDB into a SporeDB batch."""
    try:
        from sporedb.connectors.influxdb import InfluxDBConnector
    except ImportError:
        console.print(
            error_panel(
                "InfluxDB connector dependencies not installed.\n"
                'Install with: pip install "sporedb[connectors]"'
            )
        )
        return

    engine = _get_engine(ctx)
    mapping = _load_mapping_or_default(mapping_path, "influxdb")

    # Build auth dict
    auth: dict[str, str] = {}
    if token:
        auth["token"] = token
    if username:
        auth["username"] = username
    if password:
        auth["password"] = password
    if org:
        auth["org"] = org

    # Build extra dict
    extra: dict[str, str] = {"version": influx_version}
    if bucket:
        extra["bucket"] = bucket
    if database:
        extra["database"] = database

    config = ConnectorConfig(
        connector_type="influxdb",
        host=host,
        auth=auth,
        extra=extra,
    )

    try:
        connector = InfluxDBConnector(config, engine)
        with connector:
            result = connector.pull(
                batch_name=batch_name,
                mapping=mapping,
                measurement=measurement,
                start=start,
                end=end,
            )
        _format_pull_result(result)
    except Exception as exc:
        console.print(error_panel(f"InfluxDB pull failed: {exc}"))


# --------------------------------------------------------------------------
# OSIsoft PI subcommand
# --------------------------------------------------------------------------


@pull.command("pi")
@click.option("--host", required=True, help="PI Web API base URL")
@click.option("--username", required=True, help="PI Web API username")
@click.option(
    "--password",
    required=True,
    envvar="SPOREDB_PI_PASSWORD",
    help="PI Web API password (or set SPOREDB_PI_PASSWORD)",
)
@click.option("--points", required=True, help="Comma-separated PI point paths")
@click.option("--batch-name", required=True, help="Name for the new SporeDB batch")
@click.option(
    "--mapping",
    "mapping_path",
    default=None,
    type=click.Path(exists=True),
    help="Path to YAML mapping file (default: built-in pi_default.yml)",
)
@click.option(
    "--start", default="*-7d", help="Start time in PI AF syntax (default: *-7d)"
)
@click.option("--end", default="*", help="End time in PI AF syntax (default: *)")
@click.option(
    "--no-ssl-verify",
    is_flag=True,
    default=False,
    help="Disable SSL certificate verification",
)
@click.pass_context
def pull_pi(
    ctx: click.Context,
    host: str,
    username: str,
    password: str,
    points: str,
    batch_name: str,
    mapping_path: str | None,
    start: str,
    end: str,
    no_ssl_verify: bool,
) -> None:
    """Pull data from OSIsoft/AVEVA PI into a SporeDB batch."""
    try:
        from sporedb.connectors.osisoft_pi import OSIsoftPIConnector
    except ImportError:
        console.print(
            error_panel(
                "OSIsoft PI connector dependencies not installed.\n"
                'Install with: pip install "sporedb[connectors]"'
            )
        )
        return

    engine = _get_engine(ctx)

    # If user provides --mapping, use it; otherwise build a dynamic mapping
    # from the --points argument using the default mapping template
    if mapping_path:
        mapping = load_mapping(Path(mapping_path))
    else:
        # Build a mapping dynamically from the point names
        from sporedb.connectors.config import FieldMapping

        point_list = [p.strip() for p in points.split(",")]
        variable_mappings = [
            FieldMapping(source=point, target=point.split("\\")[-1].lower())
            for point in point_list
        ]
        mapping = SchemaMapping(
            timestamp_field="timestamp",
            variable_mappings=variable_mappings,
        )

    config = ConnectorConfig(
        connector_type="osisoft_pi",
        host=host,
        auth={"username": username, "password": password},
        ssl_verify=not no_ssl_verify,
    )

    try:
        connector = OSIsoftPIConnector(config, engine)
        with connector:
            result = connector.pull(
                batch_name=batch_name,
                mapping=mapping,
                start_time=start,
                end_time=end,
            )
        _format_pull_result(result)
    except Exception as exc:
        console.print(error_panel(f"PI pull failed: {exc}"))


# --------------------------------------------------------------------------
# LabVantage LIMS subcommand
# --------------------------------------------------------------------------


@pull.command("labvantage")
@click.option("--host", required=True, help="LabVantage LIMS base URL")
@click.option("--username", required=True, help="LabVantage username")
@click.option(
    "--password",
    required=True,
    envvar="SPOREDB_LABVANTAGE_PASSWORD",
    help="LabVantage password (or set SPOREDB_LABVANTAGE_PASSWORD)",
)
@click.option(
    "--database-id", default="LIMS", help="LabVantage database ID (default: LIMS)"
)
@click.option(
    "--sample-ids", default=None, help="Comma-separated LIMS sample IDs (optional)"
)
@click.option("--batch-name", required=True, help="Name for the new SporeDB batch")
@click.option(
    "--mapping",
    "mapping_path",
    default=None,
    type=click.Path(exists=True),
    help="Path to YAML mapping file (default: built-in labvantage_default.yml)",
)
@click.pass_context
def pull_labvantage(
    ctx: click.Context,
    host: str,
    username: str,
    password: str,
    database_id: str,
    sample_ids: str | None,
    batch_name: str,
    mapping_path: str | None,
) -> None:
    """Pull assay data from LabVantage LIMS into a SporeDB batch."""
    try:
        from sporedb.connectors.labvantage import LabVantageLIMSConnector
    except ImportError:
        console.print(
            error_panel(
                "LabVantage LIMS connector dependencies not installed.\n"
                'Install with: pip install "sporedb[connectors]"'
            )
        )
        return

    engine = _get_engine(ctx)
    mapping = _load_mapping_or_default(mapping_path, "labvantage")

    config = ConnectorConfig(
        connector_type="labvantage",
        host=host,
        auth={"username": username, "password": password},
        extra={"database_id": database_id},
    )

    sample_id_list: list[str] = []
    if sample_ids:
        sample_id_list = [s.strip() for s in sample_ids.split(",")]

    try:
        connector = LabVantageLIMSConnector(config, engine)
        with connector:
            result = connector.pull(
                batch_name=batch_name,
                mapping=mapping,
                sample_ids=sample_id_list,
            )
        _format_pull_result(result)
    except Exception as exc:
        console.print(error_panel(f"LabVantage pull failed: {exc}"))


# --------------------------------------------------------------------------
# SciNote ELN subcommand
# --------------------------------------------------------------------------


@pull.command("scinote")
@click.option("--host", required=True, help="SciNote server URL")
@click.option("--client-id", required=True, help="OAuth2 client ID")
@click.option(
    "--client-secret",
    required=True,
    envvar="SPOREDB_SCINOTE_CLIENT_SECRET",
    help="OAuth2 client secret (or set SPOREDB_SCINOTE_CLIENT_SECRET)",
)
@click.option(
    "--access-token",
    required=True,
    envvar="SPOREDB_SCINOTE_ACCESS_TOKEN",
    help="OAuth2 access token (or set SPOREDB_SCINOTE_ACCESS_TOKEN)",
)
@click.option(
    "--refresh-token",
    required=True,
    envvar="SPOREDB_SCINOTE_REFRESH_TOKEN",
    help="OAuth2 refresh token (or set SPOREDB_SCINOTE_REFRESH_TOKEN)",
)
@click.option("--team-id", required=True, help="SciNote team ID")
@click.option("--project-id", required=True, help="SciNote project ID")
@click.option("--experiment-id", required=True, help="SciNote experiment ID")
@click.option("--batch-name", required=True, help="Name for the new SporeDB batch")
@click.option(
    "--mapping",
    "mapping_path",
    default=None,
    type=click.Path(exists=True),
    help="Path to YAML mapping file (default: built-in scinote_default.yml)",
)
@click.pass_context
def pull_scinote(
    ctx: click.Context,
    host: str,
    client_id: str,
    client_secret: str,
    access_token: str,
    refresh_token: str,
    team_id: str,
    project_id: str,
    experiment_id: str,
    batch_name: str,
    mapping_path: str | None,
) -> None:
    """Pull experiment data from SciNote ELN into a SporeDB batch."""
    try:
        from sporedb.connectors.scinote import SciNoteELNConnector
    except ImportError:
        console.print(
            error_panel(
                "SciNote ELN connector dependencies not installed.\n"
                'Install with: pip install "sporedb[connectors]"'
            )
        )
        return

    engine = _get_engine(ctx)
    mapping = _load_mapping_or_default(mapping_path, "scinote")

    config = ConnectorConfig(
        connector_type="scinote",
        host=host,
        auth={
            "client_id": client_id,
            "client_secret": client_secret,
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
        extra={
            "team_id": team_id,
            "project_id": project_id,
            "experiment_id": experiment_id,
        },
    )

    try:
        connector = SciNoteELNConnector(config, engine)
        with connector:
            result = connector.pull(
                batch_name=batch_name,
                mapping=mapping,
                team_id=team_id,
                project_id=project_id,
                experiment_id=experiment_id,
            )
        _format_pull_result(result)
    except Exception as exc:
        console.print(error_panel(f"SciNote pull failed: {exc}"))
