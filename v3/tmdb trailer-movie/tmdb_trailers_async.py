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
import sys
import argparse
import asyncio
import aiohttp

# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

TMDB_BEARER_TOKEN = os.environ.get("TMDB_BEARER_TOKEN", "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0")

# Ces valeurs par défaut ne servent que si vous lancez le script SANS
# argument. Le moyen recommandé pour 30 000 ids est d'utiliser :
#   python tmdb_trailers_async.py --input mes_ids.txt
#   python tmdb_trailers_async.py --input mes_ids.csv
#   python tmdb_trailers_async.py --input mes_ids.csv --mixed
TMDB_IDS = [36657, 550, 27205]
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
            raw = f.read()
        # Gère : un id par ligne, OU des ids séparés par des virgules,
        # avec ou sans guillemets, avec espaces superflus.
        # Ex: 123\n456          ex: "123","456","789"          ex: 123, 456, 789
        for token in raw.replace("\n", ",").split(","):
            token = token.strip().strip('"').strip("'").strip()
            if token:
                try:
                    ids.append(int(token))
                except ValueError:
                    print(f"  ⚠️  Valeur ignorée (non numérique) : '{token}'")
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extrait les clés YouTube des trailers TMDB pour une liste de films/séries."
    )
    parser.add_argument(
        "--input", "-i",
        help="Chemin vers le fichier d'ids (.txt = un id par ligne, .csv = colonne 'tmdb_id'). "
             "Si absent, utilise la liste TMDB_IDS codée dans le script.",
    )
    parser.add_argument(
        "--mixed", action="store_true",
        help="Le CSV contient une colonne 'media_type' (movie/tv) en plus de 'tmdb_id'. "
             "Nécessite --input pointant vers un CSV.",
    )
    parser.add_argument(
        "--media-type", choices=["movie", "tv"], default=None,
        help="Force le type sans passer par la confirmation interactive.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=CONCURRENCY,
        help=f"Nombre de requêtes simultanées (défaut : {CONCURRENCY}).",
    )
    parser.add_argument(
        "--output", "-o", default=OUTPUT_CSV,
        help=f"Fichier CSV de sortie (défaut : {OUTPUT_CSV}).",
    )
    return parser.parse_args()


def main():
    if not TMDB_BEARER_TOKEN or TMDB_BEARER_TOKEN == "COLLEZ_VOTRE_TOKEN_ICI":
        raise SystemExit(
            "❌ Veuillez définir votre token TMDB via la variable d'environnement TMDB_BEARER_TOKEN."
        )

    args = parse_args()

    global CONCURRENCY
    CONCURRENCY = args.concurrency
    output_path = args.output

    # ---- Construction de la liste (tmdb_id, media_type) ----
    if args.input:
        if args.mixed:
            items = load_ids_from_file(args.input, mixed=True)
            print(f"Liste mixte chargée depuis '{args.input}' ({len(items)} ids, media_type par ligne).")
        else:
            raw_ids = load_ids_from_file(args.input, mixed=False)
            print(f"{len(raw_ids)} ids chargés depuis '{args.input}'.")
            media_type = args.media_type or confirm_media_type(len(raw_ids))
            items = [(i, media_type) for i in raw_ids]
    else:
        # Pas de --input : on utilise la liste codée en dur TMDB_IDS
        if TMDB_IDS and isinstance(TMDB_IDS[0], (tuple, list)):
            items = [(int(i), mt) for i, mt in TMDB_IDS]
            print(f"Liste mixte détectée dans TMDB_IDS ({len(items)} ids).")
        else:
            media_type = args.media_type or confirm_media_type(len(TMDB_IDS), default=DEFAULT_MEDIA_TYPE)
            items = [(int(i), media_type) for i in TMDB_IDS]

    print(f"\nTraitement de {len(items)} ids avec {CONCURRENCY} requêtes simultanées...")
    results = asyncio.run(run(items, TMDB_BEARER_TOKEN))
    write_csv(results, output_path)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n✅ Terminé. {ok}/{len(results)} trailers trouvés. Résultats dans '{output_path}'.")


if __name__ == "__main__":
    main()
