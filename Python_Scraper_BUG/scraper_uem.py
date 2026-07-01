import json
import time
import traceback
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator

# -----------------------------
# CONFIG
# -----------------------------
INPUT_FILE = "data.json"
OUTPUT_FILE = "sampleContent.ts"   # <<< DEMANDÉ PAR ALAIN
LOG_SUCCESS = "success.log"
LOG_ERROR = "errors.log"

TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0"   # <<< METS TA CLÉ TMDB
TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"

THREADS = 10
REQUEST_TIMEOUT = 10
RETRY_COUNT = 3
CHECKPOINT_EVERY = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# -----------------------------
# LOGGING
# -----------------------------
def log_success(msg):
    with open(LOG_SUCCESS, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def log_error(msg):
    with open(LOG_ERROR, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# -----------------------------
# HTTP AVEC RETRIES
# -----------------------------
def get_json(url, params=None):
    if params is None:
        params = {}
    params["api_key"] = TMDB_API_KEY

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            log_error(f"[HTTP {response.status_code}] {url}")
        except Exception as e:
            log_error(f"[Réseau] Tentative {attempt}/{RETRY_COUNT} : {e}")
        time.sleep(1)

    return None

# -----------------------------
# TRADUCTION
# -----------------------------
def translate_to_fr(text):
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target="fr").translate(text)
    except:
        return text

# -----------------------------
# BUILD UEM ITEM
# -----------------------------
def build_uem_item(id, type_media, details, credits):
    api_type = "movie" if type_media == "movie" else "tv"

    title = details.get("title") or details.get("name") or ""
    original_title = details.get("original_title") or details.get("original_name") or title

    date_str = details.get("release_date") or details.get("first_air_date") or ""
    year = date_str[:4] if date_str else None

    genres = [g["name"] for g in details.get("genres", [])]

    runtime = details.get("runtime")
    if not runtime:
        ep_rt = details.get("episode_run_time") or []
        runtime = ep_rt[0] if ep_rt else None

    vote_average = details.get("vote_average")

    poster_path = details.get("poster_path")
    backdrop_path = details.get("backdrop_path")
    poster = f"{TMDB_IMG_BASE}/w500{poster_path}" if poster_path else None
    backdrop = f"{TMDB_IMG_BASE}/w780{backdrop_path}" if backdrop_path else None

    cast = []
    if credits and "cast" in credits:
        cast = [c["name"] for c in credits["cast"][:10]]

    creators = []
    if api_type == "tv":
        creators = [c["name"] for c in details.get("created_by", [])]
    else:
        if credits and "crew" in credits:
            directors = [c["name"] for c in credits["crew"] if c.get("job") == "Director"]
            creators = directors[:5]

    seasons = details.get("number_of_seasons") if api_type == "tv" else None
    episodes = details.get("number_of_episodes") if api_type == "tv" else None

    overview_en = details.get("overview") or ""
    overview_fr = translate_to_fr(overview_en)

    tmdb_url = f"https://www.themoviedb.org/{type_media}/{id}"

    return {
        "id": id,
        "type": type_media,
        "title": title,
        "original_title": original_title,
        "year": year,
        "tmdb_id": id,
        "tmdb_url": tmdb_url,
        "description": overview_fr,
        "overview_en": overview_en,
        "poster": poster,
        "backdrop": backdrop,
        "genres": genres,
        "runtime": runtime,
        "vote_average": vote_average,
        "seasons": seasons,
        "episodes": episodes,
        "cast": cast,
        "creators": creators,
    }

# -----------------------------
# TRAITEMENT D’UN ITEM
# -----------------------------
def process_item(item):
    try:
        id = item["id"]
        type_media = item.get("type")

        if type_media not in ["movie", "serie"]:
            log_error(f"[ID {id}] Type invalide (movie/serie)")
            return None

        api_type = "movie" if type_media == "movie" else "tv"

        details = get_json(f"{TMDB_API_BASE}/{api_type}/{id}", params={"language": "en-US"})
        if not details:
            log_error(f"[ID {id}] Détails introuvables")
            return None

        credits = get_json(f"{TMDB_API_BASE}/{api_type}/{id}/credits", params={"language": "en-US"}) or {}

        uem_item = build_uem_item(id, type_media, details, credits)
        log_success(f"[OK] {type_media.upper()} {id} - {uem_item['title']}")
        return uem_item

    except Exception as e:
        log_error(f"[CRASH ID {item.get('id')}] {e}\n{traceback.format_exc()}")
        return None

# -----------------------------
# EXPORT TYPESCRIPT
# -----------------------------
def export_typescript(uem_data):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("export const sampleContent = ")
        json.dump(uem_data, f, ensure_ascii=False, indent=2)
        f.write(";\n")

# -----------------------------
# MAIN MULTITHREAD
# -----------------------------
def main():
    print("🚀 Scraper UEM (API TMDB) → sampleContent.ts")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    uem_data = []
    counter = 0

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {executor.submit(process_item, item): item for item in data}

        for future in as_completed(futures):
            result = future.result()
            if result:
                uem_data.append(result)

            counter += 1

            if counter % CHECKPOINT_EVERY == 0:
                export_typescript(uem_data)
                print(f"💾 Checkpoint ({counter}/{len(data)})")

    export_typescript(uem_data)

    print("🎉 Terminé !")
    print("📄 Export TS :", OUTPUT_FILE)

if __name__ == "__main__":
    main()
