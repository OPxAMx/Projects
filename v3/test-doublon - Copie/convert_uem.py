import json
import requests
import os

API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0"
INPUT_FILE = "input_uem.json"
OUTPUT_FILE = "output_uem.json"

TMDB_VIDEO_URL = "https://api.themoviedb.org/3/movie/{id}/videos?api_key={API_KEY}"

def get_tmdb_trailer(tmdb_id):
    """Retourne l'URL YouTube du trailer officiel TMDB."""
    url = TMDB_VIDEO_URL.format(id=tmdb_id, key=API_KEY)
    response = requests.get(url)

    if response.status_code != 200:
        print(f"[ERREUR TMDB] Impossible de récupérer les vidéos pour ID {tmdb_id}")
        return ""

    data = response.json()
    videos = data.get("results", [])

    # Priorité : Trailer officiel YouTube
    for v in videos:
        if v.get("site") == "YouTube" and v.get("type") == "Trailer":
            return f"https://www.youtube.com/embed/{v.get('key')}"

    # Sinon : n'importe quelle vidéo YouTube
    for v in videos:
        if v.get("site") == "YouTube":
            return f"https://www.youtube.com/embed/{v.get('key')}"

    return ""


def process_uem_list(input_path, output_path):
    """Charge une LISTE UEM, ajoute videos à chaque film, sauvegarde."""

    if not os.path.exists(input_path):
        print(f"[ERREUR] Le fichier {input_path} n'existe pas.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        uem_list = json.load(f)

    if not isinstance(uem_list, list):
        print("[ERREUR] Le fichier JSON doit contenir une LISTE de films.")
        return

    for item in uem_list:
        tmdb_id = item.get("tmdb_id")
        title = item.get("title", "Sans titre")

        if not tmdb_id:
            print(f"[AVERTISSEMENT] tmdb_id manquant pour {title}, skip.")
            item["videos"] = ""
            continue

        trailer_url = get_tmdb_trailer(tmdb_id)
        item["videos"] = trailer_url

        print(f"[OK] {title} → {trailer_url}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(uem_list, f, indent=2, ensure_ascii=False)

    print(f"\nFichier mis à jour : {output_path}")


# Exécution
process_uem_list(INPUT_FILE, OUTPUT_FILE)
