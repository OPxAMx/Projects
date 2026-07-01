import json
import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TMDB_API_KEY = os.getenv(
    "TMDB_API_KEY",
    "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0",
)
REQUEST_DELAY_SECONDS = 0.8
SAVE_EVERY_N_ITEMS = 20
OUTPUT_FILE = "data_updated.json"
LOG_FILE = "tmdb_scraper.log"


def build_request_kwargs() -> dict[str, Any]:
    if TMDB_API_KEY.startswith("eyJ"):
        return {
            "headers": {"Authorization": f"Bearer {TMDB_API_KEY}"},
            "params": {"language": "fr-FR"},
        }
    return {
        "params": {"api_key": TMDB_API_KEY, "language": "fr-FR"},
        "headers": {},
    }


def create_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def log_error(message: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")


def save_data(data: list[dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def translate_text(text: str) -> str:
    if not text:
        return ""
    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source="auto", target="fr").translate(text)
    except Exception as exc:
        print(f"⚠️ Traduction non disponible : {exc}")
        return text


def build_image_url(path: str | None) -> str:
    if not path:
        return ""
    return f"https://image.tmdb.org/t/p/w500{path}"


def get_tmdb_details(item: dict[str, Any], session: requests.Session) -> dict[str, Any]:
    item_id = item.get("id")
    if not item_id:
        return {"status": "skip"}

    type_media = str(item.get("type", "")).strip().lower()
    if type_media in {"film", "movie"}:
        endpoint = f"https://api.themoviedb.org/3/movie/{item_id}"
    elif type_media in {"series", "tv", "show", "serie"}:
        endpoint = f"https://api.themoviedb.org/3/tv/{item_id}"
    else:
        print(f"⚠️ Type inconnu pour ID {item_id}, type='{type_media}' → ignoré")
        return {"status": "skip"}

    print(f"\n🔎 Traitement ID: {item_id} ({type_media})")
    request_kwargs = build_request_kwargs()

    try:
        response = session.get(endpoint, timeout=20, **request_kwargs)
        if response.status_code == 401:
            message = f"401 Unauthorized pour ID {item_id} : vérifiez la clé API TMDB"
            print(f"❌ {message}")
            log_error(message)
            return {"status": "error", "message": message}

        response.raise_for_status()
        data = response.json()

        item["title"] = data.get("title") or data.get("name") or item.get("title", "")
        item["original_title"] = data.get("original_title") or data.get("original_name") or item.get("title", "")
        item["description"] = data.get("overview") or ""
        item["description_fr"] = translate_text(item["description"]) if item.get("description") else ""
        if item.get("description_fr"):
            item["description"] = item["description_fr"]

        item["thumbnail"] = build_image_url(data.get("poster_path"))
        item["backdrop"] = build_image_url(data.get("backdrop_path"))
        item["release_date"] = data.get("release_date") or data.get("first_air_date") or ""
        item["runtime"] = data.get("runtime") or data.get("episode_run_time") or ""
        item["vote_average"] = data.get("vote_average")
        item["popularity"] = data.get("popularity")
        item["status"] = data.get("status") or ""
        item["homepage"] = data.get("homepage") or ""
        item["language"] = data.get("original_language") or ""
        item["genres"] = [genre.get("name", "") for genre in data.get("genres", []) if genre.get("name")]
        item["tags"] = item.get("genres", [])
        item["production_companies"] = [company.get("name", "") for company in data.get("production_companies", []) if company.get("name")]

        item["source"] = "TMDb API"
        item["tmdb_id"] = item_id

        credits_endpoint = f"{endpoint}/credits"
        try:
            credits_response = session.get(credits_endpoint, timeout=20, **request_kwargs)
            if credits_response.ok:
                credits_data = credits_response.json()
                item["cast"] = [actor.get("name", "") for actor in credits_data.get("cast", [])[:10] if actor.get("name")]
                item["director"] = next(
                    (member.get("name", "") for member in credits_data.get("crew", []) if member.get("job") == "Director"),
                    "",
                )
                item["producers"] = [
                    member.get("name", "")
                    for member in credits_data.get("crew", [])
                    if member.get("job") in {"Producer", "Executive Producer"}
                ]
        except Exception as exc:
            print(f"⚠️ Erreur crédits pour ID {item_id} : {exc}")

        print(f"✔ Titre : {item['title']}")
        print(f"✔ Description : {item['description'][:120] if item.get('description') else ''}")
        print(f"✔ Tags : {item['tags']}")
        return {"status": "ok"}

    except requests.exceptions.HTTPError as exc:
        message = f"HTTPError ID {item_id}: {exc}"
        print(f"❌ {message}")
        log_error(message)
        return {"status": "error", "message": message}
    except requests.exceptions.RequestException as exc:
        message = f"RequestException ID {item_id}: {exc}"
        print(f"❌ {message}")
        log_error(message)
        return {"status": "error", "message": message}


session = create_session()

with open("data.json", "r", encoding="utf-8") as fh:
    data = json.load(fh)

for index, item in enumerate(data, start=1):
    get_tmdb_details(item, session)
    if index % SAVE_EVERY_N_ITEMS == 0:
        save_data(data, OUTPUT_FILE)
        print(f"💾 Sauvegarde intermédiaire à l'entrée {index}")
    if REQUEST_DELAY_SECONDS > 0:
        time.sleep(REQUEST_DELAY_SECONDS)

save_data(data, OUTPUT_FILE)
print(f"\n✅ Terminé ! Fichier sauvegardé : {OUTPUT_FILE}")
