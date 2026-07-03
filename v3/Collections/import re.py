import re
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_FILE = SCRIPT_DIR / "data.json"
OUTPUT_FILE = SCRIPT_DIR / "collections.json"

def extract_collections(html_text: str):
    """Extrait les collections depuis le contenu HTML dpstream"""

    # Trouver tous les blocs de collections
    blocks = re.findall(r'(<a href="/collection/\d+.*?</a>)', html_text, re.DOTALL)
    
    collections = []
    
    for block in blocks:
        # ID
        id_match = re.search(r'href="/collection/(\d+)"', block)
        coll_id = id_match.group(1) if id_match else None
        
        # Titre
        title_match = re.search(r'<h3[^>]*>(.*?)</h3>', block)
        title = title_match.group(1).strip() if title_match else "Collection inconnue"
        
        # Cover (image principale)
        cover_match = re.search(r'<img[^>]+src="(https://image\.tmdb\.org/t/p/w500/[^\"]+)"', block)
        cover = cover_match.group(1) if cover_match else ""
        
        # Nombre de films
        count_match = re.search(r'(\d+)\s*films?', block)
        count = int(count_match.group(1)) if count_match else 0
        
        # Description
        desc_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
        if desc_match:
            description = re.sub(r'<[^>]+>', '', desc_match.group(1))
            description = re.sub(r'\s+', ' ', description).strip()
        else:
            description = ""
        
        # Posters (miniatures)
        posters = []
        poster_matches = re.findall(
            r'<img src=[](https://image\.tmdb\.org/t/p/w200/[^"]+)" alt="([^"]+)"', 
            block
        )
        for src, alt in poster_matches[:4]:  # max 4 posters
            posters.append({
                "src": src,
                "alt": alt
            })
        
        collection = {
            "id": coll_id,
            "title": title,
            "cover": cover,
            "count": count,
            "description": description,
            "posters": posters,
            "extra": 0
        }
        collections.append(collection)
    
    return collections


if __name__ == "__main__":
    if not INPUT_FILE.exists():
        print(f"Erreur: le fichier {INPUT_FILE} n'existe pas.")
        raise SystemExit(1)
    
    html_text = INPUT_FILE.read_text(encoding="utf-8")
    print(f"Extraction en cours de {INPUT_FILE}...")
    data = extract_collections(html_text)
    
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Terminé ! {len(data)} collections extraites.")
    print(f"📁 Fichier sauvegardé : {OUTPUT_FILE}")