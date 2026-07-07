import json
import os

INPUT_FILE = "input_uem.json"
OUTPUT_FILE = "carousel_output.html"

def make_card(item):
    """Génère une card HTML Prime Video à partir d’un item UEM."""

    backdrop = item.get("backdrop", "")
    title = item.get("title", "")
    release_date = item.get("release_date", "")
    runtime = item.get("runtime", 0)
    description = item.get("description", "")
    url_trailer = item.get("url_trailer", "")
    logos = item.get("logos", "")

    duration = f"{runtime} min" if runtime else ""

    html = f"""
    <div class="pv-item">
      <article class="movie-card">

        <img src="{backdrop}" alt="wallpaper" />

        <div class="yt-preview">
          {url_trailer}
          <button class="unmute-btn">🔊</button>
        </div>

        <div class="content">
          <h1><img src="{logos}" class="title"></h1>

          <div class="infos">
            <span>·&nbsp;&nbsp; {release_date} &nbsp;&nbsp;·&nbsp;&nbsp; {duration}</span>
          </div>

          <p class="synopsis">{description}</p>

          <div class="icons">
            <svg width="25" height="25"></svg>
            <svg width="25" height="25"></svg>
            <svg width="25" height="25"></svg>
          </div>

          <button class="preview-btn">Voir preview</button>
        </div>

      </article>
    </div>
    """
    return html


def convert_to_carousel(input_path, output_path):
    """Lit une liste UEM et génère un fichier HTML complet pour un carousel Prime Video."""

    if not os.path.exists(input_path):
        print(f"[ERREUR] Le fichier {input_path} n'existe pas.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        uem_list = json.load(f)

    if not isinstance(uem_list, list):
        print("[ERREUR] Le fichier JSON doit contenir une LISTE de films.")
        return

    cards_html = "\n".join(make_card(item) for item in uem_list)

    final_html = f"""
<div class="pv-carousel">
  <h2 class="pv-title">Carousel UEM</h2>

  <button class="pv-arrow pv-left">‹</button>
  <button class="pv-arrow pv-right">›</button>

  <div class="pv-track">
    {cards_html}
  </div>
</div>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_html)

    print(f"[OK] Carousel généré → {output_path}")


# Exécution
convert_to_carousel(INPUT_FILE, OUTPUT_FILE)
