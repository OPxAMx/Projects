import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, List, Set

def load_api_key() -> str:
    for key_name in ("TMDB_API_KEY", "TMDB_BEARER_TOKEN"):
        value = os.getenv(key_name)
        if value and value.strip():
            return value.strip()

    api_key_path = Path(__file__).resolve().parent / "apiKEY"
    if api_key_path.exists():
        text = api_key_path.read_text(encoding="utf-8")
        match = re.search(r"=\s*['\"]?([^'\"\s]+)['\"]?", text)
        if match:
            return match.group(1)

    raise RuntimeError("Clé TMDB introuvable.")

def extract_existing_ids(sample_path: Path) -> Set[str]:
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    ids: Set[str] = set()

    def scan(node: Any):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"tmdb_id", "tmdbId", "tmdbID", "id", "movie_id", "tv_id"}:
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        ids.add(str(int(value)))
                    elif isinstance(value, str) and value.isdigit():
                        ids.add(value)
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(data)
    return ids

def ask_user_choice():
    print("Que voulez-vous découvrir ?")
    print("1. Films")
    print("2. Séries")
    choice = input("Votre choix (1/2): ").strip().lower()
    while choice not in {"1", "2", "film", "films", "serie", "series", "séries"}:
        choice = input("Choix invalide. Tapez 1 pour Films ou 2 pour Séries: ").strip().lower()

    if choice in {"1", "film", "films"}:
        return "movie"
    return "tv"

def ask_page_count():
    while True:
        try:
            pages = int(input("Combien de pages voulez-vous extraire ? "))
            if pages > 0:
                return pages
            print("Veuillez entrer un nombre supérieur à 0.")
        except ValueError:
            print("Veuillez entrer un nombre entier valide.")


def ask_year():
    year = input("Quel année voulez-vous rechercher ? (laisser vide pour ignorer) ").strip()
    if not year:
        return None
    while not year.isdigit() or len(year) != 4:
        print("Veuillez entrer une année valide sur 4 chiffres.")
        year = input("Quel année voulez-vous rechercher ? (laisser vide pour ignorer) ").strip()
    return int(year)


def ask_region():
    region = input("Quelle région voulez-vous utiliser ? (ex: US, FR, GB, laisser vide pour ignorer) ").strip().upper()
    if not region:
        return None
    return region


def fetch_discover(api_key: str, existing_ids: Set[str], media_type: str, pages: int, year: int | None, region: str | None, limit: int = 10000):
    endpoint = "movie" if media_type == "movie" else "tv"
    results = []
    seen = set()

    for page in range(1, pages + 1):
        params = {
            "sort_by": "popularity.desc",
            "page": page,
            "include_adult": "false",
            "language": "fr-FR",
            "original_language": "en-US",
            
            
        }
        if year is not None:
            params["year"] = year
        if region is not None:
            params["region"] = region

        headers = {"accept": "application/json"}
        if api_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            params["api_key"] = api_key

        req = urllib.request.Request(
            "https://api.themoviedb.org/3/discover/" + endpoint + "?" + urllib.parse.urlencode(params),
            headers=headers,
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.load(response)

        for item in payload.get("results", []):
            item_id = str(item.get("id", ""))
            if not item_id or item_id in existing_ids or item_id in seen:
                continue
            results.append(item)
            seen.add(item_id)
            if len(results) >= limit:
                return results

    return results

if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent
    sample_file = script_dir / "sampleContent.json"
    output_file = script_dir / "discover-movie-output.json"

    media_type = ask_user_choice()
    pages = ask_page_count()
    year = ask_year()
    region = ask_region()

    existing_ids = extract_existing_ids(sample_file)
    api_key = load_api_key()
    discovered = fetch_discover(api_key, existing_ids, media_type, pages, year, region)

    out_ids = [str(item["id"]) for item in discovered]
    Path(output_file).write_text(json.dumps(discovered, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(script_dir / "new_tmdb_ids.json").write_text(json.dumps(out_ids, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Nombre d'éléments récupérés : {len(discovered)}")