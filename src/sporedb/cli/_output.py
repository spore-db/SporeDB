"""Rich terminal output helpers for SporeDB CLI."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

console = Console()


def format_batch_table(batches: list[Any]) -> Table:
    """Format batch list as a Rich table."""
    table = Table(title="Batches", show_lines=False)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Name", style="bold cyan")
    table.add_column("Lifecycle", style="green")
    table.add_column("Strain")
    table.add_column("Created", style="dim")
    for b in batches:
        table.add_row(
            str(b.batch_id)[:8] + "...",
            escape(b.name),
            b.lifecycle.value,
            escape(b.metadata.strain or "-"),
            b.created_at.strftime("%Y-%m-%d %H:%M") if b.created_at else "-",
        )
    return table


def format_import_result(result: Any) -> Panel:
    """Format import result as a Rich panel."""
    mapped = ", ".join(f"{k}->{v}" for k, v in result.columns_mapped.items()) or "none"
    warnings_text = (
        "\n".join(f"  [yellow]! {w}[/yellow]" for w in result.warnings)
        if result.warnings
        else ""
    )
    body = (
        f"[green]Imported {result.rows_imported} rows[/green]\n"
        f"Batch ID: {result.batch_id}\n"
        f"Columns mapped: {mapped}\n"
        f"Time: {result.elapsed_seconds:.2f}s"
    )
    if warnings_text:
        body += f"\n{warnings_text}"
    return Panel(body, title="Import Complete")


def format_batch_detail(batch: Any) -> Panel:
    """Format single batch detail as a Rich panel."""
    lines = [
        f"[bold]Name:[/bold] {escape(batch.name)}",
        f"[bold]ID:[/bold] {batch.batch_id}",
        f"[bold]Lifecycle:[/bold] {batch.lifecycle.value}",
        f"[bold]Strain:[/bold] {escape(batch.metadata.strain or '-')}",
        f"[bold]Media:[/bold] {escape(batch.metadata.media or '-')}",
        f"[bold]Scale:[/bold] {batch.metadata.scale_liters or '-'} L",
        f"[bold]Operator:[/bold] {escape(batch.metadata.operator or '-')}",
        f"[bold]Tags:[/bold] {escape(', '.join(batch.tags) if batch.tags else '-')}",
    ]
    if batch.timestamps.inoculation:
        lines.append(f"[bold]Inoculation:[/bold] {batch.timestamps.inoculation}")
    return Panel("\n".join(lines), title=f"Batch: {batch.name}")


def error_panel(message: str) -> Panel:
    """Format error message as a red Rich panel."""
    return Panel(f"[red]{escape(message)}[/red]", title="Error", border_style="red")
