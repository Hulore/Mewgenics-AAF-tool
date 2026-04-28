from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.classify_active_abilities_from_wiki import (
    FRAME_FOLDER_NAMES,
    WIKI_URL,
    classify_attributes,
    fetch_wiki_html,
    normalize_name,
    parse_wiki_abilities,
    read_manifest,
    safe_name,
    split_normal_upgraded,
)


def value_kind(description: str) -> str:
    text = description.lower()
    has_heal = "heal" in text or "healing" in text
    has_damage = "damage" in text or "damages" in text or "attack" in text
    if has_heal and has_damage:
        return "damage_or_heal"
    if has_heal:
        return "heal"
    if has_damage:
        return "damage"
    return "none"


def parse_attributes(attributes: str) -> dict:
    tokens = attributes.split()
    frame_key = classify_attributes(attributes)
    frame_type = FRAME_FOLDER_NAMES[frame_key]

    data = {
        "raw": attributes,
        "frame_type": frame_type,
        "value": "",
        "mana": "",
        "hit_count": None,
        "hit_value": "",
    }

    if not tokens:
        return data

    if frame_key == "mana":
        data["mana"] = tokens[-1]
        return data

    data["value"] = tokens[0]
    data["mana"] = tokens[-1] if len(tokens) > 1 else ""

    multi_match = re.fullmatch(r"(\d+)\s*x\s*([\d?]+)", tokens[0], flags=re.IGNORECASE)
    if multi_match:
        data["hit_count"] = int(multi_match.group(1))
        data["hit_value"] = multi_match.group(2)

    return data


def read_translations(path: Path | None) -> dict[str, dict[str, str]]:
    if not path or not path.exists():
        return {}

    translations: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            key = row.get("+", "")
            if not key:
                continue
            translations[key] = {
                "en": row.get("en", ""),
                "ru": row.get("ru", ""),
            }
    return translations


def translation_block(manifest_row: dict[str, str] | None, translations: dict[str, dict[str, str]]) -> dict:
    text_key = manifest_row.get("text_key", "") if manifest_row else ""
    if not text_key.endswith("_NAME"):
        return {
            "text_key": text_key,
            "ru_name": "",
            "ru_description": "",
            "ru_upgraded_description": "",
            "en_name": "",
            "en_description": "",
            "en_upgraded_description": "",
        }

    base_key = text_key[:-5]
    name_row = translations.get(f"{base_key}_NAME", {})
    desc_row = translations.get(f"{base_key}_DESC", {})
    desc2_row = translations.get(f"{base_key}2_DESC", {})

    return {
        "text_key": text_key,
        "ru_name": name_row.get("ru", ""),
        "ru_description": desc_row.get("ru", ""),
        "ru_upgraded_description": desc2_row.get("ru") or desc_row.get("ru", ""),
        "en_name": name_row.get("en", ""),
        "en_description": desc_row.get("en", ""),
        "en_upgraded_description": desc2_row.get("en") or desc_row.get("en", ""),
    }


def build_rule_entry(wiki_ability, manifest_row: dict[str, str] | None) -> dict:
    normal_attrs, upgraded_attrs = split_normal_upgraded(wiki_ability.attributes)
    kind = value_kind(wiki_ability.description)

    variants = {"normal": parse_attributes(normal_attrs)}
    variants["upgraded"] = parse_attributes(upgraded_attrs or normal_attrs)

    return {
        "wiki_name": wiki_ability.name,
        "class": wiki_ability.class_name,
        "description": wiki_ability.description,
        "value_kind": kind,
        "manifest": {
            "ability_id": manifest_row.get("ability_id", "") if manifest_row else "",
            "display_name": manifest_row.get("display_name", "") if manifest_row else "",
            "tool_class": manifest_row.get("tool_class", "") if manifest_row else "",
            "icon_label": manifest_row.get("icon_label", "") if manifest_row else "",
            "resolved_icon_label": manifest_row.get("resolved_icon_label", "") if manifest_row else "",
            "main_svg_id": manifest_row.get("main_svg_id", "") if manifest_row else "",
            "main_svg_filename": manifest_row.get("main_svg_filename", "") if manifest_row else "",
        },
        "variants": variants,
    }


def build_rules(wiki_url: str, manifest_path: Path, output_dir: Path, translations_path: Path | None) -> dict:
    wiki_abilities = parse_wiki_abilities(fetch_wiki_html(wiki_url))
    manifest = read_manifest(manifest_path)
    translations = read_translations(translations_path)

    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    index = {
        "source": wiki_url,
        "layout": "rules/wiki_active_abilities/<Class>/<FrameType>.json",
        "classes": {},
        "ability_lookup": {},
    }

    for wiki_ability in wiki_abilities:
        manifest_row = manifest.get(normalize_name(wiki_ability.name))
        entry = build_rule_entry(wiki_ability, manifest_row)

        for variant_name, variant_data in entry["variants"].items():
            frame_type = variant_data["frame_type"]
            class_name = safe_name(wiki_ability.class_name)
            grouped[class_name][frame_type].append(
                {
                    "wiki_name": entry["wiki_name"],
                    "class": entry["class"],
                    "variant": variant_name,
                    "description": entry["description"],
                    "value_kind": entry["value_kind"],
                    "translation": translation_block(manifest_row, translations),
                    "manifest": entry["manifest"],
                    "numbers": variant_data,
                }
            )

            lookup_key = manifest_row.get("ability_id") if manifest_row else normalize_name(wiki_ability.name)
            if lookup_key:
                index["ability_lookup"].setdefault(lookup_key, []).append(
                    {
                        "class": class_name,
                        "frame_type": frame_type,
                        "variant": variant_name,
                        "file": f"{class_name}/{frame_type}.json",
                    }
                )

    output_dir.mkdir(parents=True, exist_ok=True)
    for class_name, frame_groups in sorted(grouped.items()):
        index["classes"][class_name] = {}
        class_dir = output_dir / class_name
        class_dir.mkdir(parents=True, exist_ok=True)

        for frame_type, entries in sorted(frame_groups.items()):
            entries.sort(key=lambda item: (item["wiki_name"].lower(), item["variant"]))
            payload = {
                "source": wiki_url,
                "class": class_name,
                "frame_type": frame_type,
                "count": len(entries),
                "abilities": entries,
            }
            file_path = class_dir / f"{frame_type}.json"
            file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            index["classes"][class_name][frame_type] = {
                "file": f"{class_name}/{frame_type}.json",
                "count": len(entries),
            }

    (output_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build split JSON rule files from the wiki active ability table.")
    parser.add_argument("--wiki-url", default=WIKI_URL)
    parser.add_argument("--manifest", type=Path, default=Path("output") / "active_manifest.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("rules") / "wiki_active_abilities")
    parser.add_argument("--translations", type=Path, default=Path(r"H:\YouTube\Download\combined.csv"))
    args = parser.parse_args()

    index = build_rules(args.wiki_url, args.manifest.resolve(), args.output_dir.resolve(), args.translations.resolve())
    print(f"output={args.output_dir.resolve()}")
    print(f"classes={len(index['classes'])}")
    print(f"lookup_entries={len(index['ability_lookup'])}")


if __name__ == "__main__":
    main()
