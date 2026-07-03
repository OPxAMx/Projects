"""
Fusionne les trailers YouTube (générés par tmdb_trailers_async.py) dans votre
fichier JSON détaillé, en ajoutant un champ "url_trailer" à chaque entrée
dont le tmdb_id correspond.

Utilisation :
    python merge_trailers.py --data ma_base_detaillee.json --trailers trailers_films.csv --output ma_base_detaillee_updated.json
    python merge_trailers.py --data ma_base_detaillee.json --trailers trailers_films.csv --trailers trailers_series.csv --output ma_base_detaillee_updated.json

Vous pouvez passer --trailers plusieurs fois (un pour les films, un pour les séries).
"""

import json
import csv
import argparse


def load_trailer_map(csv_path):
    """
    Lit un CSV généré par tmdb_trailers_async.py (colonnes : tmdb_id, media_type,
    youtube_key, trailer_name, official, status) et retourne un dict
    { tmdb_id (str) : url_trailer (str) } pour les lignes où un trailer a été trouvé.
    """
    trailer_map = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tmdb_id = str(row["tmdb_id"]).strip()
            youtube_key = row.get("youtube_key", "").strip()
            status = row.get("status", "")

            if not youtube_key or status != "ok":
                continue

            trailer_map[tmdb_id] = f"https://www.youtube.com/watch?v={youtube_key}"
    return trailer_map


def merge(data_path, trailer_csv_paths, output_path):
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    # Fusionne les mappings de plusieurs CSV (ex: films.csv + series.csv)
    trailer_map = {}
    for csv_path in trailer_csv_paths:
        trailer_map.update(load_trailer_map(csv_path))

    matched = 0
    unmatched = 0

    for entry in data:
        # On matche sur tmdb_id en priorité, sinon sur id
        key = str(entry.get("tmdb_id") or entry.get("id") or "").strip()

        if key in trailer_map:
            entry["url_trailer"] = trailer_map[key]
            matched += 1
        else:
            entry.setdefault("url_trailer", "")
            unmatched += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ {matched} entrées mises à jour avec un url_trailer.")
    print(f"ℹ️  {unmatched} entrées sans trailer correspondant (url_trailer laissé vide).")
    print(f"Résultat écrit dans : {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Fusionne les trailers YouTube dans un JSON détaillé.")
    parser.add_argument("--data", required=True, help="Chemin vers le fichier JSON détaillé (le tableau complet).")
    parser.add_argument(
        "--trailers", required=True, action="append",
        help="Chemin vers un CSV de trailers (tmdb_trailers_async.py). Peut être répété plusieurs fois.",
    )
    parser.add_argument("--output", required=True, help="Chemin du fichier JSON de sortie.")
    return parser.parse_args()


def main():
    args = parse_args()
    merge(args.data, args.trailers, args.output)


if __name__ == "__main__":
    main()