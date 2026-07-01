import os
import re
from typing import Any
from urllib.parse import quote

import requests


def scrape_metadata_from_url(url: str) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        html = response.text
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        page_title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

        meta_tags: dict[str, str] = {}
        for pattern in [
            r"<meta[^>]+name=['\"]([^'\"]+)['\"][^>]+content=['\"]([^'\"]*)['\"]",
            r"<meta[^>]+property=['\"]([^'\"]+)['\"][^>]+content=['\"]([^'\"]*)['\"]",
        ]:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                meta_tags[match.group(1).lower()] = re.sub(r"\s+", " ", match.group(2)).strip()

        description = meta_tags.get("description") or meta_tags.get("og:description") or meta_tags.get("twitter:description") or ""
        image = meta_tags.get("og:image") or meta_tags.get("twitter:image") or meta_tags.get("image") or ""
        title = meta_tags.get("og:title") or meta_tags.get("twitter:title") or page_title
        return {
            "title": title,
            "description": description,
            "image": image,
            "source": "URL",
            "status": "ok",
        }
    except Exception:
        return {"status": "error"}


def scrape_metadata_for_record(record: dict[str, Any], api_key: str | None = None, provider: str = "omdb", mode: str = "auto") -> dict[str, Any]:
    title = str(record.get("title", "")).strip()
    if not title:
        return {}

    if not api_key:
        api_key = os.getenv("OMDB_API_KEY") or os.getenv("TMDB_API_KEY")

    for url_key in ("url", "link", "source_url", "href", "website"):
        url = str(record.get(url_key, "") or "").strip()
        if url and mode in {"auto", "url", "title_and_url"}:
            url_meta = scrape_metadata_from_url(url)
            if url_meta.get("status") == "ok":
                return {
                    "title": url_meta.get("title", title),
                    "description": url_meta.get("description", ""),
                    "image": url_meta.get("image", ""),
                    "source": "URL",
                    "status": "ok",
                }

    if provider == "omdb" and api_key and mode in {"auto", "title", "title_and_url"}:
        try:
            url = f"http://www.omdbapi.com/?t={quote(title)}&apikey={api_key}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("Response") == "True":
                return {
                    "duration": data.get("Runtime", ""),
                    "cast": data.get("Actors", ""),
                    "producer": data.get("Director", ""),
                    "year": data.get("Year", ""),
                    "source": "OMDb",
                    "status": "ok",
                }
        except Exception:
            return {"status": "error"}

    if provider == "tmdb" and api_key and mode in {"auto", "title", "title_and_url"}:
        try:
            media_type = "tv" if str(record.get("type", "")).lower() in {"serie", "series", "tv"} else "movie"
            url = f"https://api.themoviedb.org/3/search/{media_type}?query={quote(title)}&include_adult=false"
            response = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
            response.raise_for_status()
            data = response.json()
            results = data.get("results") or []
            if results:
                first = results[0]
                return {
                    "duration": first.get("runtime") or first.get("episode_run_time") or "",
                    "cast": "",
                    "producer": first.get("original_title") or first.get("name") or "",
                    "year": first.get("release_date") or first.get("first_air_date") or "",
                    "source": "TMDb",
                    "status": "ok",
                }
        except Exception:
            return {"status": "error"}

    return {"status": "missing_api_key"}


def enrich_records(records: list[dict[str, Any]], api_key: str | None = None, provider: str = "omdb", limit: int = 20, mode: str = "auto") -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for record in records[:limit]:
        updated = dict(record)
        meta = scrape_metadata_for_record(updated, api_key=api_key, provider=provider, mode=mode)
        if meta.get("status") == "ok":
            updated.setdefault("meta", {})
            updated["meta"].update(
                {
                    "duration": meta.get("duration", updated.get("meta", {}).get("duration", "")),
                    "cast": meta.get("cast", updated.get("meta", {}).get("cast", "")),
                    "producer": meta.get("producer", updated.get("meta", {}).get("producer", "")),
                    "year": meta.get("year", updated.get("meta", {}).get("year", "")),
                    "source": meta.get("source", updated.get("meta", {}).get("source", "")),
                }
            )
            if meta.get("description"):
                updated["description"] = meta["description"]
            if meta.get("image"):
                updated["image"] = meta["image"]
            if meta.get("title") and not updated.get("title"):
                updated["title"] = meta["title"]
        enriched.append(updated)
    return enriched
