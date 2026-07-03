"""
Script ASYNC pour extraire les clés YouTube des trailers depuis l'API TMDB.
Optimisé pour traiter des milliers de tmdb_id rapidement, avec :
    - requêtes concurrentes (asyncio + aiohttp)
    - limite de concurrence configurable
    - retry automatique en cas de 429 (rate limit) ou erreur réseau
    - barre de progression simple
    - support Films (movie) ET Séries (tv), avec confirmation avant de lancer
    - écriture des résultats au fur et à mesure (résistant aux interruptions)

Installation :
    pip install aiohttp

Utilisation :
    1. export TMDB_BEARER_TOKEN="votre_token"
    2. Deux options pour fournir vos ids :
       a) Liste homogène (tous movie OU tous tv) : mettez vos ids dans
          TMDB_IDS et le script vous demandera confirmation du type au
          lancement.
       b) Liste mixte (movie ET tv mélangés) : préparez un CSV avec deux
          colonnes 'tmdb_id' et 'media_type' (valeurs 'movie' ou 'tv'),
          et utilisez load_ids_from_file(path, mixed=True).
    3. python tmdb_trailers_async.py
"""

import os
import csv
import asyncio
import aiohttp

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

TMDB_BEARER_TOKEN = os.environ.get("TMDB_BEARER_TOKEN", "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0")

# Chargez vos ids depuis un fichier si vous en avez des milliers :
# TMDB_IDS = load_ids_from_file("mes_ids.txt")
TMDB_IDS = [36657, 550, 27205]

# Si votre liste est homogène (100% movie ou 100% tv), laissez ceci à None :
# le script vous demandera de confirmer le type au lancement.
# Vous pouvez aussi le forcer directement ici : "movie" ou "tv".
DEFAULT_MEDIA_TYPE = None

LANGUAGE = "en-US"
OUTPUT_CSV = "tmdb_trailers_output.csv"

# Nombre de requêtes simultanées. TMDB tolère généralement ~40-50 req/s
# sur la clé API v4. 20 concurrentes est un bon compromis sûr/rapide.
CONCURRENCY = 20

# Nombre de tentatives en cas d'erreur (429, timeout, erreur réseau)
MAX_RETRIES = 5

# ---------------------------------------------------------------------
# FONCTIONS
# ---------------------------------------------------------------------

def load_ids_from_file(path, mixed=False):
    """
    Charge une liste d'ids depuis un fichier.

    Si mixed=False (par défaut) :
        - fichier texte : un id par ligne
        - CSV : colonne 'tmdb_id'
        -> retourne une liste d'ints. Le media_type sera demandé/appliqué
           globalement au lancement.

    Si mixed=True :
        - CSV obligatoire, avec colonnes 'tmdb_id' ET 'media_type'
          (valeurs 'movie' ou 'tv')
        -> retourne une liste de tuples (tmdb_id, media_type)
    """
    if mixed:
        if not path.lower().endswith(".csv"):
            raise ValueError("mixed=True necessite un CSV avec colonnes 'tmdb_id' et 'media_type'.")
        items = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                media_type = row["media_type"].strip().lower()
                if media_type not in ("movie", "tv"):
                    raise ValueError(f"media_type invalide pour l'id {row['tmdb_id']}: '{media_type}'")
                items.append((int(row["tmdb_id"]), media_type))
        return items

    ids = []
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ids.append(int(row["tmdb_id"]))
    else:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ids.append(int(line))
    return ids


def confirm_media_type(id_count, default=None):
    """Demande confirmation a l'utilisateur : films ou series ? Bloque tant
    que l'utilisateur n'a pas repondu movie/tv."""
    if default in ("movie", "tv"):
        print(f"Type de media force via DEFAULT_MEDIA_TYPE = '{default}'.")
        answer = input(
            f"-> {id_count} ids seront traites comme des '{default}'. Confirmer ? [Y/n] "
        ).strip().lower()
        if answer in ("", "y", "yes", "o", "oui"):
            return default
        print("Annule par l'utilisateur. Relancez avec le bon parametre.")
        raise SystemExit(0)

    print(f"\nVous avez {id_count} ids a traiter.")
    while True:
        answer = input(
            "Est-ce une liste de FILMS ou de SERIES ? Tapez 'movie' ou 'tv' (ou 'q' pour annuler) : "
        ).strip().lower()
        if answer in ("movie", "film", "films", "m"):
            return "movie"
        if answer in ("tv", "serie", "series", "s"):
            return "tv"
        if answer in ("q", "quit", "annuler"):
            print("Annule par l'utilisateur.")
            raise SystemExit(0)
        print("Reponse non reconnue. Tapez 'movie', 'tv', ou 'q' pour annuler.")


def pick_best_trailer(results):
    """Choisit le meilleur trailer YouTube : officiel > trailer > n'importe quelle vidéo YouTube."""
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


async def fetch_videos(session, tmdb_id, media_type, semaphore):
    """Recupere les videos d'un film ou d'une serie, avec retry/backoff en cas de 429 ou erreur."""
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
                            return {
                                "tmdb_id": tmdb_id,
                                "media_type": media_type,
                                "youtube_key": best.get("key", ""),
                                "trailer_name": best.get("name", ""),
                                "official": best.get("official", ""),
                                "status": "ok",
                            }
                        else:
                            return {
                                "tmdb_id": tmdb_id,
                                "media_type": media_type,
                                "youtube_key": "",
                                "trailer_name": "",
                                "official": "",
                                "status": "aucun_trailer_trouve",
                            }

                    elif resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after else (2 ** attempt) * 0.5
                        await asyncio.sleep(wait)
                        continue

                    elif resp.status == 404:
                        return {
                            "tmdb_id": tmdb_id,
                            "media_type": media_type,
                            "youtube_key": "",
                            "trailer_name": "",
                            "official": "",
                            "status": "introuvable_verifier_media_type",
                        }

                    else:
                        if attempt == MAX_RETRIES:
                            return {
                                "tmdb_id": tmdb_id,
                                "media_type": media_type,
                                "youtube_key": "",
                                "trailer_name": "",
                                "official": "",
                                "status": f"erreur_{resp.status}",
                            }
                        await asyncio.sleep((2 ** attempt) * 0.5)

            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == MAX_RETRIES:
                    return {
                        "tmdb_id": tmdb_id,
                        "media_type": media_type,
                        "youtube_key": "",
                        "trailer_name": "",
                        "official": "",
                        "status": "erreur_reseau",
                    }
                await asyncio.sleep((2 ** attempt) * 0.5)

    return {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "youtube_key": "",
        "trailer_name": "",
        "official": "",
        "status": "echec_apres_retries",
    }


async def run(items, token):
    """items : liste de tuples (tmdb_id, media_type)"""
    semaphore = asyncio.Semaphore(CONCURRENCY)
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    results = []
    completed = 0
    total = len(items)

    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [
            asyncio.create_task(fetch_videos(session, tmdb_id, media_type, semaphore))
            for tmdb_id, media_type in items
        ]

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1
            if completed % 50 == 0 or completed == total:
                print(f"  {completed}/{total} traités...")

    return results


def write_csv(rows, path):
    # Trie par tmdb_id pour un résultat prévisible (as_completed ne garde pas l'ordre)
    rows_sorted = sorted(rows, key=lambda r: r["tmdb_id"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["tmdb_id", "media_type", "youtube_key", "trailer_name", "official", "status"]
        )
        writer.writeheader()
        writer.writerows(rows_sorted)


def main():
    if not TMDB_BEARER_TOKEN or TMDB_BEARER_TOKEN == "COLLEZ_VOTRE_TOKEN_ICI":
        raise SystemExit(
            "❌ Veuillez définir votre token TMDB via la variable d'environnement TMDB_BEARER_TOKEN."
        )

    # Détecte si TMDB_IDS contient déjà des tuples (tmdb_id, media_type),
    # cas d'une liste mixte chargée via load_ids_from_file(path, mixed=True)
    if TMDB_IDS and isinstance(TMDB_IDS[0], (tuple, list)):
        items = [(int(i), mt) for i, mt in TMDB_IDS]
        print(f"Liste mixte détectée ({len(items)} ids, media_type déjà spécifié par id).")
    else:
        # Liste homogène : on demande confirmation du type avant de lancer
        media_type = confirm_media_type(len(TMDB_IDS), default=DEFAULT_MEDIA_TYPE)
        items = [(int(i), media_type) for i in TMDB_IDS]

    print(f"\nTraitement de {len(items)} ids avec {CONCURRENCY} requêtes simultanées...")
    results = asyncio.run(run(items, TMDB_BEARER_TOKEN))
    write_csv(results, OUTPUT_CSV)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n✅ Terminé. {ok}/{len(results)} trailers trouvés. Résultats dans '{OUTPUT_CSV}'.")


if __name__ == "__main__":
    main()