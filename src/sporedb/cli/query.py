"""CLI command for DSL query execution."""

from __future__ import annotations

import click

from sporedb.cli._output import console


@click.command("query")
@click.argument("expression")
@click.pass_context
def query_cmd(ctx: click.Context, expression: str) -> None:
    """Execute a bioprocess DSL query."""
    db = ctx.obj["db"]

    try:
        from lark.exceptions import UnexpectedInput
    except ImportError:
        UnexpectedInput = Exception  # type: ignore[assignment, misc]

    try:
        df = db.query(expression)
    except UnexpectedInput as exc:
        raise click.ClickException(f"Query parse error:\n{exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Query error: {exc}") from exc

    if df.empty:
        console.print("[dim]No results.[/dim]")
        return

    # Display as Rich table, truncated to 50 rows
    from rich.table import Table

    table = Table(title="Query Results")
    for col in df.columns:
        table.add_column(str(col))

    max_rows = 50
    for _, row in df.head(max_rows).iterrows():
        table.add_row(*(str(v) for v in row))

    console.print(table)
    if len(df) > max_rows:
        console.print(f"[dim]Showing {max_rows} of {len(df)} rows.[/dim]")
