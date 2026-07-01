import json
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# Charger ton fichier JSON
with open("movie_data.json", "r", encoding="utf-8") as f:
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
    # 1) EXTRACTION DESCRIPTION
    # ---------------------------
    description = soup.find("div", class_="overview")

    if description:
        texte = description.text.strip()
        try:
            traduction = GoogleTranslator(source='auto', target='fr').translate(texte)
            item["description"] = traduction
        except:
            print("Erreur traduction")
            item["description"] = texte
    else:
        print("❌ Description non trouvée")
        item["description"] = ""

    # ---------------------------
    # 2) EXTRACTION TITLE
    # ---------------------------
    title_tag = soup.find("h2", class_="title")

    if title_tag:
        # parfois <h2 class="title"><a>TEXT</a></h2>
        title = title_tag.text.strip()
        item["title"] = title
        print(f"✔ Titre : {title}")
    else:
        print("❌ Titre non trouvé")
        item["title"] = ""

    # ---------------------------
    # 3) EXTRACTION THUMBNAIL
    # ---------------------------
    poster = soup.find("img", class_="poster")

    if poster:
        # TMDB utilise parfois src ou data-src
        thumbnail = poster.get("data-src") or poster.get("src")
        item["thumbnail"] = thumbnail
        print(f"✔ Thumbnail : {thumbnail}")
    else:
        print("❌ Thumbnail non trouvé")
        item["thumbnail"] = ""

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

    # ---------------------------
    # EXTRACTION TITLE (alt du poster + fallback)
    # ---------------------------
    title = ""

    # 1) Essayer via le alt du poster
    poster = soup.find("img", class_="poster")
    if poster:
        title_alt = poster.get("alt", "").strip()
        if title_alt and title_alt.lower() not in ["poster", "image"]:
            title = title_alt

    # 2) Fallback : h2.title
    if not title:
        title_tag = soup.find("h2", class_="title")
        if title_tag:
            title = title_tag.text.strip()

    item["title"] = title
    print(f"✔ Titre : {title}")

# Sauvegarde
with open("movie_data_updated.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\n✅ Terminé ! Fichier sauvegardé : movie_data_updated.json")
