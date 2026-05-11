"""CLI commands for batch management (create, list, show, delete)."""

from __future__ import annotations

from uuid import UUID

import click

from sporedb.cli._output import (
    console,
    format_batch_detail,
    format_batch_table,
)


@click.group()
def batch() -> None:
    """Manage bioprocess batches."""


@batch.command("create")
@click.argument("name")
@click.option("--strain", default=None, help="Organism strain")
@click.option("--media", default=None, help="Growth media")
@click.option("--scale", default=None, type=float, help="Scale in liters")
@click.option("--operator", default=None, help="Operator name")
@click.option("--tag", multiple=True, help="Batch tags (repeatable)")
@click.pass_context
def create_batch(
    ctx: click.Context,
    name: str,
    strain: str | None,
    media: str | None,
    scale: float | None,
    operator: str | None,
    tag: tuple[str, ...],
) -> None:
    """Create a new batch."""
    db = ctx.obj["db"]
    batch_obj = db.create_batch(
        name,
        strain=strain,
        media=media,
        scale_liters=scale,
        operator=operator,
        tags=list(tag) if tag else None,
    )
    console.print(format_batch_detail(batch_obj))


@batch.command("list")
@click.pass_context
def list_batches(ctx: click.Context) -> None:
    """List all batches."""
    db = ctx.obj["db"]
    batches = db.list_batches()
    if not batches:
        console.print("[dim]No batches found.[/dim]")
        return
    console.print(format_batch_table(batches))


@batch.command("show")
@click.argument("batch_id")
@click.pass_context
def show_batch(ctx: click.Context, batch_id: str) -> None:
    """Show batch details."""
    try:
        bid = UUID(batch_id)
    except ValueError:
        raise click.ClickException(f"Invalid batch ID format: {batch_id}") from None

    db = ctx.obj["db"]
    batch_obj = db.get_batch(bid)
    if batch_obj is None:
        raise click.ClickException(f"Batch not found: {batch_id}")
    console.print(format_batch_detail(batch_obj))


@batch.command("delete")
@click.argument("batch_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_batch(ctx: click.Context, batch_id: str, yes: bool) -> None:
    """Delete a batch."""
    try:
        bid = UUID(batch_id)
    except ValueError:
        raise click.ClickException(f"Invalid batch ID format: {batch_id}") from None

    if not yes:
        click.confirm(f"Delete batch {batch_id}?", abort=True)

    db = ctx.obj["db"]
    deleted = db.delete_batch(bid)
    if deleted:
        console.print(f"[green]Batch {batch_id} deleted.[/green]")
    else:
        raise click.ClickException(f"Batch not found: {batch_id}")
