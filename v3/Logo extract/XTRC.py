import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm  # pip install tqdm

API_KEY = "TON_API_KEY"  # ⚠️ Remplace par ta clé TMDB

REQUEST_DELAY_SECONDS = 0.5
SAVE_EVERY_N_ITEMS = 20
MAX_THREADS = 10  # Multithreading x10


# ============================================================
# 🔵 FETCH LOGOS
# ============================================================

def fetch_logos(tmdb_id):
    endpoints = [
        f"https://api.themoviedb.org/3/movie/{tmdb_id}/images?include_image_language=fr,en,null",
        f"https://api.themoviedb.org/3/tv/{tmdb_id}/images?include_image_language=fr,en,null",
        f"https://api.themoviedb.org/3/collection/{tmdb_id}/images?include_image_language=fr,en,null",
        f"https://api.themoviedb.org/3/company/{tmdb_id}/images?include_image_language=fr,en,null"
    ]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json"
    }

    for url in endpoints:
        try:
            r = requests.get(url, headers=headers)
        except Exception:
            continue

        if not r.ok:
            continue

        data = r.json()

        if "logos" in data and len(data["logos"]) > 0:
            return [
                "https://image.tmdb.org/t/p/original" + logo["file_path"]
                for logo in data["logos"]
            ]

    return []


# ============================================================
# 🔴 FETCH TRAILER KEY
# ============================================================

def fetch_trailer(tmdb_id):
    endpoints = [
        f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos",
        f"https://api.themoviedb.org/3/tv/{tmdb_id}/videos"
    ]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "accept": "application/json"
    }

    for url in endpoints:
        try:
            r = requests.get(url, headers=headers)
        except Exception:
            continue

        if not r.ok:
            continue

        data = r.json()

        if "results" not in data:
            continue

        # Trailer officiel YouTube
        for vid in data["results"]:
            if (
                vid.get("site") == "YouTube"
                and vid.get("type") == "Trailer"
                and vid.get("official") is True
                and vid.get("key")
            ):
                return [{
                    "name": vid.get("name", ""),
                    "key": vid.get("key"),
                    "site": "YouTube",
                    "size": vid.get("size", 1080),
                    "type": "Trailer",
                    "official": True
                }]

        # Trailer YouTube non officiel
        for vid in data["results"]:
            if vid.get("site") == "YouTube" and vid.get("key"):
                return [{
                    "name": vid.get("name", ""),
                    "key": vid.get("key"),
                    "site": "YouTube",
                    "size": vid.get("size", 1080),
                    "type": vid.get("type", "Trailer"),
                    "official": False
                }]

    return []


# ============================================================
# 🟣 PROCESS ITEM (selon mode choisi)
# ============================================================

def process_item(item, mode):
    tmdb_id = item.get("tmdb_id")

    logos = []
    videos = []

    if tmdb_id:
        if mode in (1, 3):
            logos = fetch_logos(tmdb_id)
            item["logos"] = logos

        if mode in (2, 3):
            videos = fetch_trailer(tmdb_id)
            item["videos"] = videos

        return item, tmdb_id, logos, videos

    else:
        if mode in (1, 3):
            item["logos"] = []
        if mode in (2, 3):
            item["videos"] = []

        return item, None, [], []


# ============================================================
# 🟢 MENU DE CHOIX
# ============================================================

print("\n=== CHOISIS LE TYPE D'EXTRACTION ===")
print("1 → Logos TMDB")
print("2 → Vidéos (Trailer YouTube)")
print("3 → Logos + Vidéos")
mode = int(input("\nTon choix : ").strip())

if mode not in (1, 2, 3):
    print("❌ Choix invalide.")
    exit()


# ============================================================
# 🔥 LOAD DATA.JSON
# ============================================================

with open("data.json", "r", encoding="utf-8") as f:
    items = json.load(f)

output = []
processed_count = 0

print("\n🚀 Traitement multithread en cours...\n")


# ============================================================
# 🚀 MULTITHREAD PROCESSING
# ============================================================

with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
    futures = {executor.submit(process_item, item, mode): item for item in items}

    for future in tqdm(as_completed(futures), total=len(items), desc="Progression"):
        item, tmdb_id, logos, videos = future.result()

        output.append(item)
        processed_count += 1

        # Aperçu live
        if tmdb_id:
            print(f"✔️ {tmdb_id} → {len(logos)} logo(s), {len(videos)} vidéo(s)")

        # Autosave
        if processed_count % SAVE_EVERY_N_ITEMS == 0:
            with open("output.json", "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            print(f"💾 Sauvegarde intermédiaire ({processed_count}/{len(items)})")

        # Anti-429
        time.sleep(REQUEST_DELAY_SECONDS)


# ============================================================
# 💾 SAVE FINAL OUTPUT.JSON
# ============================================================

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n🎉 Terminé ! Fichier output.json généré avec succès.\n")
