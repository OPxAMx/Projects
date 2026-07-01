import json
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# Charger ton fichier JSON
with open("tv_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    id = item["id"]
    type_media = item.get("type", "").lower()

    # Sélection automatique du bon chemin
    if type_media == "film":
        url = f"https://www.themoviedb.org/movie/{id}"
    elif type_media == "series":
        url = f"https://www.themoviedb.org/tv/{id}"
    else:
        print(f"⚠️ Type inconnu pour ID {id}, type='{type_media}' → ignoré")
        continue

    print(f"\n🔎 Traitement ID: {id} ({type_media}) → {url}")

    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # ---------------------------
    # 4) EXTRACTION TAGS (genres)
    # ---------------------------
    tags = []
    genres_block = soup.find("span", class_="genres")

    if genres_block:
        for g in genres_block.find_all("a"):
            tag = g.text.strip()
            if tag:
                tags.append(tag)
        print(f"✔ Tags : {tags}")
    else:
        print("❌ Aucun tag trouvé")

    item["tags"] = tags

# Sauvegarde
with open("tv_data_updated.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\n✅ Terminé ! Fichier sauvegardé : tv_data_updated.json")
