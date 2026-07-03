"""
Script tout-en-un : lit votre fichier JSON détaillé, va chercher le trailer
YouTube sur TMDB pour chaque entrée (via tmdb_id + type), et réécrit le JSON
avec un champ "url_trailer" ajouté à chaque objet.

Pas besoin de fichier .txt ni de .csv intermédiaire : tout se fait
directement à partir de votre JSON existant.

Installation :
    pip install aiohttp

Utilisation :
    export TMDB_BEARER_TOKEN="votre_token"
    python add_trailers_to_json.py --data ma_base.json --output ma_base_updated.json

Le script détecte automatiquement movie vs série à partir du champ "type"
de chaque entrée (adapté à votre structure : "type": "series" ou "movie").
Si votre champ s'appelle différemment, ajustez TYPE_FIELD / TYPE_MOVIE_VALUES
/ TYPE_TV_VALUES ci-dessous.
"""

import os
import json
import argparse
import asyncio
import aiohttp

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

TMDB_BEARER_TOKEN = os.environ.get("TMDB_BEARER_TOKEN", "COLLEZ_VOTRE_TOKEN_ICI")

LANGUAGE = "en-US"
CONCURRENCY = 20
MAX_RETRIES = 5

# Nom du champ dans votre JSON qui indique id et type
ID_FIELD = "tmdb_id"          # fallback sur "id" si absent
TYPE_FIELD = "type"           # champ qui contient "movie" / "series" / etc.

# Valeurs possibles pour chaque type dans votre JSON (adaptez si besoin)
TYPE_MOVIE_VALUES = {"movie", "film"}
TYPE_TV_VALUES = {"series", "tv", "show"}

# ---------------------------------------------------------------------
# LOGIQUE TMDB
# ---------------------------------------------------------------------

def pick_best_trailer(results):
    if not results:
        return None
    youtube_videos = [v for v in results if v.get("site") == "YouTube"]
    if not youtube_videos:
        return None
    for v in youtube_videos:
        if v.get("type") == "Trailer" and v.get("official"):
            return v
    for v in youtube_videos:
        if v.get("type") == "Trailer":
            return v
    return youtube_videos[0]


def resolve_media_type(entry):
    raw = str(entry.get(TYPE_FIELD, "")).strip().lower()
    if raw in TYPE_MOVIE_VALUES:
        return "movie"
    if raw in TYPE_TV_VALUES:
        return "tv"
    return None  # type inconnu, on skip


async def fetch_trailer_url(session, tmdb_id, media_type, semaphore):
    endpoint = "movie" if media_type == "movie" else "tv"
    url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/videos"
    params = {"language": LANGUAGE}

    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        best = pick_best_trailer(data.get("results", []))
                        if best:
                            return f"https://www.youtube.com/watch?v={best.get('key')}"
                        return ""

                    elif resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after else (2 ** attempt) * 0.5
                        await asyncio.sleep(wait)
                        continue

                    elif resp.status == 404:
                        return ""

                    else:
                        if attempt == MAX_RETRIES:
                            return ""
                        await asyncio.sleep((2 ** attempt) * 0.5)

            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == MAX_RETRIES:
                    return ""
                await asyncio.sleep((2 ** attempt) * 0.5)

    return ""


async def process_entry(session, entry, semaphore, stats):
    tmdb_id = entry.get(ID_FIELD) or entry.get("id")
    media_type = resolve_media_type(entry)

    if not tmdb_id or media_type is None:
        entry.setdefault("url_trailer", "")
        stats["skipped"] += 1
        return

    url_trailer = await fetch_trailer_url(session, tmdb_id, media_type, semaphore)
    entry["url_trailer"] = url_trailer

    if url_trailer:
        stats["found"] += 1
    else:
        stats["not_found"] += 1


async def run(data, token):
    semaphore = asyncio.Semaphore(CONCURRENCY)
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    stats = {"found": 0, "not_found": 0, "skipped": 0}
    total = len(data)
    completed = 0

    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [asyncio.create_task(process_entry(session, entry, semaphore, stats)) for entry in data]

        for coro in asyncio.as_completed(tasks):
            await coro
            completed += 1
            if completed % 50 == 0 or completed == total:
                print(f"  {completed}/{total} traités...")

    return stats


def parse_args():
    parser = argparse.ArgumentParser(description="Ajoute url_trailer directement dans un JSON, sans CSV intermédiaire.")
    parser.add_argument("--data", required=True, help="Chemin du fichier JSON détaillé (tableau d'objets).")
    parser.add_argument("--output", required=True, help="Chemin du fichier JSON de sortie.")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"Requêtes simultanées (défaut {CONCURRENCY}).")
    return parser.parse_args()


def main():
    if not TMDB_BEARER_TOKEN or TMDB_BEARER_TOKEN == "COLLEZ_VOTRE_TOKEN_ICI":
        raise SystemExit("❌ Veuillez définir votre token TMDB via la variable d'environnement TMDB_BEARER_TOKEN.")

    args = parse_args()

    global CONCURRENCY
    CONCURRENCY = args.concurrency

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise SystemExit("❌ Le JSON doit être un tableau (liste) d'objets.")

    print(f"Traitement de {len(data)} entrées avec {CONCURRENCY} requêtes simultanées...")
    stats = asyncio.run(run(data, TMDB_BEARER_TOKEN))

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Terminé.")
    print(f"   Trailers trouvés     : {stats['found']}")
    print(f"   Trailers non trouvés : {stats['not_found']}")
    print(f"   Entrées ignorées (type/id manquant ou inconnu) : {stats['skipped']}")
    print(f"   Résultat écrit dans : {args.output}")


if __name__ == "__main__":
    main()