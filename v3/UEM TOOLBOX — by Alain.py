import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json
import os
import requests
from bs4 import BeautifulSoup  # pip install beautifulsoup4

# =========================
#  THEMES
# =========================

THEMES = {
    "dark": {
        "bg": "#1e1e1e",
        "fg": "#ffffff",
        "accent": "#4af",
        "log_bg": "#111111",
        "log_fg": "#00ff00",
        "preview_bg": "#222222",
        "preview_fg": "#ffffff",
    },
    "light": {
        "bg": "#f5f5f5",
        "fg": "#111111",
        "accent": "#0078d4",
        "log_bg": "#ffffff",
        "log_fg": "#006400",
        "preview_bg": "#ffffff",
        "preview_fg": "#000000",
    }
}

current_theme = "dark"
current_file = None
current_data = None  # JSON en mémoire (liste ou dict)


# =========================
#  FONCTIONS UI GÉNÉRALES
# =========================

def apply_theme(root, widgets):
    theme = THEMES[current_theme]
    root.configure(bg=theme["bg"])

    for w in widgets:
        if isinstance(w, tk.Label):
            w.configure(bg=theme["bg"], fg=theme["fg"])
        elif isinstance(w, tk.Frame):
            w.configure(bg=theme["bg"])
        elif isinstance(w, tk.Text):
            if "log" in str(w):
                w.configure(bg=theme["log_bg"], fg=theme["log_fg"])
            else:
                w.configure(bg=theme["preview_bg"], fg=theme["preview_fg"])
        elif isinstance(w, tk.Button):
            w.configure(bg=theme["bg"], fg=theme["fg"], activebackground=theme["accent"])


def toggle_theme(root, widgets):
    global current_theme
    current_theme = "light" if current_theme == "dark" else "dark"
    apply_theme(root, widgets)


def log(msg):
    log_text.insert("end", msg + "\n")
    log_text.see("end")


def set_preview(content: str):
    preview.delete("1.0", "end")
    preview.insert("end", content)


# =========================
#  FICHIERS
# =========================

def open_file():
    global current_file, current_data

    file_path = filedialog.askopenfilename(
        title="Choisir un fichier",
        filetypes=[("Tous fichiers", "*.*")]
    )
    if not file_path:
        return

    current_file = file_path
    log(f"📂 Fichier chargé : {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        set_preview(content)

        if file_path.endswith(".json"):
            current_data = json.loads(content)
            log("✔ JSON chargé en mémoire")
        else:
            current_data = None

    except Exception as e:
        messagebox.showerror("Erreur", str(e))


def save_json():
    global current_data
    if current_data is None:
        messagebox.showerror("Erreur", "Aucun JSON en mémoire")
        return

    file_path = filedialog.asksaveasfilename(
        title="Enregistrer JSON",
        defaultextension=".json",
        filetypes=[("JSON", "*.json")]
    )
    if not file_path:
        return

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(current_data, f, ensure_ascii=False, indent=2)

    log(f"💾 JSON sauvegardé : {file_path}")


# =========================
#  EXTRACTION HTML → JSON UEM
# =========================

def extract_html_to_json():
    """Extraction TMDB RAW (media-card) → JSON UEM."""
    global current_data
    content = preview.get("1.0", "end").strip()
    if not content:
        messagebox.showerror("Erreur", "Aucun contenu HTML dans la prévisualisation")
        return

    try:
        soup = BeautifulSoup(content, "html.parser")
        cards = soup.select("[class*='media-card']")
        results = []

        for card in cards:
            link = card.select_one("a[href*='/movie/']")
            if not link:
                continue
            href = link.get("href", "")
            # /movie/384018-fast-furious-presents-hobbs-shaw
            parts = href.split("/movie/")
            if len(parts) < 2:
                continue
            id_slug = parts[1]
            if "-" not in id_slug:
                continue
            id_part = id_slug.split("-")[0]
            slug = "-".join(id_slug.split("-")[1:])

            img = card.select_one("img")
            thumbnail = ""
            if img and img.get("src"):
                thumbnail = img["src"].replace("w94_and_h141_face", "w440_and_h660_face")

            spans = card.select("h2 span")
            title_fr = spans[0].get_text(strip=True) if len(spans) > 0 else ""
            title_en = spans[1].get_text(strip=True).strip("()") if len(spans) > 1 else slug.replace("-", " ")

            date_el = card.select_one(".release_date")
            date = date_el.get_text(strip=True) if date_el else ""

            desc_el = card.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            obj = {
                "id": id_part,
                "type": "film",
                "title": title_en,
                "description": description,
                "tags": [""],
                "thumbnail": thumbnail,
                "embed": {
                    "provider": "vidking",
                    "iframe": f'<iframe src="https://www.vidking.net/embed/movie/{id_part}" allowfullscreen></iframe>',
                    "url": f"https://www.vidking.net/embed/movie/{id_part}-{slug}"
                },
                "meta": {
                    "duration": "",
                    "author": title_fr,
                    "date_added": date,
                    "source": "TMDB"
                }
            }
            results.append(obj)

        current_data = results
        set_preview(json.dumps(results, ensure_ascii=False, indent=2))
        log(f"✔ Extraction HTML → JSON UEM : {len(results)} éléments")

    except Exception as e:
        messagebox.showerror("Erreur extraction HTML", str(e))


# =========================
#  EXTRACTION DEPUIS URL TMDB
# =========================

def extract_from_url(url: str):
    """Télécharge une page TMDB, détecte le type, extrait HTML → JSON UEM."""
    global current_data

    url = url.strip()
    if not url.startswith("http"):
        messagebox.showerror("Erreur", "URL invalide")
        return

    log(f"🌐 Téléchargement : {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html = response.text
        set_preview(html)

        # Détection du type TMDB
        if "/collection/" in url:
            media_type = "collection"
        elif "/movie/" in url:
            media_type = "film"
        elif "/tv/" in url:
            media_type = "series"
        else:
            media_type = "unknown"

        log(f"🔎 Type détecté : {media_type}")

        # Extraction HTML → JSON UEM
        extract_html_to_json()

        # Ajout du type détecté dans chaque item
        if isinstance(current_data, list):
            for item in current_data:
                item["type"] = media_type

        set_preview(json.dumps(current_data, ensure_ascii=False, indent=2))
        log("✔ Extraction depuis URL terminée")

    except Exception as e:
        messagebox.showerror("Erreur URL", str(e))


# =========================
#  OPTIONS TMDB (STUB)
# =========================

def update_from_tmdb_stub():
    """
    Ici tu peux recoller ton code :
    - fetch_tmdb()
    - traduire()
    - logique film/série (title, overview, genres, runtime, etc.)
    en utilisant les options ci‑dessous.
    """
    global current_data
    if not isinstance(current_data, list):
        messagebox.showerror("Erreur", "Le JSON doit être une liste d'objets")
        return

    overwrite_title = var_overwrite_title.get()
    overwrite_desc = var_overwrite_desc.get()
    overwrite_tags = var_overwrite_tags.get()
    overwrite_thumb = var_overwrite_thumb.get()

    log("⚙️ TMDB pipeline (stub) :")
    log(f"  • overwrite_title = {overwrite_title}")
    log(f"  • overwrite_desc  = {overwrite_desc}")
    log(f"  • overwrite_tags  = {overwrite_tags}")
    log(f"  • overwrite_thumb = {overwrite_thumb}")
    log("👉 Branche ici ton code existant de mise à jour TMDB.")


# =========================
#  PIPELINE COMPLET
# =========================

def pipeline_complet():
    """
    1) Si contenu non JSON → extraction HTML → JSON
    2) Mise à jour TMDB (stub pour l’instant)
    """
    content = preview.get("1.0", "end").strip()
    if not content:
        messagebox.showerror("Erreur", "Aucun contenu dans la prévisualisation")
        return

    # 1) Si ce n'est pas du JSON → on tente HTML → JSON
    try:
        json.loads(content)
        log("📄 Contenu déjà JSON → pas d'extraction HTML")
    except:
        log("📄 Contenu non JSON → extraction HTML → JSON")
        extract_html_to_json()

    # 2) TMDB enrichissement (stub)
    update_from_tmdb_stub()

    log("✅ Pipeline complet terminé (structure prête pour UEM).")


# =========================
#  UI PRINCIPALE
# =========================

root = tk.Tk()
root.title("UEM TOOLBOX — by Alain")
root.geometry("1100x800")

header = tk.Label(
    root,
    text="UEM TOOLBOX — Multi‑Outils",
    font=("Segoe UI", 20, "bold")
)
header.pack(pady=5)

subtitle = tk.Label(
    root,
    text="Extraction HTML → JSON • Format UEM • TMDB • Écrasement contrôlé",
    font=("Segoe UI", 11)
)
subtitle.pack(pady=2)

# Notebook
notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=10, pady=10)

tab_main = tk.Frame(notebook)
tab_html = tk.Frame(notebook)
tab_tmdb = tk.Frame(notebook)
tab_logs = tk.Frame(notebook)

notebook.add(tab_main, text="Fichier & Prévisualisation")
notebook.add(tab_html, text="Extraction HTML / URL")
notebook.add(tab_tmdb, text="TMDB & Champs")
notebook.add(tab_logs, text="Logs")

# ---- Onglet MAIN ----
frame_buttons = tk.Frame(tab_main)
frame_buttons.pack(pady=5)

btn_open = tk.Button(frame_buttons, text="📂 Ouvrir fichier", command=open_file)
btn_open.grid(row=0, column=0, padx=5)

btn_pipeline = tk.Button(frame_buttons, text="🚀 Pipeline complet", command=pipeline_complet)
btn_pipeline.grid(row=0, column=1, padx=5)

btn_save = tk.Button(frame_buttons, text="💾 Sauvegarder JSON", command=save_json)
btn_save.grid(row=0, column=2, padx=5)

# bouton thème sera branché après définition de all_themable_widgets
btn_theme = tk.Button(frame_buttons, text="🌓 Mode clair/sombre")
btn_theme.grid(row=0, column=3, padx=5)

preview = tk.Text(tab_main, height=25)
preview.pack(fill="both", expand=True, padx=10, pady=10)

# ---- Onglet HTML / URL ----
lbl_html = tk.Label(tab_html, text="Extraction HTML → JSON (TMDB RAW / media-card)")
lbl_html.pack(pady=5)

url_frame = tk.Frame(tab_html)
url_frame.pack(pady=5)

tk.Label(url_frame, text="URL TMDB :").grid(row=0, column=0, padx=5)
entry_url = tk.Entry(url_frame, width=60)
entry_url.grid(row=0, column=1, padx=5)

btn_extract_url = tk.Button(
    url_frame,
    text="🌐 Extraire depuis URL",
    command=lambda: extract_from_url(entry_url.get())
)
btn_extract_url.grid(row=0, column=2, padx=5)

btn_extract_html = tk.Button(
    tab_html,
    text="🔎 Extraire HTML → JSON UEM",
    command=extract_html_to_json
)
btn_extract_html.pack(pady=5)

# ---- Onglet TMDB ----
lbl_tmdb = tk.Label(tab_tmdb, text="Options de mise à jour via TMDB")
lbl_tmdb.pack(pady=5)

options_frame = tk.Frame(tab_tmdb)
options_frame.pack(pady=5)

var_overwrite_title = tk.BooleanVar(value=True)
var_overwrite_desc = tk.BooleanVar(value=False)
var_overwrite_tags = tk.BooleanVar(value=False)
var_overwrite_thumb = tk.BooleanVar(value=False)

tk.Checkbutton(options_frame, text="Écraser TITLE", variable=var_overwrite_title).grid(row=0, column=0, sticky="w")
tk.Checkbutton(options_frame, text="Écraser DESCRIPTION si vide", variable=var_overwrite_desc).grid(row=1, column=0, sticky="w")
tk.Checkbutton(options_frame, text="Écraser TAGS", variable=var_overwrite_tags).grid(row=2, column=0, sticky="w")
tk.Checkbutton(options_frame, text="Écraser THUMBNAIL si vide", variable=var_overwrite_thumb).grid(row=3, column=0, sticky="w")

btn_tmdb_update = tk.Button(tab_tmdb, text="⚙️ Lancer mise à jour TMDB", command=update_from_tmdb_stub)
btn_tmdb_update.pack(pady=10)

# ---- Onglet LOGS ----
log_text = tk.Text(tab_logs, height=20)
log_text.pack(fill="both", expand=True, padx=10, pady=10)

# Widgets à thématiser
all_themable_widgets = [
    root, header, subtitle,
    tab_main, tab_html, tab_tmdb, tab_logs,
    frame_buttons, preview, log_text,
    lbl_html, lbl_tmdb, options_frame,
    btn_open, btn_pipeline, btn_save, btn_theme,
    btn_extract_html, btn_extract_url, btn_tmdb_update,
    url_frame, entry_url
]

apply_theme(root, all_themable_widgets)

# maintenant qu'on a all_themable_widgets, on peut brancher le bouton thème
btn_theme.configure(command=lambda: toggle_theme(root, all_themable_widgets))

root.mainloop()
