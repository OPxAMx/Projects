import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm  # pip install tqdm

API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0"  # ⚠️ Remplace par ta clé TMDB

REQUEST_DELAY_SECONDS = 0.5
SAVE_EVERY_N_ITEMS = 20
MAX_THREADS = 10  # Multithreading x10

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


def process_item(item):
    tmdb_id = item.get("tmdb_id")
    if tmdb_id:
        logos = fetch_logos(tmdb_id)
        item["logos"] = logos
        return item, tmdb_id, logos
    else:
        item["logos"] = []
        return item, None, []


# ============================
# 🔥 LOAD DATA.JSON
# ============================

with open("data.json", "r", encoding="utf-8") as f:
    items = json.load(f)

output = []
processed_count = 0

# ============================
# 🚀 MULTITHREAD PROCESSING
# ============================

print("\n🚀 Traitement multithread en cours...\n")

with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
    futures = {executor.submit(process_item, item): item for item in items}

    # Barre de progression
    for future in tqdm(as_completed(futures), total=len(items), desc="Progression"):
        item, tmdb_id, logos = future.result()

        output.append(item)
        processed_count += 1

        # Aperçu live
        if tmdb_id:
            print(f"✔️ {tmdb_id} → {len(logos)} logo(s) trouvé(s)")

        # Autosave
        if processed_count % SAVE_EVERY_N_ITEMS == 0:
            with open("output.json", "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            print(f"💾 Sauvegarde intermédiaire ({processed_count}/{len(items)})")

        # Anti-429
        time.sleep(REQUEST_DELAY_SECONDS)

# ============================
# 💾 SAVE FINAL OUTPUT.JSON
# ============================

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\n🎉 Terminé ! Fichier output.json généré avec succès.\n")
