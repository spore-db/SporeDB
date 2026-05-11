"""CLI commands for SporeDB configuration."""

from __future__ import annotations

from pathlib import Path

import click

from sporedb.cli._output import console


@click.group()
def config() -> None:
    """View SporeDB configuration."""


@config.command("show")
@click.pass_context
def show_config(ctx: click.Context) -> None:
    """Show current SporeDB configuration."""
    db = ctx.obj["db"]
    data_dir = Path(db._engine.data_root).resolve()

    console.print(f"[bold]Data directory:[/bold] {data_dir}")
    console.print(f"[bold]Exists:[/bold] {data_dir.exists()}")

    if data_dir.exists():
        batches = db.list_batches()
        console.print(f"[bold]Batch count:[/bold] {len(batches)}")
