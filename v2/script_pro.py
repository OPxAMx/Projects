import json
import requests
from deep_translator import GoogleTranslator

API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0"

with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    id = item["id"]

    url = f"https://api.themoviedb.org/3/movie/{id}?api_key={API_KEY}&language=en-US"

    print(f"Traitement ID: {id}")

    response = requests.get(url)
    result = response.json()

    # 🎬 Description
    overview = result.get("overview", "")
    if overview:
        try:
            traduction = GoogleTranslator(source='auto', target='fr').translate(overview)
            item["description"] = traduction
        except:
            item["description"] = overview

    # 🏷️ Tags (genres)
    genres = result.get("genres", [])
    item["tags"] = [g["name"] for g in genres]

    # ⏱️ Durée
    runtime = result.get("episode_run_time", [])
    if runtime:
        item["meta"]["duration"] = f"{runtime[0]} min"

    # ✍️ Auteur (créateur)
    creators = result.get("created_by", [])
    if creators:
        item["meta"]["author"] = creators[0]["name"]

# 💾 Sauvegarde
with open("data_updated.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Terminé !")