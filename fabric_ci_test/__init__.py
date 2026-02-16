"""Fabric CI Test, Power BI visual regression testing."""

__version__ = "0.1.0"

import os
import sys
import subprocess
import webbrowser
from pathlib import Path
from dotenv import load_dotenv


def _find_project_root() -> Path:
    """Walk up from CWD looking for conftest.py or pytest.ini as project markers."""
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pytest.ini").exists() or (parent / "conftest.py").exists():
            return parent
    return cwd


def init(env_file: str = ".env.example"):
    """Scaffold environment: copy .env template and install Playwright browsers."""
    root = _find_project_root()
    source = root / env_file
    target = root / ".env"

    if target.exists():
        print(f".env already exists at {target}")
    elif source.exists():
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Created .env from {env_file}")
    else:
        print(f"No {env_file} found at {root}. Create a .env file manually.")

    print("Installing Playwright browsers...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install"],
        check=True,
    )
    print("Done.")


def fetch() -> dict:
    """Refresh workspace metadata (reports + datasets) from the Power BI API.

    Reads credentials from environment variables / .env file.
    Returns the metadata dict and writes it to metadata/reports/reports_datasets.json.
    """
    root = _find_project_root()
    load_dotenv(root / ".env")

    client_id = os.environ.get("SP_CLIENT_ID")
    client_secret = os.environ.get("SP_CLIENT_SECRET")
    tenant_id = os.environ.get("SP_TENANT_ID")
    workspace_id = os.environ.get("WORKSPACE_ID")
    environment = os.environ.get("ENVIRONMENT", "prod")

    missing = [
        name
        for name, value in {
            "SP_CLIENT_ID": client_id,
            "SP_TENANT_ID": tenant_id,
            "SP_CLIENT_SECRET": client_secret,
            "WORKSPACE_ID": workspace_id,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    from helper_functions.get_workspace_reports_datasets import fetch_workspace_metadata

    output_path = root / "metadata" / "reports" / "reports_datasets.json"
    return fetch_workspace_metadata(
        client_id=client_id,
        client_secret=client_secret,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        environment=environment,
        output_path=output_path,
    )


def test(workers: int | str = 1, filter: str | None = None, *extra_args: str) -> int:
    """Run the visual regression tests via pytest.

    Args:
        workers: Number of parallel workers (int) or "auto". 1 = no parallelism.
        filter: pytest -k filter expression (e.g. "test_pbi_visual_validation").
        extra_args: Additional arguments passed through to pytest.

    Returns:
        pytest exit code (0 = all passed).
    """
    root = _find_project_root()
    load_dotenv(root / ".env")

    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", f"--rootdir={root}"]

    if workers != 1:
        cmd.append(f"-n={workers}")

    if filter:
        cmd.append(f"-k={filter}")

    cmd.extend(extra_args)

    # Run as subprocess to avoid Playwright sync API conflicting with
    # Jupyter's asyncio event loop.
    result = subprocess.run(cmd, cwd=str(root))
    return result.returncode


def report(json_output: bool = False):
    """Open the test results report.

    Args:
        json_output: If True, print the JSON results path instead of opening HTML.
    """
    root = _find_project_root()
    results_dir = root / "tests" / "test-results"

    if json_output:
        json_file = results_dir / "all_reports_results.json"
        if json_file.exists():
            print(str(json_file))
        else:
            print(f"No results found at {json_file}")
    else:
        html_file = results_dir / "report.html"
        if html_file.exists():
            webbrowser.open(html_file.as_uri())
            print(f"Opened {html_file}")
        else:
            print(f"No report found at {html_file}. Run test() first.")
