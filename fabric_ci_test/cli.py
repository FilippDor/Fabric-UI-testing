"""CLI entry point for fabric-ci-test."""

import os
import sys
import subprocess
import webbrowser
from pathlib import Path

import click
from dotenv import load_dotenv


def _find_project_root():
    """Find the project root by looking for pytest.ini or pyproject.toml."""
    cwd = Path.cwd()
    for marker in ("pytest.ini", "pyproject.toml", ".env"):
        if (cwd / marker).exists():
            return cwd
    return cwd


@click.group()
@click.version_option(package_name="fabric-ci-test")
def cli():
    """Fabric CI Test - Power BI visual regression testing."""


@cli.command()
def init():
    """Scaffold .env file and install Playwright browsers."""
    root = _find_project_root()
    env_file = root / ".env"
    env_example = root / ".env.example"

    if not env_file.exists():
        if env_example.exists():
            env_file.write_text(
                env_example.read_text(encoding="utf-8"), encoding="utf-8"
            )
            click.echo(f"Created {env_file} from .env.example")
        else:
            template = (
                "SP_CLIENT_ID = 'your-service-principal-client-id'\n"
                "SP_TENANT_ID = 'your-azure-tenant-id'\n"
                "SP_CLIENT_SECRET = 'your-service-principal-client-secret'\n"
                "WORKSPACE_ID = 'your-power-bi-workspace-id'\n"
                "ENVIRONMENT = 'prod'\n"
                "DEFAULT_RLS_ROLE = 'master'\n"
            )
            env_file.write_text(template, encoding="utf-8")
            click.echo(f"Created {env_file} with default template")
    else:
        click.echo(f"{env_file} already exists, skipping.")

    click.echo("Edit .env with your Service Principal credentials.")

    click.echo("\nInstalling Playwright browsers (chromium)...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"],
        check=False,
    )
    if result.returncode == 0:
        click.echo("Playwright browsers installed successfully.")
    else:
        click.echo("Failed to install Playwright browsers.", err=True)
        sys.exit(result.returncode)


@cli.command()
def fetch():
    """Refresh workspace metadata (reports & datasets from Power BI API)."""
    root = _find_project_root()
    load_dotenv(root / ".env")

    script = root / "helper_functions" / "get_workspace_reports_datasets.py"
    if not script.exists():
        click.echo(f"Error: {script} not found.", err=True)
        sys.exit(1)

    click.echo("Fetching workspace metadata...")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        check=False,
    )
    if result.returncode != 0:
        click.echo("Metadata fetch failed.", err=True)
    sys.exit(result.returncode)


@cli.command(context_settings={"ignore_unknown_options": True})
@click.option(
    "--workers", "-n", default="auto", help="Number of parallel workers (integer or 'auto')."
)
@click.option(
    "--filter", "-k", "test_filter", default=None, help="Filter tests by name (pytest -k)."
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test(workers, test_filter, pytest_args):
    """Run visual regression tests."""
    root = _find_project_root()
    load_dotenv(root / ".env")

    cmd = [sys.executable, "-m", "pytest"]

    if workers:
        cmd.extend(["-n", str(workers)])
    if test_filter:
        cmd.extend(["-k", test_filter])

    cmd.extend(pytest_args)

    click.echo("Running visual regression tests...")
    result = subprocess.run(cmd, cwd=str(root), check=False)
    sys.exit(result.returncode)


@cli.command()
@click.option("--json", "show_json", is_flag=True, help="Open JSON results instead.")
def report(show_json):
    """Open the test report in the browser."""
    root = _find_project_root()
    results_dir = root / "tests" / "test-results"

    target = results_dir / (
        "all_reports_results.json" if show_json else "report.html"
    )

    if not target.exists():
        click.echo(f"Report not found: {target}", err=True)
        click.echo("Run 'fabric-ci-test test' first to generate a report.")
        sys.exit(1)

    click.echo(f"Opening {target.name}...")
    webbrowser.open(target.as_uri())
