from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from build_wiki_active_ability_rules import read_translations, translation_block
from classify_active_abilities_from_wiki import normalize_name
from extract_active_manifest import normalize_tool_class


MANIFEST_FIELDS = [
    "ability_id",
    "display_name",
    "tool_class",
    "icon_label",
    "resolved_icon_label",
    "main_svg_id",
    "main_svg_filename",
]


def read_manifest_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def build_index(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        for value in (
            row.get("display_name", ""),
            row.get("ability_id", ""),
            row.get("icon_label", ""),
            row.get("resolved_icon_label", ""),
        ):
            key = normalize_name(value)
            if key and row not in index[key]:
                index[key].append(row)
    return index


def pick_manifest_row(candidates: list[dict[str, str]], class_name: str) -> dict[str, str] | None:
    if not candidates:
        return None
    wanted_class = normalize_tool_class(class_name)
    class_matches = [row for row in candidates if normalize_tool_class(row.get("tool_class", "")) == wanted_class]
    if class_matches:
        return class_matches[0]
    return candidates[0]


def update_rules(rules_dir: Path, manifest_path: Path) -> tuple[int, int]:
    rows = read_manifest_rows(manifest_path)
    index = build_index(rows)
    touched_files = 0
    updated_abilities = 0

    for path in sorted(rules_dir.glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        class_name = data.get("class") or path.parent.name

        for ability in data.get("abilities", []):
            keys = [
                normalize_name(ability.get("wiki_name", "")),
                normalize_name(ability.get("manifest", {}).get("ability_id", "")),
            ]
            row = None
            for key in keys:
                row = pick_manifest_row(index.get(key, []), class_name)
                if row:
                    break
            if not row:
                continue

            current = ability.setdefault("manifest", {})
            replacement = {field: row.get(field, "") for field in MANIFEST_FIELDS}
            if any(current.get(field, "") != replacement[field] for field in MANIFEST_FIELDS):
                current.update(replacement)
                changed = True
                updated_abilities += 1

        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            touched_files += 1

    return touched_files, updated_abilities


def update_rules_with_translations(
    rules_dir: Path,
    manifest_path: Path,
    translations_path: Path | None,
) -> tuple[int, int]:
    rows = read_manifest_rows(manifest_path)
    index = build_index(rows)
    translations = read_translations(translations_path)
    touched_files = 0
    updated_abilities = 0

    for path in sorted(rules_dir.glob("*/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        class_name = data.get("class") or path.parent.name

        for ability in data.get("abilities", []):
            keys = [
                normalize_name(ability.get("wiki_name", "")),
                normalize_name(ability.get("manifest", {}).get("ability_id", "")),
            ]
            row = None
            for key in keys:
                row = pick_manifest_row(index.get(key, []), class_name)
                if row:
                    break
            if not row:
                continue

            current = ability.setdefault("manifest", {})
            replacement = {field: row.get(field, "") for field in MANIFEST_FIELDS}
            new_translation = translation_block(row, translations)
            if (
                any(current.get(field, "") != replacement[field] for field in MANIFEST_FIELDS)
                or ability.get("translation") != new_translation
            ):
                current.update(replacement)
                ability["translation"] = new_translation
                changed = True
                updated_abilities += 1

        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            touched_files += 1

    return touched_files, updated_abilities


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh wiki rule manifest fields from active_manifest.csv.")
    parser.add_argument("--rules-dir", type=Path, default=Path("rules") / "wiki_active_abilities")
    parser.add_argument("--manifest", type=Path, default=Path("output") / "active_manifest.csv")
    parser.add_argument("--translations", type=Path, default=Path(r"H:\YouTube\Download\combined.csv"))
    args = parser.parse_args()

    touched_files, updated_abilities = update_rules_with_translations(
        args.rules_dir.resolve(),
        args.manifest.resolve(),
        args.translations.resolve(),
    )
    print(f"touched_files={touched_files} updated_abilities={updated_abilities}")


if __name__ == "__main__":
    main()
