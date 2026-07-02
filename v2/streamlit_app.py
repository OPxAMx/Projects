import json
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from tkinter import Tk
from tkinter.filedialog import askdirectory, askopenfilename

from check_json_duplicates import deduplicate_records, load_json_data, normalize_titles
from metadata_scraper import enrich_records

ROOT = Path(__file__).resolve().parent

st.set_page_config(page_title="JSON Pipeline Manager", page_icon="🧩", layout="wide")
st.title("JSON Pipeline Manager")
st.caption("Prototype d’interface pour fusionner, nettoyer, enrichir et exporter vos fichiers JSON")

if "records" not in st.session_state:
    st.session_state.records = []
if "source_file" not in st.session_state:
    st.session_state.source_file = ""
if "source_folder" not in st.session_state:
    st.session_state.source_folder = str(ROOT / "v3" / "test-doublon")
if "manual_choices" not in st.session_state:
    st.session_state.manual_choices = {}
if "duplicate_groups" not in st.session_state:
    st.session_state.duplicate_groups = {}
if "section_index" not in st.session_state:
    st.session_state.section_index = 0


def choose_file_path() -> str:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = askopenfilename(filetypes=[("JSON files", "*.json"), ("Tous les fichiers", "*.*")])
    root.destroy()
    return path


def choose_folder_path() -> str:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = askdirectory()
    root.destroy()
    return path


def load_records_from_path(file_path: str | None = None, folder_path: str | None = None, section_limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if folder_path:
        root = Path(folder_path)
        if root.exists() and root.is_dir():
            files = sorted(root.rglob("*.json"))
            if section_limit is not None:
                files = files[st.session_state.section_index : st.session_state.section_index + section_limit]
            for path in files:
                data = load_json_data(path)
                if isinstance(data, list):
                    records.extend([item for item in data if isinstance(item, dict)])
                elif isinstance(data, dict):
                    records.append(data)
        return records

    if file_path:
        path = Path(file_path)
        if path.exists():
            data = load_json_data(path)
            if isinstance(data, list):
                records.extend([item for item in data if isinstance(item, dict)])
            elif isinstance(data, dict):
                records.append(data)
    return records


def records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        tags = record.get("tags", [])
        if isinstance(tags, list):
            tags_text = ", ".join(str(tag) for tag in tags if str(tag).strip())
        elif isinstance(tags, str):
            tags_text = tags
        else:
            tags_text = ""
        rows.append(
            {
                "id": record.get("id", ""),
                "title": record.get("title", ""),
                "type": record.get("type", ""),
                "tags": tags_text,
                "classification": record.get("classification", ""),
                "source": record.get("source", ""),
            }
        )
    return pd.DataFrame(rows)


def save_records(records: list[dict[str, Any]], output_path: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def export_dataframe(df: pd.DataFrame, output_path: str, fmt: str) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        df.to_csv(output, index=False, encoding="utf-8")
    elif fmt == "excel":
        df.to_excel(output, index=False, engine="openpyxl")


def merge_record_values(current: Any, candidate: Any) -> Any:
    if current is None or current == "":
        return deepcopy(candidate)
    if isinstance(current, dict) and isinstance(candidate, dict):
        merged = deepcopy(current)
        for key, value in candidate.items():
            merged[key] = merge_record_values(merged.get(key), value)
        return merged
    if isinstance(current, list) and isinstance(candidate, list):
        merged_list = deepcopy(current)
        for item in candidate:
            if item not in merged_list:
                merged_list.append(item)
        return merged_list
    if isinstance(current, str) and isinstance(candidate, str):
        if not current.strip():
            return candidate
        if len(candidate.strip()) > len(current.strip()):
            return candidate
        if current.strip() != candidate.strip():
            return f"{current} | {candidate}"
        return current
    if isinstance(current, (int, float)) and isinstance(candidate, (int, float)) and candidate != current:
        return candidate
    return current


def merge_duplicate_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for record in records:
        merged = merge_record_values(merged, record)
    merged["classification"] = auto_classify_record(merged)
    return merged


def auto_classify_record(record: dict[str, Any]) -> str:
    searchable = []
    for key in ("title", "type", "description", "overview", "summary", "synopsis", "content", "tags"):
        value = record.get(key, "")
        if isinstance(value, list):
            searchable.extend([str(item) for item in value])
        else:
            searchable.append(str(value))
    if isinstance(record.get("meta"), dict):
        searchable.append(json.dumps(record.get("meta"), ensure_ascii=False))
    text = " ".join(searchable).lower()
    if any(token in text for token in ["film", "movie", "cinema", "cinéma", "trailer", "feature"]):
        return "Film"
    if any(token in text for token in ["serie", "series", "tv", "show", "saison", "episode", "épisode"]):
        return "Série"
    if any(token in text for token in ["music", "musique", "album", "song", "chanson", "playlist", "artist", "artiste"]):
        return "Musique"
    if any(token in text for token in ["documentaire", "documentary", "doc"]):
        return "Documentaire"
    if any(token in text for token in ["animation", "anime", "dessin"]):
        return "Animation"
    if any(token in text for token in ["podcast", "interview", "talk"]):
        return "Podcast"
    if any(token in text for token in ["sport", "actualité", "actualite", "news"]):
        return "Actualité"
    return "Autre"


def build_preview_payload(record: dict[str, Any]) -> dict[str, Any]:
    image_url = ""
    for key in ("image", "poster", "poster_url", "image_url", "thumbnail", "cover", "banner", "photo", "picture", "img"):
        value = record.get(key, "")
        if isinstance(value, str) and value.strip():
            image_url = value.strip()
            break
    if not image_url and isinstance(record.get("meta"), dict):
        meta = record.get("meta", {})
        for key in ("image", "poster", "thumbnail", "cover", "banner"):
            value = meta.get(key, "")
            if isinstance(value, str) and value.strip():
                image_url = value.strip()
                break

    description = ""
    for key in ("description", "overview", "plot", "summary", "synopsis", "content", "notes"):
        value = record.get(key, "")
        if isinstance(value, str) and value.strip():
            description = value.strip()
            break

    metadata = {
        "source": record.get("source", ""),
        "year": record.get("year", "") or record.get("meta", {}).get("year", "") if isinstance(record.get("meta"), dict) else "",
        "duration": record.get("meta", {}).get("duration", "") if isinstance(record.get("meta"), dict) else "",
        "producer": record.get("meta", {}).get("producer", "") if isinstance(record.get("meta"), dict) else "",
        "cast": record.get("meta", {}).get("cast", "") if isinstance(record.get("meta"), dict) else "",
        "classification": record.get("classification", ""),
    }
    return {"image_url": image_url, "description": description, "metadata": metadata}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def compute_duplicate_score(record_a: dict[str, Any], record_b: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if not isinstance(record_a, dict) or not isinstance(record_b, dict):
        return 0, ["Entrée invalide"]

    a_id = normalize_text(record_a.get("id"))
    b_id = normalize_text(record_b.get("id"))
    if a_id and b_id and a_id == b_id:
        score += 60
        reasons.append("ID identique")

    a_title = normalize_text(record_a.get("title"))
    b_title = normalize_text(record_b.get("title"))
    if a_title and b_title:
        similarity = SequenceMatcher(None, a_title, b_title).ratio()
        if similarity >= 0.9:
            score += 35
            reasons.append("Titres quasi identiques")
        elif similarity >= 0.7:
            score += 25
            reasons.append("Titres similaires")
        elif similarity >= 0.5:
            score += 15
            reasons.append("Titres proches")

    a_type = normalize_text(record_a.get("type"))
    b_type = normalize_text(record_b.get("type"))
    if a_type and b_type and a_type == b_type:
        score += 10
        reasons.append("Type identique")

    a_tags = set(normalize_text(tag).replace(" ", "") for tag in record_a.get("tags", []) if isinstance(record_a.get("tags"), list))
    b_tags = set(normalize_text(tag).replace(" ", "") for tag in record_b.get("tags", []) if isinstance(record_b.get("tags"), list))
    overlap = len(a_tags & b_tags)
    if overlap:
        score += min(10, overlap * 3)
        reasons.append("Tags partagés")

    a_desc = normalize_text(record_a.get("description") or record_a.get("overview") or record_a.get("summary"))
    b_desc = normalize_text(record_b.get("description") or record_b.get("overview") or record_b.get("summary"))
    if a_desc and b_desc:
        desc_similarity = SequenceMatcher(None, a_desc, b_desc).ratio()
        if desc_similarity >= 0.7:
            score += 10
            reasons.append("Descriptions similaires")

    if normalize_text(record_a.get("source")) and normalize_text(record_a.get("source")) == normalize_text(record_b.get("source")):
        score += 5
        reasons.append("Source identique")

    return min(score, 100), reasons


def score_to_color(score: int) -> str:
    if score >= 80:
        return "#2e7d32"
    if score >= 60:
        return "#f9a825"
    return "#c62828"


def recommend_duplicate_action(score: int) -> str:
    if score >= 80:
        return "fusionner"
    if score >= 55:
        return "garder"
    return "supprimer"


def build_duplicate_report(duplicate_groups: dict[Any, list[tuple[int, dict[str, Any]]]], manual_choices: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, items in duplicate_groups.items():
        if len(items) < 2:
            continue
        pair_scores: list[tuple[int, list[str]]] = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                score, reasons = compute_duplicate_score(items[i][1], items[j][1])
                pair_scores.append((score, reasons))
        group_score = max(score for score, _ in pair_scores) if pair_scores else 0
        recommendation = recommend_duplicate_action(group_score)
        selected_choice = manual_choices.get(str(key), {"action": recommendation, "selected_index": 0})
        rows.append(
            {
                "group": str(key),
                "entries": len(items),
                "recommended_action": recommendation,
                "selected_action": selected_choice.get("action", recommendation),
                "selected_index": selected_choice.get("selected_index", 0),
                "score": group_score,
                "justification": "; ".join(dict.fromkeys(reason for _, reasons in pair_scores for reason in reasons)),
                "titles": " | ".join(item[1].get("title", "Sans titre") for _, item in items),
            }
        )
    return rows


def export_duplicate_report(rows: list[dict[str, Any]], output_path: str, fmt: str) -> str:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        pd.DataFrame(rows).to_csv(output, index=False, encoding="utf-8")
    else:
        with output.open("w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return str(output)


def split_by_classification(records: list[dict[str, Any]], folder: str) -> list[str]:
    output_dir = Path(folder)
    output_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        classification = str(record.get("classification", "autre")).strip() or "autre"
        grouped.setdefault(classification, []).append(record)
    for name, items in grouped.items():
        out_path = output_dir / f"{name.replace(' ', '_').lower()}.json"
        save_records(items, str(out_path))
        exported.append(str(out_path))
    return exported


with st.sidebar:
    st.header("Sélection")
    if st.button("Choisir un fichier JSON"):
        st.session_state.source_file = choose_file_path()
    if st.button("Choisir un dossier"):
        st.session_state.source_folder = choose_folder_path() or st.session_state.source_folder

    st.text_input("Fichier sélectionné", key="source_file_input", value=st.session_state.source_file)
    st.text_input("Dossier sélectionné", key="source_folder_input", value=st.session_state.source_folder)

    if st.button("Charger les données"):
        if st.session_state.source_file:
            st.session_state.records = load_records_from_path(file_path=st.session_state.source_file)
        elif st.session_state.source_folder:
            st.session_state.records = load_records_from_path(folder_path=st.session_state.source_folder)
        else:
            st.session_state.records = []
        st.session_state.manual_choices = {}

    st.markdown("---")
    st.header("Analyse par section")
    section_size = st.number_input("Taille d’une section", min_value=1, max_value=50, value=5)
    section_index = st.number_input("Index de la section", min_value=0, max_value=1000, value=0, step=1)
    st.session_state.section_index = int(section_index)
    if st.button("Charger une section"):
        if st.session_state.source_file:
            st.session_state.records = load_records_from_path(file_path=st.session_state.source_file)
        elif st.session_state.source_folder:
            st.session_state.records = load_records_from_path(folder_path=st.session_state.source_folder, section_limit=int(section_size))
        else:
            st.session_state.records = []
        st.session_state.manual_choices = {}

    st.markdown("---")
    st.header("Export")
    export_path = st.text_input("Chemin de sortie CSV/Excel", value=str(ROOT / "exports" / "export.csv"))
    export_format = st.radio("Format", ["csv", "excel"], horizontal=True)
    if st.button("Exporter les données") and st.session_state.records:
        df = records_to_dataframe(st.session_state.records)
        export_dataframe(df, export_path, export_format)
        st.success(f"Exporté vers {export_path}")


tab_fusion, tab_nettoyage, tab_enrichissement = st.tabs(["Fusion", "Nettoyage", "Enrichissement"])

with tab_fusion:
    st.subheader("Fusion de fichiers JSON")
    output_file = st.text_input("Fichier de fusion", value=str(ROOT / "v3" / "test-doublon" / "merged.json"))
    merge_field = st.text_input("Champ de comparaison", value="id")
    normalize_check = st.checkbox("Mettre les titres en style Title Case", value=True)
    if st.button("Fusionner") and st.session_state.records:
        merged = st.session_state.records
        if normalize_check:
            merged = normalize_titles(merged)
        deduped, removed = deduplicate_records(merged, field=merge_field)
        save_records(deduped, output_file)
        st.success(f"Fusion réalisée : {len(deduped)} éléments conservés, {removed} doublons éliminés")

    if st.session_state.records:
        preview_df = records_to_dataframe(st.session_state.records)
        st.dataframe(preview_df.head(100), use_container_width=True)
    else:
        st.info("Chargez d’abord un fichier ou un dossier depuis la barre latérale.")

with tab_nettoyage:
    st.subheader("Consolidation manuelle des doublons")
    duplicate_field = st.text_input("Champ pour la détection", value="id")
    if st.button("Analyser les doublons") and st.session_state.records:
        groups: dict[Any, list[tuple[int, dict[str, Any]]]] = {}
        for index, record in enumerate(st.session_state.records):
            key = record.get(duplicate_field, "") if isinstance(record, dict) and duplicate_field in record else ""
            groups.setdefault(key, []).append((index, record))
        duplicate_groups = {key: items for key, items in groups.items() if len(items) > 1}
        st.session_state.manual_choices = {}
        st.session_state.duplicate_groups = duplicate_groups

    if st.session_state.duplicate_groups:
        st.write(f"{len(st.session_state.duplicate_groups)} groupe(s) de doublons détectés")
        comparison_df = []
        for key, items in st.session_state.duplicate_groups.items():
            for index, item in enumerate(items):
                comparison_df.append({
                    "group": key,
                    "option": index + 1,
                    "id": item[1].get("id", ""),
                    "title": item[1].get("title", ""),
                    "type": item[1].get("type", ""),
                    "tags": ", ".join(item[1].get("tags", [])) if isinstance(item[1].get("tags", []), list) else item[1].get("tags", ""),
                    "content": json.dumps(item[1], ensure_ascii=False)[:300],
                })
        st.dataframe(pd.DataFrame(comparison_df), use_container_width=True)

        for key, items in st.session_state.duplicate_groups.items():
            with st.expander(f"Groupe {key} ({len(items)} entrées)"):
                score_rows = []
                for i in range(len(items)):
                    for j in range(i + 1, len(items)):
                        score, reasons = compute_duplicate_score(items[i][1], items[j][1])
                        score_rows.append({
                            "Option A": f"{i + 1} - {items[i][1].get('title', 'Sans titre')}",
                            "Option B": f"{j + 1} - {items[j][1].get('title', 'Sans titre')}",
                            "Score": score,
                            "Raisons": ", ".join(reasons),
                        })
                if score_rows:
                    st.dataframe(pd.DataFrame(score_rows), use_container_width=True)

                group_score = max(
                    compute_duplicate_score(items[i][1], items[j][1])[0]
                    for i in range(len(items))
                    for j in range(i + 1, len(items))
                ) if len(items) >= 2 else 0
                recommendation = recommend_duplicate_action(group_score)
                color = score_to_color(group_score)
                st.markdown(
                    f"<div style='padding:0.6rem 0.8rem;border-radius:0.5rem;background-color:{color};color:white;font-weight:bold'>"
                    f"Recommandation automatique : {recommendation.upper()} — score {group_score}/100</div>",
                    unsafe_allow_html=True,
                )
                st.progress(min(1.0, group_score / 100))
                st.caption("Justifications : " + ", ".join(dict.fromkeys(reason for i in range(len(items)) for j in range(i + 1, len(items)) for reason in compute_duplicate_score(items[i][1], items[j][1])[1])))

                st.write("Choisissez l’action à appliquer sur ce groupe :")
                action_options = ["garder", "supprimer", "fusionner"]
                current_choice = st.session_state.manual_choices.get(str(key), {}).get("action", recommendation)
                action_index = action_options.index(current_choice) if current_choice in action_options else action_options.index(recommendation)
                action = st.radio("Action", action_options, index=action_index, key=f"action_{key}", horizontal=True)
                choice = st.selectbox("Version à conserver", [f"{i + 1} - {item[1].get('title', 'Sans titre')}" for i, item in enumerate(items)], key=f"select_{key}")
                selected_index = [f"{i + 1} - {item[1].get('title', 'Sans titre')}" for i, item in enumerate(items)].index(choice)
                st.session_state.manual_choices[str(key)] = {"action": action, "selected_index": selected_index}

                if len(items) >= 2:
                    left_col, right_col = st.columns(2)
                    for column, idx in [(left_col, 0), (right_col, 1)]:
                        with column:
                            record = items[idx][1]
                            preview = build_preview_payload(record)
                            st.markdown(f"### Option {idx + 1}")
                            st.markdown(f"**{record.get('title', 'Sans titre')}**")
                            if preview["image_url"]:
                                st.image(preview["image_url"], use_container_width=True)
                            st.write(preview["description"] or "Aucune description disponible")
                            st.caption("Métadonnées")
                            st.json(preview["metadata"], expanded=False)
                    if len(items) >= 2:
                        score, reasons = compute_duplicate_score(items[0][1], items[1][1])
                        st.metric("Score de similarité", f"{score}/100")
                        st.caption("Raisons : " + ", ".join(reasons))

                preview_index = st.selectbox("Prévisualiser une version", options=range(len(items)), format_func=lambda idx: f"Option {idx + 1} - {items[idx][1].get('title', 'Sans titre')}", key=f"preview_{key}")
                preview_record = items[preview_index][1]
                preview = build_preview_payload(preview_record)
                preview_col, info_col = st.columns([1, 2])
                with preview_col:
                    if preview["image_url"]:
                        st.image(preview["image_url"], use_container_width=True)
                    else:
                        st.info("Aucune image disponible")
                with info_col:
                    st.markdown(f"### {preview_record.get('title', 'Sans titre')}")
                    st.write(preview["description"] or "Aucune description disponible")
                    st.caption("Métadonnées")
                    st.json(preview["metadata"], expanded=False)

                cols = st.columns(len(items))
                for idx, col in enumerate(cols):
                    with col:
                        st.markdown(f"### Option {idx + 1}")
                        st.json(items[idx][1], expanded=False)
        if st.button("Appliquer la consolidation manuelle"):
            consolidated: list[dict[str, Any]] = []
            kept_keys: set[Any] = set()
            for key, items in st.session_state.duplicate_groups.items():
                choice = st.session_state.manual_choices.get(str(key), {"action": "garder", "selected_index": 0})
                action = choice.get("action", "garder")
                selected_index = choice.get("selected_index", 0)
                if action == "garder":
                    chosen_record = dict(items[selected_index][1])
                    if not chosen_record.get("classification"):
                        chosen_record["classification"] = auto_classify_record(chosen_record)
                    if key not in kept_keys:
                        consolidated.append(chosen_record)
                        kept_keys.add(key)
                elif action == "fusionner":
                    chosen_record = merge_duplicate_group([item[1] for item in items])
                    chosen_record["title"] = chosen_record.get("title") or items[selected_index][1].get("title", "")
                    chosen_record["classification"] = chosen_record.get("classification") or auto_classify_record(chosen_record)
                    if key not in kept_keys:
                        consolidated.append(chosen_record)
                        kept_keys.add(key)
                else:
                    continue
            for record in st.session_state.records:
                record_key = record.get(duplicate_field, "") if isinstance(record, dict) and duplicate_field in record else None
                if record_key in kept_keys:
                    continue
                if isinstance(record, dict):
                    consolidated.append(record)
            output_clean = st.text_input("Fichier de nettoyage", value=str(ROOT / "v3" / "test-doublon" / "cleaned.json"))
            save_records(consolidated, output_clean)
            st.success(f"Consolidation écrite dans {output_clean}")

        st.markdown("---")
        st.subheader("Rapport de doublons")
        report_path = st.text_input("Chemin du rapport", value=str(ROOT / "exports" / "duplicate_report.csv"))
        report_format = st.radio("Format du rapport", ["csv", "json"], horizontal=True)
        if st.button("Exporter le rapport de doublons") and st.session_state.duplicate_groups:
            report_rows = build_duplicate_report(st.session_state.duplicate_groups, st.session_state.manual_choices)
            exported_path = export_duplicate_report(report_rows, report_path, report_format)
            st.success(f"Rapport exporté vers {exported_path}")
            st.dataframe(pd.DataFrame(report_rows), use_container_width=True)
    else:
        st.info("Aucun doublon détecté pour le moment.")

with tab_enrichissement:
    st.subheader("Enrichissement et organisation")
    if st.session_state.records:
        st.write("Le module de scraping de métadonnées peut enrichir les fiches à partir d’une API externe ou directement à partir d’une URL.")
        api_key = st.text_input("Clé API (OMDb/TMDb)", value="")
        provider = st.selectbox("Provider", ["omdb", "tmdb"], index=0)
        enrichment_mode = st.selectbox("Mode d’enrichissement", ["auto", "title", "url", "title_and_url"], index=0)
        limit = st.number_input("Nombre d’éléments à enrichir", min_value=1, max_value=100, value=20)
        if st.button("Enrichir les métadonnées"):
            enriched = enrich_records(st.session_state.records, api_key=api_key or None, provider=provider, limit=int(limit), mode=enrichment_mode)
            save_records(enriched, str(ROOT / "v3" / "test-doublon" / "enriched.json"))
            st.session_state.records = enriched
            st.success(f"{len(enriched)} éléments enrichis")

        df = records_to_dataframe(st.session_state.records)
        edited_df = st.data_editor(
            df,
            column_config={
                "tags": st.column_config.TextColumn("Tags (séparés par des virgules)", width="large"),
                "classification": st.column_config.TextColumn("Classification / Bucket"),
            },
            disabled=["id", "title", "type"],
            use_container_width=True,
        )
        if st.button("Classer automatiquement"):
            classified = []
            for record in st.session_state.records:
                updated_record = dict(record)
                updated_record["classification"] = auto_classify_record(updated_record)
                classified.append(updated_record)
            save_records(classified, str(ROOT / "v3" / "test-doublon" / "classified.json"))
            st.session_state.records = classified
            st.success("Classification automatique appliquée")

        if st.button("Sauvegarder les modifications"):
            updated_records: list[dict[str, Any]] = []
            for row in edited_df.to_dict(orient="records"):
                tags = [tag.strip() for tag in str(row.get("tags", "")).split(",") if tag.strip()]
                record = {
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "type": row.get("type", ""),
                    "tags": tags,
                    "classification": row.get("classification", ""),
                }
                updated_records.append(record)
            save_records(updated_records, str(ROOT / "v3" / "test-doublon" / "enriched.json"))
            st.session_state.records = updated_records
            st.success("Modifications sauvegardées")

        st.markdown("---")
        st.subheader("Prévisualisation détaillée")
        preview_options = [f"{index + 1} - {record.get('title', 'Sans titre')}" for index, record in enumerate(st.session_state.records)]
        selected_preview = st.selectbox("Choisir un élément", options=preview_options, index=0 if preview_options else None)
        if selected_preview:
            preview_index = preview_options.index(selected_preview)
            preview_record = st.session_state.records[preview_index]
            preview = build_preview_payload(preview_record)
            preview_col, info_col = st.columns([1, 2])
            with preview_col:
                if preview["image_url"]:
                    st.image(preview["image_url"], use_container_width=True)
                else:
                    st.info("Aucune image disponible")
            with info_col:
                st.markdown(f"### {preview_record.get('title', 'Sans titre')}")
                st.write(preview["description"] or "Aucune description disponible")
                st.caption("Métadonnées")
                st.json(preview["metadata"], expanded=False)

        split_folder = st.text_input("Dossier de séparation", value=str(ROOT / "exports" / "separated"))
        if st.button("Séparer par classification"):
            exported = split_by_classification(st.session_state.records, split_folder)
            st.success("Fichiers générés : " + ", ".join(exported))
    else:
        st.info("Chargez d’abord des données pour les modifier.")
