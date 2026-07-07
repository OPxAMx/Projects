import json
import time
import requests

REQUEST_DELAY_SECONDS = 0.5
SAVE_EVERY_N_ITEMS = 20

def fetch_logos(tmdb_id):
    # Priorité : FR → EN → NULL
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


# ============================
# 🔥 PROCESS DATA.JSON
# ============================

with open("data.json", "r", encoding="utf-8") as f:
    items = json.load(f)

output = []
processed_count = 0

for item in items:
    tmdb_id = item.get("tmdb_id")

    if tmdb_id:
        print(f"Fetching logos for TMDB ID: {tmdb_id}...")
        logos = fetch_logos(tmdb_id)
        item["logos"] = logos
    else:
        item["logos"] = []

    output.append(item)
    processed_count += 1

    # Delay anti-429
    time.sleep(REQUEST_DELAY_SECONDS)

    # Sauvegarde périodique
    if processed_count % SAVE_EVERY_N_ITEMS == 0:
        with open("output.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"✔️ Sauvegarde intermédiaire après {processed_count} items")


# ============================
# 💾 SAVE FINAL OUTPUT.JSON
# ============================

with open("output.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("✔️ Fichier output.json généré avec succès !")