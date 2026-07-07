import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SAMPLE_FILE = SCRIPT_DIR / "sampleContent.json"
DATA_FILE = SCRIPT_DIR / "data_updated.json"
LOG_FILE = SCRIPT_DIR / "sampleContent_update.log"


def load_json(path: Path) -> Any:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_ids(items: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for item in items:
        item_id = item.get("id") or item.get("tmdb_id")
        if item_id is None:
            continue
        ids.add(str(item_id))
    return ids


def append_unique_items(existing_items: list[dict[str, Any]], new_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing_ids = extract_ids(existing_items)
    added_items: list[dict[str, Any]] = []

    for item in new_items:
        item_id = str(item.get("id") or item.get("tmdb_id") or "")
        if not item_id or item_id in existing_ids:
            continue

        existing_ids.add(item_id)
        added_items.append(item)

    if added_items:
        existing_items.extend(added_items)

    return existing_items, added_items


def write_log(added_items: list[dict[str, Any]], log_path: Path) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"[{timestamp}] {len(added_items)} nouvel(les) élément(s) ajouté(s) à sampleContent.json"]
    for item in added_items:
        item_id = item.get("id") or item.get("tmdb_id") or ""
        title = item.get("title") or ""
        lines.append(f"- {item_id}: {title}")
    if added_items:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    else:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{timestamp}] Aucun nouvel élément à ajouter.\n")


if __name__ == "__main__":
    existing_items = load_json(SAMPLE_FILE)
    if not isinstance(existing_items, list):
        existing_items = []

    new_items = load_json(DATA_FILE)
    if not isinstance(new_items, list):
        new_items = []

    merged_items, added_items = append_unique_items(existing_items, new_items)

    save_json(SAMPLE_FILE, merged_items)
    write_log(added_items, LOG_FILE)

    print(f"sampleContent.json mis à jour : {len(merged_items)} éléments")
    print(f"Éléments ajoutés : {len(added_items)}")
    print(f"Journal : {LOG_FILE}")
