#!/usr/bin/env python3
"""Normalize Vidking embed URLs in JSON files.

Examples:
- <iframe src="https://www.vidking.net/embed/movie/14784-the-fall/14784/" ...>
  -> <iframe src="https://www.vidking.net/embed/movie/14784" ...>
- https://www.vidking.net/embed/tv/1416/1/1?foo=bar
  -> https://www.vidking.net/embed/tv/1416

The script updates any field/value containing a Vidking embed URL, including
nested objects and lists, and normalizes the media type to either "film"
(movie) or "series" (tv) when possible.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

IFRAME_SRC_RE = re.compile(r"src=[\"'](https?://[^\"']+)[\"']")
TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def strip_json_comments(text: str) -> str:
    """Remove JS/JSONC comments so the file can be parsed as JSON."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    return text


def get_content_id_from_object(obj: Any) -> str | None:
    if not isinstance(obj, dict):
        return None

    for key in ("tmdb_id", "tmdbId", "tmdb", "id"):
        value = obj.get(key)
        if isinstance(value, (int, str)):
            text = str(value).strip()
            if text:
                match = re.search(r"\d+", text)
                if match:
                    return match.group(0)
    return None


def normalize_vidking_url(value: str, fallback_id: str | None = None) -> str:
    """Return a normalized Vidking embed URL or unchanged string."""
    if not isinstance(value, str):
        return value

    iframe_match = IFRAME_SRC_RE.search(value)
    if iframe_match:
        original_url = iframe_match.group(1)
        normalized_url = normalize_vidking_url(original_url, fallback_id=fallback_id)
        return value.replace(original_url, normalized_url, 1)

    if "vidking.net/embed/" not in value:
        return value

    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if not parts:
        return value

    if parts[0] == "embed":
        parts = parts[1:]
    if not parts:
        return value

    kind = parts[0].lower()
    if kind in {"movie", "film"}:
        canonical_kind = "movie"
    elif kind in {"tv", "series", "serie", "tvshow"}:
        canonical_kind = "tv"
    else:
        return value

    if fallback_id:
        media_id = fallback_id
    else:
        numeric_parts = [p for p in parts[1:] if re.fullmatch(r"\d+", p)]
        media_id = numeric_parts[-1] if numeric_parts else ""

    if not media_id:
        matches = re.findall(r"\d+", path)
        media_id = matches[-1] if matches else ""

    if not media_id:
        return value

    if canonical_kind == "tv":
        return f"https://www.vidking.net/embed/{canonical_kind}/{media_id}/1/1?nextEpisode=true&episodeSelector=true"

    return f"https://www.vidking.net/embed/{canonical_kind}/{media_id}"


def normalize_value(value: Any, fallback_id: str | None = None) -> bool:
    changed = False

    if isinstance(value, dict):
        object_fallback_id = fallback_id or get_content_id_from_object(value)

        # Normalize type if present
        if "type" in value and isinstance(value["type"], str):
            low = value["type"].strip().lower()
            if low in {"film", "movie"}:
                value["type"] = "film"
                changed = True
            elif low in {"serie", "series", "tv", "tvshow"}:
                value["type"] = "series"
                changed = True

        # Normalize iframe/url inside this object
        for key in ("iframe", "url"):
            if key in value and isinstance(value[key], str):
                new_value = normalize_vidking_url(value[key], fallback_id=object_fallback_id)
                if new_value != value[key]:
                    value[key] = new_value
                    changed = True

        # Normalize nested embed dict
        if "embed" in value and isinstance(value["embed"], dict):
            embed_changed = False
            embed = value["embed"]
            for key in ("iframe", "url"):
                if key in embed and isinstance(embed[key], str):
                    new_value = normalize_vidking_url(embed[key], fallback_id=object_fallback_id)
                    if new_value != embed[key]:
                        embed[key] = new_value
                        embed_changed = True
            if embed_changed:
                changed = True

        # Recurse into nested content
        for child in value.values():
            if isinstance(child, (dict, list)) and normalize_value(child, fallback_id=object_fallback_id):
                changed = True

    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)) and normalize_value(item, fallback_id=fallback_id):
                changed = True

    return changed


def repair_json_text(text: str) -> str:
    text = text.strip()
    text = TRAILING_COMMA_RE.sub(r"\1", text)
    return text


def process_file(path: Path, dry_run: bool = False, output_path: Path | None = None) -> tuple[int, Path | None]:
    with path.open("r", encoding="utf-8") as fh:
        text = fh.read()

    repaired = repair_json_text(strip_json_comments(text))
    data = json.loads(repaired)

    changed = normalize_value(data)
    if changed and not dry_run:
        if output_path is None:
            output_path = path.with_name("Update.json")
            if output_path.resolve() == path.resolve():
                output_path = path.with_name(f"{path.stem}_Update.json")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        return 1, output_path

    return 1 if changed else 0, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize Vidking embed URLs in one or more JSON files")
    parser.add_argument("paths", nargs="+", help="JSON files or folders to process")
    parser.add_argument("--dry-run", action="store_true", help="Show which files would change without editing them")
    args = parser.parse_args()

    files_to_process: list[Path] = []
    for raw_path in args.paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            print(f"[skip] {path} does not exist")
            continue
        if path.is_file():
            files_to_process.append(path)
        elif path.is_dir():
            files_to_process.extend(sorted(path.rglob("*.json")))

    if not files_to_process:
        print("No JSON files found")
        return

    changed_count = 0
    for path in files_to_process:
        try:
            output_path = None
            if not args.dry_run:
                if len(files_to_process) == 1:
                    output_path = path.parent / "Update.json"
                else:
                    output_path = path.with_name(f"{path.stem}_Update.json")

            count, saved_path = process_file(path, dry_run=args.dry_run, output_path=output_path)
            changed_count += count
            status = "changed" if count else "unchanged"
            if args.dry_run and count:
                print(f"[would change] {path}")
            elif saved_path:
                print(f"[{status}] {path} -> {saved_path}")
            else:
                print(f"[{status}] {path}")
        except Exception as exc:
            print(f"[error] {path}: {exc}")

    print(f"Processed {len(files_to_process)} file(s); {changed_count} changed")


if __name__ == "__main__":
    main()
