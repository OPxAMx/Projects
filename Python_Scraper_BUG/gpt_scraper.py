import json
import time
import requests
from deep_translator import GoogleTranslator

# 🔐 TA CLÉ API (⚠️ pense à la régénérer après l’avoir partagée)
API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "accept": "application/json"
}

BASE_URL = "https://api.themoviedb.org/3"

# ---------------------------
# 🔎 Fonction API
# ---------------------------
def fetch_tmdb(endpoint):
    url = f"{BASE_URL}{endpoint}"

    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)

            if response.status_code == 429:
                print("⏳ Rate limit API → pause 3 sec")
                time.sleep(3)
                continue

            if response.status_code != 200:
                print(f"❌ API error {response.status_code}")
                return None

            return response.json()

        except Exception as e:
            print(f"❌ Erreur requête: {e}")
            time.sleep(2)

    return None


# ---------------------------
# 🌍 Traduction
# ---------------------------
def traduire(texte):
    if not texte:
        return ""

    try:
        return GoogleTranslator(source='auto', target='fr').translate(texte)
    except:
        return texte


# ---------------------------
# 📂 Charger JSON
# ---------------------------
with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)


# ---------------------------
# 🔁 Traitement principal
# ---------------------------
for item in data:
    id = item.get("id")
    type_media = item.get("type", "").lower()

    if not id:
        print("❌ ID manquant → skip")
        continue

    print(f"\n🔎 Traitement ID: {id} ({type_media})")

    # ---------------------------
    # 🎬 FILM
    # ---------------------------
    if type_media == "film":
        result = fetch_tmdb(f"/movie/{id}?language=en-US")

        if not result:
            continue

        if not item.get("title"):
            item["title"] = result.get("title")

        if not item.get("description"):
            item["description"] = traduire(result.get("overview"))

        if not item.get("thumbnail"):
            poster = result.get("poster_path")
            if poster:
                item["thumbnail"] = f"https://image.tmdb.org/t/p/w500{poster}"

        if not item.get("tags"):
            item["tags"] = [g["name"] for g in result.get("genres", [])]

    # ---------------------------
    # 📺 SERIES
    # ---------------------------
    elif type_media == "series":
        result = fetch_tmdb(f"/tv/{id}?language=en-US")

        if not result:
            continue

        if not item.get("title"):
            item["title"] = result.get("name")

        if not item.get("description"):
            item["description"] = traduire(result.get("overview"))

        if not item.get("thumbnail"):
            poster = result.get("poster_path")
            if poster:
                item["thumbnail"] = f"https://image.tmdb.org/t/p/w500{poster}"

        if not item.get("tags"):
            item["tags"] = [g["name"] for g in result.get("genres", [])]

    else:
        print("⚠️ Type inconnu → skip")
        continue

    # ⏱️ petit délai sécurité
    time.sleep(0.25)


# ---------------------------
# 💾 Sauvegarde
# ---------------------------
with open("data_updated.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\n✅ Terminé ! Fichier: data_updated.json")