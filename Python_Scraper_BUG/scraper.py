import json
import time
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from datetime import datetime

# -----------------------------
# CONFIG
# -----------------------------
INPUT_FILE = "data.json"
OUTPUT_FILE = "data_updated.json"
ERROR_FILE = "errors.log"
LOG_FILE = "scraper.log"

BASE_URL = "https://www.themoviedb.org/tv/"   # changer en /movie/ si besoin
HEADERS = {"User-Agent": "Mozilla/5.0"}

# -----------------------------
# LOGGING UTILS
# -----------------------------
def log(msg):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} {msg}\n")
    print(msg)

def log_error(msg):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(ERROR_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} {msg}\n")
    print("❌ " + msg)

# -----------------------------
# SCRAPER
# -----------------------------
def fetch_description(id):
    url = f"{BASE_URL}{id}"
    log(f"🔎 Scraping ID {id} → {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
    except Exception as e:
        log_error(f"Erreur réseau pour ID {id}: {e}")
        return None

    if response.status_code != 200:
        log_error(f"HTTP {response.status_code} pour ID {id}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    desc = soup.find("div", class_="overview")

    if not desc:
        log_error(f"Description introuvable pour ID {id}")
        return None

    texte = desc.text.strip()
    return texte

# -----------------------------
# TRADUCTION
# -----------------------------
def translate(text, id):
    try:
        return GoogleTranslator(source="auto", target="fr").translate(text)
    except Exception as e:
        log_error(f"Erreur traduction pour ID {id}: {e}")
        return text  # fallback

# -----------------------------
# MAIN PIPELINE
# -----------------------------
def main():
    log("🚀 Démarrage du scraper")

    # Charger JSON
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Reprise automatique : si OUTPUT existe, on recharge
    processed_ids = set()
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            old_data = json.load(f)
            for item in old_data:
                processed_ids.add(item["id"])
        log(f"🔁 Reprise automatique : {len(processed_ids)} IDs déjà traités")
    except:
        log("🆕 Aucun fichier existant, démarrage à zéro")

    updated_data = []

    for item in data:
        id = item["id"]

        if id in processed_ids:
            log(f"⏩ ID {id} déjà traité, skip")
            updated_data.append(item)
            continue

        # Scraping
        texte = fetch_description(id)
        if not texte:
            log_error(f"Impossible de récupérer la description pour ID {id}")
            continue

        # Traduction
        traduction = translate(texte, id)
        item["description"] = traduction

        updated_data.append(item)

        # Sauvegarde progressive (sécurité)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(updated_data, f, ensure_ascii=False, indent=2)

        time.sleep(1)  # éviter rate-limit

    log("🎉 Terminé ! Fichier final sauvegardé.")
    log(f"📄 Output : {OUTPUT_FILE}")
    log(f"⚠️ Erreurs : {ERROR_FILE}")

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    main()
