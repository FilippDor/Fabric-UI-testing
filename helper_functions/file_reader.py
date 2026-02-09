from pathlib import Path
import json
from typing import TypeVar, List, Any

T = TypeVar("T", bound=Any)

def read_json_files_from_folder(folder_path: str | Path) -> List[T]:
    """
    Read all JSON files from a folder and return a flat list of reports.
    Assumes each JSON file has a top-level key "reports" that is a list.
    """
    folder = Path(folder_path).resolve()

    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder}")

    if not folder.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {folder}")

    all_reports: List[T] = []

    for json_file in folder.glob("*.json"):
        try:
            with json_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure 'reports' key exists and is a list
                reports = data.get("reports", [])
                if isinstance(reports, list):
                    all_reports.extend(reports)  # <-- flatten here
                else:
                    print(f"Warning: 'reports' is not a list in file {json_file}")
        except Exception as exc:
            print(f"Failed to read/parse JSON file: {json_file}")
            print(exc)

    return all_reports
