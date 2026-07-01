import json
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# Charger ton fichier JSON
with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    id = item["id"]
    url = f"https://www.themoviedb.org/movie/{id}"

    print(f"Traitement ID: {id}")

    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

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
        print("Description non trouvée")

# Sauvegarder dans un nouveau fichier
with open("data_updated.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Terminé ! Fichier sauvegardé : data_updated.json")