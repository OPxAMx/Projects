import json
import time
import random
import traceback
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from concurrent.futures import ThreadPoolExecutor, as_completed

# -----------------------------
# CONFIG
# -----------------------------
INPUT_FILE = "data.json"
OUTPUT_FILE = "data_updated.json"
LOG_SUCCESS = "success.log"
LOG_ERROR = "errors.log"

THREADS = 10
CHECKPOINT_EVERY = 30
REQUEST_TIMEOUT = 10
RETRY_COUNT = 3

# Proxies (exemple)
PROXIES = [
    "http://user:pass@proxy1:8000",
    "http://user:pass@proxy2:8000",
    "http://user:pass@proxy3:8000",
]

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
# HTTP REQUEST AVEC RETRIES + PROXY ROTATION
# -----------------------------
def fetch_url(url):
    for attempt in range(1, RETRY_COUNT + 1):
        proxy = {"http": random.choice(PROXIES), "https": random.choice(PROXIES)}

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                proxies=proxy,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                return response.text

            log_error(f"[HTTP {response.status_code}] {url}")

        except Exception as e:
            log_error(f"[Réseau] Tentative {attempt}/{RETRY_COUNT} : {e}")

        time.sleep(1)

    return None

# -----------------------------
# EXTRACTION DESCRIPTION TMDB
# -----------------------------
def extract_description(html):
    soup = BeautifulSoup(html, "html.parser")

    selectors = [
        "div.overview",
        "section.facts p",
        "div.text",
        "div[data-role='description']",
    ]

    for sel in selectors:
        block = soup.select_one(sel)
        if block and block.text.strip():
            return block.text.strip()

    return None

# -----------------------------
# TRADUCTION
# -----------------------------
def translate_text(text):
    try:
        return GoogleTranslator(source="auto", target="fr").translate(text)
    except:
        return text

# -----------------------------
# TRAITEMENT D’UN SEUL ITEM
# -----------------------------
def process_item(item):
    try:
        id = item["id"]
        type_media = item.get("type", "auto")

        # Détection automatique film/série
        if type_media == "auto":
            type_media = "movie" if len(str(id)) < 7 else "tv"

        url = f"https://www.themoviedb.org/{type_media}/{id}"

        html = fetch_url(url)
        if not html:
            log_error(f"[ID {id}] Page introuvable")
            return None

        desc = extract_description(html)
        if not desc:
            log_error(f"[ID {id}] Description introuvable")
            return None

        traduction = translate_text(desc)
        item["description"] = traduction

        log_success(f"[OK] {type_media.upper()} {id}")
        return item

    except Exception as e:
        log_error(f"[CRASH ID {item['id']}] {e}\n{traceback.format_exc()}")
        return None

# -----------------------------
# MAIN MULTITHREAD
# -----------------------------
def main():
    print("🚀 Scraper PRO démarré…")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = []
    counter = 0

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = {executor.submit(process_item, item): item for item in data}

        for future in as_completed(futures):
            result = future.result()
            if result:
                updated.append(result)

            counter += 1

            # Checkpoint
            if counter % CHECKPOINT_EVERY == 0:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(updated, f, ensure_ascii=False, indent=2)
                print(f"💾 Checkpoint ({counter}/{len(data)})")

    # Sauvegarde finale
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print("🎉 Terminé !")
    print("📄 Fichier :", OUTPUT_FILE)
    print("📄 Logs : success.log / errors.log")

if __name__ == "__main__":
    main()
