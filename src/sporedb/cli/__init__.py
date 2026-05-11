"""SporeDB CLI: command-line interface for batch management and automation.

Entry point: `sporedb` console script (registered via pyproject.toml [project.scripts]).
"""

from __future__ import annotations

import click

from sporedb.client import SporeDB


@click.group()
@click.option(
    "--data-dir",
    envvar="SPOREDB_DATA_DIR",
    default="./sporedb_data",
    type=click.Path(),
    help="SporeDB data directory",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress non-essential output")
@click.version_option(package_name="sporedb")
@click.pass_context
def cli(ctx: click.Context, data_dir: str, quiet: bool) -> None:
    """SporeDB - Bioprocess-native time-series database."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = SporeDB(data_dir)
    ctx.obj["quiet"] = quiet


# Register sub-command groups after cli definition to avoid circular imports
from sporedb.cli.batch import batch  # noqa: E402
from sporedb.cli.config import config  # noqa: E402
from sporedb.cli.data import data  # noqa: E402
from sporedb.cli.query import query_cmd  # noqa: E402

cli.add_command(batch)
cli.add_command(data)
cli.add_command(query_cmd, "query")
cli.add_command(config)

from sporedb.cli.demo import demo  # noqa: E402

cli.add_command(demo)

# pull command requires connectors extra (pyyaml) -- register only if available
try:
    from sporedb.cli.pull import pull  # noqa: E402

    cli.add_command(pull)
except ImportError:
    pass

__all__ = ["cli"]
