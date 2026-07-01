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
OUTPUT_FILE = "sampleContent.ts"
LOG_SUCCESS = "success.log"
LOG_ERROR = "errors.log"

TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5NDAwODY3YWVmNGU1OWZhM2IyMjUxNWEzYmE0MzA4YiIsIm5iZiI6MTc3NjI4NDk3OS4zNjMwMDAyLCJzdWIiOiI2OWRmZjUzMzQxMzA0YTM0ZGQzOTQ4NTYiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.6bfDm-Rdmk7K5-teBKkZTKmfBX-8WTN2IvZlr2OxAR0"
TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"

THREADS = 10
REQUEST_TIMEOUT = 10
RETRY_COUNT = 3
CHECKPOINT_EVERY = 30

HEADERS = {"User-Agent": "Mozilla/5.0"}

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
def build_uem_item(id, type_media, details, credits, embed):
    api_type = "movie" if type_media == "movie" else "tv"

    title = details.get("title") or details.get("name") or ""
    overview_en = details.get("overview") or ""
    overview_fr = translate_to_fr(overview_en)

    genres = [g["name"] for g in details.get("genres", [])]

    poster_path = details.get("poster_path")
    thumbnail = f"{TMDB_IMG_BASE}/w500{poster_path}" if poster_path else ""

    runtime = details.get("runtime")
    if not runtime:
        ep_rt = details.get("episode_run_time") or []
        runtime = ep_rt[0] if ep_rt else ""

    # Auteur
    author = ""
    if api_type == "tv":
        creators = details.get("created_by", [])
        if creators:
            author = creators[0]["name"]
    else:
        crew = credits.get("crew", [])
        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        if directors:
            author = directors[0]

    return {
        "id": str(id),
        "type": type_media,
        "title": title,
        "description": overview_fr,
        "tags": genres,
        "thumbnail": thumbnail,
        "embed": embed,  # <<< REPRISE DIRECTE DE data.json
        "meta": {
            "duration": str(runtime),
            "author": author,
            "date_added": "",
            "source": "tmdb"
        }
    }

# -----------------------------
# TRAITEMENT D’UN ITEM
# -----------------------------
def process_item(item):
    try:
        id = item["id"]
        type_media = item.get("type")
        embed = item.get("embed", {})  # <<< EMBED REPRIS TEL QUEL

        if type_media not in ["movie", "serie"]:
            log_error(f"[ID {id}] Type invalide (movie/serie)")
            return None

        api_type = "movie" if type_media == "movie" else "tv"

        details = get_json(f"{TMDB_API_BASE}/{api_type}/{id}", params={"language": "en-US"})
        if not details:
            log_error(f"[ID {id}] Détails introuvables")
            return None

        credits = get_json(f"{TMDB_API_BASE}/{api_type}/{id}/credits", params={"language": "en-US"}) or {}

        uem_item = build_uem_item(id, type_media, details, credits, embed)
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
    print("🚀 Scraper UEM → sampleContent.ts")

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
