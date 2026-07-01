#!/usr/bin/env python3
"""Vérifie, supprime et fusionne des fichiers JSON.

Exemples d'utilisation :
  python check_json_duplicates.py --path C:\\chemin\\vers\\dossier
  python check_json_duplicates.py --path C:\\chemin\\vers\\dossier --field id
  python check_json_duplicates.py --path C:\\chemin\\vers\\fichier.json --field id --deduplicate --write
  python check_json_duplicates.py --merge file1.json file2.json --field id --output merged.json
  python check_json_duplicates.py --merge-dir C:\\chemin\\vers\\dossier --field id --output merged.json
"""

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def normalize(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def iter_json_files(root: Path) -> Iterable[Path]:
    return sorted(root.rglob("*.json"))


def load_json_data(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def record_score(record: Any) -> int:
    if not isinstance(record, dict):
        return 0

    score = 0

    for field in ("id", "type"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            score += 2

    title = record.get("title")
    if isinstance(title, str) and title.strip():
        score += 3 + min(len(title), 20) // 2

    description = record.get("description")
    if isinstance(description, str) and description.strip():
        score += 2 + min(len(description), 40) // 10

    tags = record.get("tags")
    if isinstance(tags, list):
        score += min(len(tags), 10)

    thumbnail = record.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail.strip():
        score += 2

    embed = record.get("embed")
    if isinstance(embed, dict):
        score += 2 + sum(1 for value in embed.values() if value not in [None, "", [], {}])

    meta = record.get("meta")
    if isinstance(meta, dict):
        score += 1 + sum(1 for value in meta.values() if value not in [None, "", [], {}])

    return score


def find_duplicates_in_file(path: Path, field: str | None = None) -> list[dict[str, Any]]:
    data = load_json_data(path)
    records: list[Any] = data if isinstance(data, list) else [data]

    seen: dict[Any, int] = {}
    duplicates: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        if field is not None:
            if not isinstance(record, dict):
                raise TypeError(f"Le champ '{field}' ne peut être utilisé que sur des objets JSON. Fichier : {path}")
            if field not in record:
                raise KeyError(f"Le champ '{field}' est introuvable dans un objet du fichier : {path}")
            key = record[field]
        else:
            if isinstance(record, dict) and "id" in record:
                key = record.get("id")
            else:
                key = normalize(record)

        if key in seen:
            duplicates.append({
                "position": index,
                "value": record,
                "first_position": seen[key],
            })
        else:
            seen[key] = index

    return duplicates


def deduplicate_records(records: list[Any], field: str | None = None) -> tuple[list[Any], int]:
    deduped: list[Any] = []
    positions: dict[Any, int] = {}
    removed = 0

    for record in records:
        if field is not None:
            if not isinstance(record, dict):
                raise TypeError(f"Le champ '{field}' ne peut être utilisé que sur des objets JSON.")
            if field not in record:
                raise KeyError(f"Le champ '{field}' est introuvable dans un objet JSON.")
            key = record[field]
        else:
            if isinstance(record, dict) and "id" in record:
                key = record.get("id")
            else:
                key = normalize(record)

        if key not in positions:
            positions[key] = len(deduped)
            deduped.append(record)
        else:
            previous = deduped[positions[key]]
            if record_score(record) > record_score(previous):
                deduped[positions[key]] = record
            removed += 1

    return deduped, removed


def deduplicate_file(path: Path, field: str | None = None, write: bool = False) -> int:
    data = load_json_data(path)
    if not isinstance(data, list):
        raise TypeError(f"Le fichier {path} n'est pas une liste JSON.")

    deduped, removed = deduplicate_records(data, field=field)
    if write and removed > 0:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(deduped, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return removed


def title_case(value: str) -> str:
    if not isinstance(value, str):
        return value
    words = value.split()
    if not words:
        return value
    return " ".join(word[:1].upper() + word[1:] if word else "" for word in words)


def normalize_titles(records: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for record in records:
        if isinstance(record, dict):
            updated = dict(record)
            title = updated.get("title")
            if isinstance(title, str) and title.strip():
                updated["title"] = title_case(title)
            normalized.append(updated)
        else:
            normalized.append(record)
    return normalized


def merge_json_files(paths: list[Path], field: str | None = None) -> tuple[list[Any], int]:
    merged_records: list[Any] = []

    for path in paths:
        if not path.exists():
            continue
        data = load_json_data(path)
        if isinstance(data, list):
            merged_records.extend(data)
        else:
            merged_records.append(data)

    deduped, removed = deduplicate_records(merged_records, field=field)
    return normalize_titles(deduped), removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Vérifie, supprime et fusionne des fichiers JSON.")
    parser.add_argument("--path", help="Fichier ou dossier à analyser (recherche récursive).")
    parser.add_argument("--folder", help="Dossier à analyser si vous voulez préciser un chemin explicite.")
    parser.add_argument("--field", default=None, help="Nom du champ à comparer pour détecter les doublons (ex. id).")
    parser.add_argument("--deduplicate", action="store_true", help="Supprime les doublons en gardant l'entrée la plus riche.")
    parser.add_argument("--write", action="store_true", help="Écrit les changements dans les fichiers JSON.")
    parser.add_argument("--merge", nargs="+", help="Liste de fichiers JSON à fusionner en une seule liste.")
    parser.add_argument("--merge-dir", help="Dossier contenant les fichiers JSON à fusionner.")
    parser.add_argument("--output", help="Chemin du fichier JSON de sortie lors d'un merge.")
    parser.add_argument("--merge-folder", help="Fusionne tous les fichiers JSON d'un dossier en un seul fichier de sortie.")
    args = parser.parse_args()

    if args.merge or args.merge_dir or args.merge_folder:
        merge_paths: list[Path] = []
        if args.merge:
            for item in args.merge:
                path = Path(item).expanduser().resolve()
                if not path.exists():
                    raise SystemExit(f"Le fichier n'existe pas : {path}")
                merge_paths.append(path)
        elif args.merge_dir:
            root = Path(args.merge_dir).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise SystemExit(f"Le dossier n'existe pas ou n'est pas un dossier : {root}")
            merge_paths = list(iter_json_files(root))
        else:
            root = Path(args.merge_folder).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise SystemExit(f"Le dossier n'existe pas ou n'est pas un dossier : {root}")
            merge_paths = list(iter_json_files(root))

        if not merge_paths:
            raise SystemExit("Aucun fichier JSON à fusionner.")

        output_path = Path(args.output).expanduser().resolve() if args.output else None
        if output_path is not None:
            merge_paths = [path for path in merge_paths if path.resolve() != output_path]

        merged_records, removed = merge_json_files(merge_paths, field=args.field)
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as fh:
                json.dump(merged_records, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print(f"Fusion terminée : {len(merged_records)} élément(s) enregistrés dans {output_path}")
        else:
            print(json.dumps(merged_records, ensure_ascii=False, indent=2))

        print(f"{removed} doublon(s) supprimé(s) pendant la fusion.")
        return

    target_path = args.path or args.folder
    if not target_path:
        raise SystemExit("Vous devez fournir --path ou --folder.")

    target = Path(target_path).expanduser().resolve()
    if not target.exists():
        raise SystemExit(f"Le chemin n'existe pas : {target}")

    if target.is_file():
        paths = [target]
    else:
        paths = list(iter_json_files(target))

    if not paths:
        print(f"Aucun fichier JSON trouvé dans : {target}")
        return

    total_duplicates = 0
    print(f"Analyse de {len(paths)} fichier(s) JSON dans : {target}")

    for path in paths:
        try:
            duplicates = find_duplicates_in_file(path, field=args.field)
            if args.deduplicate:
                removed = deduplicate_file(path, field=args.field, write=args.write)
                if removed > 0:
                    print(f"- {path.name}: {removed} doublon(s) supprimé(s)")
                    total_duplicates += removed
                else:
                    print(f"- {path.name}: aucun doublon à supprimer")
            elif duplicates:
                print(f"\n{path.name}")
                for item in duplicates:
                    print(f"  - Doublon à la position {item['position']} (première occurrence : {item['first_position']})")
                total_duplicates += len(duplicates)
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"[ERREUR] {path.name}: {exc}")
            continue

    if total_duplicates == 0:
        print("\nAucun doublon détecté.")
    else:
        print(f"\n{total_duplicates} doublon(s) traité(s) au total.")


if __name__ == "__main__":
    main()
