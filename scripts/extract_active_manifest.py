from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_PROJECT_ROOT = Path(r"H:\Mewgenics Projects\Passive Abilities Frame")
DEFAULT_UNPACKED_ROOT = DEFAULT_PROJECT_ROOT / "OtherGameFiles" / "UnpackedImportant"

SKIP_ABILITY_FILES = {
    "util_abilities.gon",
    "test_abilities.gon",
}

CLASS_ALIASES = {
    "medic": "cleric",
    "colorless": "colorless",
    "collarless": "colorless",
}


def normalize_tool_class(source_class: str) -> str:
    key = source_class.strip().lower()
    return CLASS_ALIASES.get(key, key)


def strip_comments(text: str) -> str:
    return re.sub(r"//.*", "", text)


def iter_top_level_blocks(text: str):
    text = strip_comments(text)
    index = 0
    length = len(text)
    while index < length:
        match = re.search(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)\s*\{", text[index:])
        if not match:
            return

        name = match.group(1)
        start = index + match.start()
        open_brace = index + match.end() - 1
        depth = 0
        cursor = open_brace
        in_string = False
        escaped = False
        while cursor < length:
            char = text[cursor]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        yield name, text[open_brace + 1 : cursor], text[start:cursor + 1]
                        index = cursor + 1
                        break
            cursor += 1
        else:
            return


def find_section(block: str, name: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*\{{", block)
    if not match:
        return ""

    open_brace = match.end() - 1
    depth = 0
    for cursor in range(open_brace, len(block)):
        char = block[cursor]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return block[open_brace + 1 : cursor]
    return ""


def scalar(section: str, key: str) -> str:
    quoted = re.search(rf'(?m)^\s*{re.escape(key)}\s+"([^"]*)"', section)
    if quoted:
        return quoted.group(1)
    bare = re.search(rf"(?m)^\s*{re.escape(key)}\s+([A-Za-z_][A-Za-z0-9_]*)", section)
    return bare.group(1) if bare else ""


def read_names(path: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.reader(file):
            if len(row) >= 2:
                names[row[0]] = row[1]
    return names


def extract_ability_icon_map(frames_xml: Path) -> dict[str, dict[str, int]]:
    root = ET.parse(frames_xml).getroot()
    sprite = None
    for item in root.find("tags").findall("item"):
        if item.get("type") == "DefineSpriteTag" and item.get("spriteId") == "1346":
            sprite = item
            break
    if sprite is None:
        raise KeyError("DefineSprite 1346 / AbilityIcon was not found.")

    icon_map: dict[str, dict[str, int]] = {}
    frame = 1
    display: dict[int, int] = {}
    pending_labels: list[str] = []
    pending_character_id = 0

    for item in sprite.find("subTags").findall("item"):
        item_type = item.get("type")
        if item_type == "FrameLabelTag":
            label = item.get("name") or ""
            if label:
                pending_labels.append(label)
                pending_character_id = 0
        elif item_type == "PlaceObject2Tag":
            depth = int(item.get("depth") or 0)
            if item.get("placeFlagHasCharacter") == "true":
                character_id = int(item.get("characterId") or 0)
                display[depth] = character_id
                if pending_labels:
                    pending_character_id = character_id
        elif item_type == "RemoveObject2Tag":
            display.pop(int(item.get("depth") or 0), None)
        elif item_type == "ShowFrameTag":
            main_svg_id = pending_character_id or display.get(3)
            for label in pending_labels:
                if label != "unknown":
                    icon_map[label] = {
                        "icon_frame": frame,
                        "main_svg_id": main_svg_id or 0,
                    }
            pending_labels = []
            pending_character_id = 0
            frame += 1

    return icon_map


def iter_active_defs(abilities_dir: Path):
    for path in sorted(abilities_dir.glob("*_abilities.gon")):
        if path.name in SKIP_ABILITY_FILES:
            continue

        for ability_id, block, full_block in iter_top_level_blocks(path.read_text(encoding="utf-8")):
            meta = find_section(block, "meta")
            graphics = find_section(block, "graphics")
            name_key = scalar(meta, "name")
            source_class = scalar(meta, "class")
            type_icon = scalar(meta, "type_icon")
            ability_icon = scalar(graphics, "ability_icon") or scalar(meta, "ability_icon")
            variant_of = scalar(block, "variant_of")
            template = scalar(block, "template")
            cut = "CUT" in full_block.splitlines()[0]

            if not name_key and not source_class and not ability_icon:
                continue

            yield {
                "ability_id": ability_id,
                "icon_label": ability_icon or ability_id,
                "text_key": name_key,
                "source_class": source_class,
                "tool_class": normalize_tool_class(source_class) if source_class else "colorless",
                "type_icon": type_icon,
                "ability_icon_override": ability_icon,
                "variant_of": variant_of,
                "template": template,
                "source_file": path.name,
                "cut": cut,
            }


def build_manifest(project_root: Path, unpacked_root: Path, output: Path) -> tuple[int, int, int, Counter]:
    icon_map = extract_ability_icon_map(unpacked_root / "DefineSprite(AbilityIcon)" / "frames.xml")
    names = {}
    text_dir = project_root / "gpak-all" / "data" / "text"
    for text_file in ("abilities.csv", "enemy_abilities.csv", "items.csv"):
        path = text_dir / text_file
        if path.exists():
            names.update(read_names(path))

    rows = []
    missing = 0
    cut = 0
    for ability in iter_active_defs(project_root / "gpak-all" / "data" / "abilities"):
        if ability["cut"]:
            cut += 1
            continue

        fallback_labels = [
            ability["icon_label"],
            ability["variant_of"],
            re.sub(r"\d+$", "", ability["ability_id"]),
        ]
        icon = None
        resolved_label = ability["icon_label"]
        for fallback_label in fallback_labels:
            if fallback_label and fallback_label in icon_map:
                icon = icon_map[fallback_label]
                resolved_label = fallback_label
                break
        main_svg_id = icon["main_svg_id"] if icon else 0
        if not main_svg_id:
            missing += 1

        rows.append(
            {
                **ability,
                "display_name": names.get(ability["text_key"], ""),
                "resolved_icon_label": resolved_label if icon else "",
                "icon_frame": icon["icon_frame"] if icon else "",
                "main_svg_id": main_svg_id or "",
                "main_svg_filename": f"{main_svg_id}.svg" if main_svg_id else "",
            }
        )

    fieldnames = [
        "ability_id",
        "display_name",
        "text_key",
        "source_class",
        "tool_class",
        "type_icon",
        "ability_icon_override",
        "variant_of",
        "template",
        "icon_label",
        "resolved_icon_label",
        "icon_frame",
        "main_svg_id",
        "main_svg_filename",
        "source_file",
        "cut",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows), missing, cut, Counter(row["source_class"] or "Colorless" for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract active ability -> class -> SVG manifest.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--unpacked-root", type=Path, default=DEFAULT_UNPACKED_ROOT)
    parser.add_argument("--output", type=Path, default=Path("output") / "active_manifest.csv")
    args = parser.parse_args()

    rows, missing, cut, by_class = build_manifest(
        args.project_root.resolve(),
        args.unpacked_root.resolve(),
        args.output.resolve(),
    )
    print(f"rows={rows} missing={missing} cut={cut}")
    print(f"output={args.output.resolve()}")
    print("by_class=" + ", ".join(f"{key}:{value}" for key, value in sorted(by_class.items())))


if __name__ == "__main__":
    main()
