"""CLI commands for data import and export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

import click

from sporedb.cli._output import console, format_import_result


@click.group()
def data() -> None:
    """Import and export batch data."""


@data.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--name", required=True, help="Batch name for imported data")
@click.option(
    "--inoculation",
    default=None,
    help="Inoculation timestamp (ISO 8601 format)",
)
@click.pass_context
def import_data(
    ctx: click.Context,
    file: str,
    name: str,
    inoculation: str | None,
) -> None:
    """Import a CSV or Excel file into SporeDB."""
    db = ctx.obj["db"]

    inoc_dt: datetime | None = None
    if inoculation:
        try:
            inoc_dt = datetime.fromisoformat(inoculation)
        except ValueError:
            raise click.ClickException(
                f"Invalid inoculation timestamp: {inoculation}"
            ) from None

    path = Path(file)
    ext = path.suffix.lower()

    try:
        if ext == ".csv":
            result = db.import_csv(path, name, inoculation_ts=inoc_dt)
        elif ext in (".xlsx", ".xls"):
            result = db.import_excel(path, name, inoculation_ts=inoc_dt)
        else:
            raise click.ClickException(
                f"Unsupported file type: {ext}. Use .csv, .xlsx, or .xls"
            )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    # import_excel may return a list for multi-sheet files
    if isinstance(result, list):
        for r in result:
            console.print(format_import_result(r))
    else:
        console.print(format_import_result(result))


@data.command("export")
@click.argument("batch_id")
@click.option(
    "--format",
    "fmt",
    default="csv",
    type=click.Choice(["csv", "parquet", "arrow"]),
    help="Export format",
)
@click.option(
    "--output", "output_path", default=None, type=click.Path(), help="Output file path"
)
@click.pass_context
def export_data(
    ctx: click.Context,
    batch_id: str,
    fmt: str,
    output_path: str | None,
) -> None:
    """Export batch data to a file."""
    try:
        bid = UUID(batch_id)
    except ValueError:
        raise click.ClickException(f"Invalid batch ID format: {batch_id}") from None

    db = ctx.obj["db"]
    try:
        result = db.export(bid, format=fmt, output_path=output_path)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_path:
        console.print(f"[green]Exported to {output_path}[/green]")
    elif result is not None:
        # Write bytes to stdout
        click.echo(result)
