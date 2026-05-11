"""CLI commands for the SporeDB demo dataset."""

from __future__ import annotations

import shutil
from pathlib import Path

import click

DEMO_DIR = Path.home() / ".sporedb"
DEMO_DATA = DEMO_DIR / "demo_data"


@click.group()
def demo() -> None:
    """Demo dataset commands for exploring SporeDB features."""


@demo.command()
@click.option("--force", is_flag=True, help="Reload even if demo data exists")
def load(force: bool) -> None:
    """Import the bundled ABPDU fermentation dataset.

    Creates batches with descriptive names, imports CSV data, and runs
    automatic phase detection. Results are stored at ~/.sporedb/demo_data/.
    """
    from rich.table import Table

    from sporedb.cli._output import console, error_panel
    from sporedb.client import SporeDB
    from sporedb.data.demo import get_demo_csv_paths

    # Idempotent check
    if DEMO_DATA.exists() and not force:
        console.print(
            "[yellow]Demo data already loaded.[/yellow] "
            "Use [bold]--force[/bold] to reload."
        )
        return

    # Clean existing if --force
    if DEMO_DATA.is_symlink():
        DEMO_DATA.unlink()
    elif DEMO_DATA.is_dir():
        shutil.rmtree(DEMO_DATA)

    csv_paths = get_demo_csv_paths()
    if not csv_paths:
        console.print(error_panel("No demo CSV files found in package."))
        return

    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    # Feedstock mapping from filename
    feedstock_map = {
        "glucose": "Glucose",
        "xylose": "Xylose",
        "hydrolysate": "Lignocellulosic hydrolysate",
    }

    with SporeDB(str(DEMO_DATA)) as db:
        table = Table(title="Demo Data Loaded")
        table.add_column("Run", style="bold cyan")
        table.add_column("Feedstock", style="green")
        table.add_column("Data Points", justify="right")
        table.add_column("Phases Detected", justify="right", style="yellow")

        for csv_path in csv_paths:
            # Derive batch name from filename:
            # abpdu_rt_glucose_001.csv -> ABPDU-Rt-glucose-001
            stem = csv_path.stem  # e.g., abpdu_rt_glucose_001
            parts = stem.split("_")
            batch_name = (
                f"{parts[0].upper()}-{parts[1].capitalize()}-{'-'.join(parts[2:])}"
            )

            # Determine feedstock
            feedstock = "Unknown"
            for key, label in feedstock_map.items():
                if key in stem:
                    feedstock = label
                    break

            # Import CSV (creates batch internally)
            result = db.import_csv(str(csv_path), batch_name)

            # Run phase detection using 'biomass' (OD600 maps to 'biomass' variable)
            phases = db.detect_phases(result.batch_id, signal="biomass")

            table.add_row(
                batch_name,
                feedstock,
                str(result.rows_imported),
                str(len(phases)),
            )

        console.print(table)
        console.print(
            "\n[green]Demo data loaded successfully.[/green] "
            "Try exploring with "
            "[bold]sporedb batch list --data-dir ~/.sporedb/demo_data[/bold]."
        )


@demo.command()
def clean() -> None:
    """Remove the demo database.

    Deletes all demo data at ~/.sporedb/demo_data/.
    """
    from sporedb.cli._output import console

    if DEMO_DATA.is_symlink():
        DEMO_DATA.unlink()
        console.print("[green]Demo data symlink removed.[/green]")
    elif DEMO_DATA.is_dir():
        shutil.rmtree(DEMO_DATA)
        console.print("[green]Demo data removed.[/green]")
    else:
        console.print("[yellow]No demo data found.[/yellow]")
