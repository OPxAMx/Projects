import json
import os
import re
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TMDB_API_KEY = os.getenv(
    "TMDB_API_KEY",
    "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0",
)
REQUEST_DELAY_SECONDS = 1.5
SAVE_EVERY_N_ITEMS = 20
OUTPUT_FILE = "data_updated.json"
LOG_FILE = "tmdb_scraper.log"
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 2.0
TAG_MODE = "append"  # IMPORTANT : conserver tags existants


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
    retries = Retry(total=0)
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


def add_tag(item, tag):
    """Ajoute un tag sans jamais écraser les tags existants."""
    if "tags" not in item:
        item["tags"] = []
    if tag and tag not in item["tags"]:
        item["tags"].append(tag)


def extract_iframe_src(iframe: str) -> str:
    if not iframe:
        return ""
    match = re.search(r'src=["\']([^"\']+)["\']', iframe)
    return match.group(1) if match else ""


def ensure_embed_url(item, provider_name: str) -> None:
    if "embed" not in item:
        item["embed"] = {}

    embed = item["embed"]
    provider_lower = (provider_name or "").lower()
    existing_url = (embed.get("url") or "").strip()
    iframe_html = (embed.get("iframe") or "").strip()

    if not existing_url and iframe_html:
        existing_url = extract_iframe_src(iframe_html)

    if not existing_url and "vidking" not in provider_lower:
        return

    item_id = str(item.get("id", "")).strip()
    if not item_id:
        return

    type_media = str(item.get("type", "")).strip().lower()
    if type_media in {"series", "tv", "show", "serie"}:
        media_path = "tv"
    elif type_media in {"film", "movie"}:
        media_path = "movie"
    else:
        media_path = "movie"

    if "vidking" in provider_lower or "vidking" in existing_url.lower() or "vidking" in iframe_html.lower():
        if not existing_url:
            existing_url = f"https://www.vidking.net/embed/{media_path}/"

        if not existing_url.endswith("/"):
            existing_url = existing_url.rstrip("/") + "/"

        if not existing_url.rstrip("/").endswith(item_id):
            existing_url = existing_url.rstrip("/") + f"/{item_id}"

        embed["url"] = existing_url
        embed["iframe"] = f'<iframe src="{existing_url}" allowfullscreen></iframe>'


def build_video_iframe(video: dict[str, Any]) -> str:
    site = str(video.get("site", "")).strip().lower()
    key = str(video.get("key", "")).strip()
    if site == "youtube" and key:
        return (
            f'<iframe width="560" height="315" src="https://www.youtube.com/embed/{key}" '
            f'title="YouTube video player" frameborder="0" '
            f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
            f'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>'
        )
    return ""


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

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(endpoint, timeout=20, **request_kwargs)
            response.raise_for_status()
            data = response.json()

            # --- TITRES & DESCRIPTION ---
            item["title"] = data.get("title") or data.get("name") or item.get("title", "")
            item["original_title"] = data.get("original_title") or data.get("original_name") or item.get("title", "")
            item["description"] = data.get("overview") or ""
            item["description_fr"] = translate_text(item["description"]) if item.get("description") else ""
            if item.get("description_fr"):
                item["description"] = item["description_fr"]

            # --- IMAGES ---
            item["thumbnail"] = build_image_url(data.get("poster_path"))
            item["backdrop"] = build_image_url(data.get("backdrop_path"))

            # --- DATE DE SORTIE ---
            release_date = data.get("release_date") or data.get("first_air_date") or ""
            item["release_date"] = release_date

            # EXTRACTION ANNÉE
            if release_date and len(release_date) >= 4:
                year = release_date[:4]
                add_tag(item, year)

            # --- MÉTA ---
            item["runtime"] = data.get("runtime") or data.get("episode_run_time") or ""
            item["vote_average"] = data.get("vote_average")
            item["popularity"] = data.get("popularity")
            item["status"] = data.get("status") or ""
            item["homepage"] = data.get("homepage") or ""
            item["language"] = data.get("original_language") or ""

            # --- GENRES TMDB (NE PAS ÉCRASER TES TAGS) ---
            genres = [genre.get("name", "") for genre in data.get("genres", []) if genre.get("name")]

            if TAG_MODE == "append":
                for g in genres:
                    add_tag(item, g)

            item["production_companies"] = [
                company.get("name", "") for company in data.get("production_companies", []) if company.get("name")
            ]

            item["source"] = "TMDb API"
            item["tmdb_id"] = item_id

            # --- CRÉDITS ---
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

            # --- VIDEOS TMDB ---
            videos_endpoint = f"https://api.themoviedb.org/3/{'movie' if type_media in {'film', 'movie'} else 'tv'}/{item_id}/videos"
            try:
                videos_response = session.get(videos_endpoint, timeout=20, **request_kwargs)
                if videos_response.ok:
                    videos_data = videos_response.json()
                    videos = videos_data.get("results", []) or []
                    for video in videos:
                        if isinstance(video, dict):
                            video["url_trailer"] = build_video_iframe(video)
                    item["videos"] = videos
                else:
                    item["videos"] = []
            except Exception as exc:
                print(f"⚠️ Erreur videos pour ID {item_id} : {exc}")
                item["videos"] = []

            # --- PROVIDERS STREAMING ---
            providers_endpoint = f"{endpoint}/watch/providers"
            try:
                providers_response = session.get(providers_endpoint, timeout=20, **request_kwargs)
                if providers_response.ok:
                    providers_data = providers_response.json()

                    country_data = providers_data.get("results", {}).get("CA", {})
                    flatrate = country_data.get("flatrate", [])
                    provider_names = [p.get("provider_name") for p in flatrate if p.get("provider_name")]

                    main_provider = provider_names[0] if provider_names else ""

                    # embed.provider
                    if "embed" not in item:
                        item["embed"] = {}

                    item["embed"]["provider"] = main_provider
                    ensure_embed_url(item, main_provider)

                    # Ajouter provider dans tags SANS ÉCRASER
                    add_tag(item, main_provider)

            except Exception as exc:
                print(f"⚠️ Erreur providers pour ID {item_id} : {exc}")

            print(f"✔ Titre : {item['title']}")
            print(f"✔ Provider : {item['embed'].get('provider', '')}")
            print(f"✔ Tags : {item['tags']}")
            return {"status": "ok"}

        except Exception as exc:
            print(f"❌ Erreur ID {item_id}: {exc}")
            log_error(str(exc))
            return {"status": "error", "message": str(exc)}


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