from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_from_rules import build_from_rules


DEFAULT_SHAPES_DIR = Path(
    r"H:\Mewgenics Projects\Passive Abilities Frame\OtherGameFiles\UnpackedImportant\Ability Passive Svg\shapes"
)
DEFAULT_BUTCHER_GON = Path(
    r"H:\Mewgenics Projects\Passive Abilities Frame\gpak-all\data\abilities\butcher_abilities.gon"
)


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w\- ]+", "", value, flags=re.UNICODE).strip()
    value = re.sub(r"\s+", "_", value)
    return value or "active"


def read_top_level_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    pattern = re.compile(r"(?m)^([A-Za-z_][\w]*)\s*\{")
    index = 0
    while True:
        match = pattern.search(text, index)
        if not match:
            break

        name = match.group(1)
        body_start = match.end()
        depth = 1
        pos = body_start
        while pos < len(text) and depth:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1

        blocks[name] = text[body_start : pos - 1]
        index = pos

    return blocks


def named_blocks(text: str, name: str) -> list[str]:
    blocks: list[str] = []
    pattern = re.compile(rf"(?m)^\s*{re.escape(name)}\s*\{{")
    index = 0
    while True:
        match = pattern.search(text, index)
        if not match:
            break

        body_start = match.end()
        depth = 1
        pos = body_start
        while pos < len(text) and depth:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
            pos += 1

        blocks.append(text[body_start : pos - 1])
        index = pos

    return blocks


def first_value(text: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s+(.+?)\s*$", text)
    if not match:
        return ""
    return match.group(1).strip().strip('"')


def direct_numbers(body: str) -> dict[str, str]:
    cost_blocks = named_blocks(body, "cost")
    damage_blocks = named_blocks(body, "damage_instance")

    data = {
        "mana": "",
        "damage": "",
        "heal": "",
        "variant_of": first_value(body, "variant_of"),
    }

    for block in cost_blocks:
        data["mana"] = first_value(block, "mana") or data["mana"]

    for block in damage_blocks:
        data["damage"] = first_value(block, "damage") or data["damage"]
        data["heal"] = first_value(block, "heal") or data["heal"]

    return data


def effective_numbers(block_data: dict[str, dict[str, str]], ability_id: str) -> dict[str, str]:
    @lru_cache(maxsize=None)
    def resolve(current: str) -> tuple[str, str, str]:
        data = block_data.get(current, {})
        inherited = ("", "", "")
        parent = data.get("variant_of", "")
        if parent:
            inherited = resolve(parent)

        mana = data.get("mana") or inherited[0]
        damage = data.get("damage") or inherited[1]
        heal = data.get("heal") or inherited[2]
        return mana, damage, heal

    mana, damage, heal = resolve(ability_id)
    return {"mana": mana, "damage": damage, "heal": heal}


def prepare_frame_rules(rules_path: Path, main_layer: dict, class_color: str) -> dict:
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rules["classes"] = {"butcher": {"color": class_color}}

    layers = []
    inserted_main = False
    for layer in rules["layers"]:
        layer = dict(layer)
        if layer["source"] != "$main":
            layer["recolor"] = {"#111111": "$classColor"}
        layers.append(layer)

        if layer["id"] == "class_body":
            layers.append(dict(main_layer))
            inserted_main = True

    if not inserted_main:
        layers.append(dict(main_layer))

    rules["layers"] = layers
    return rules


def generate_split(
    manifest_path: Path,
    butcher_gon: Path,
    shapes_dir: Path,
    frame_rules_path: Path,
    output_dir: Path,
    class_color: str,
    main_x: float,
    main_y: float,
    main_scale: float,
) -> dict[str, int]:
    gon_text = butcher_gon.read_text(encoding="utf-8")
    block_data = {name: direct_numbers(body) for name, body in read_top_level_blocks(gon_text).items()}

    damage_dir = output_dir / "damage_or_heal_and_mana"
    mana_only_dir = output_dir / "mana_only"
    framed_dir = damage_dir / "framed"
    damage_source_dir = damage_dir / "source_svgs"
    mana_source_dir = mana_only_dir / "source_svgs"

    for directory in (framed_dir, damage_source_dir, mana_source_dir):
        directory.mkdir(parents=True, exist_ok=True)

    main_layer = {
        "id": "main_picture",
        "label": "Main picture",
        "source": "$main",
        "x": main_x,
        "y": main_y,
        "scaleX": main_scale,
        "scaleY": main_scale,
        "rotation": 0,
        "visible": True,
    }
    frame_rules = prepare_frame_rules(frame_rules_path, main_layer, class_color)

    rows: list[dict[str, str]] = []
    counts = {"damage_or_heal_and_mana": 0, "mana_only": 0, "skipped": 0, "framed": 0}

    with manifest_path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if (row.get("tool_class") or "").lower() != "butcher":
                continue
            if row.get("cut", "").lower() == "true":
                continue

            ability_id = row["ability_id"]
            numbers = effective_numbers(block_data, ability_id)
            has_mana = bool(numbers["mana"])
            has_damage_or_heal = bool(numbers["damage"] or numbers["heal"])

            if has_mana and has_damage_or_heal:
                group = "damage_or_heal_and_mana"
                target_source_dir = damage_source_dir
                counts[group] += 1
            elif has_mana:
                group = "mana_only"
                target_source_dir = mana_source_dir
                counts[group] += 1
            else:
                group = "skipped"
                counts[group] += 1

            source_svg = shapes_dir / f"{row['main_svg_id']}.svg" if row.get("main_svg_id") else None
            output_name = f"{safe_name(row.get('display_name') or ability_id)}_{ability_id}.svg"
            source_output = ""
            framed_output = ""

            if group != "skipped" and source_svg and source_svg.exists():
                source_output_path = target_source_dir / output_name
                shutil.copy2(source_svg, source_output_path)
                source_output = str(source_output_path)

                if group == "damage_or_heal_and_mana":
                    framed_output_path = framed_dir / output_name
                    build_from_rules(
                        frame_rules,
                        frame_rules_path.parent.resolve(),
                        source_svg.resolve(),
                        "butcher",
                        framed_output_path.resolve(),
                    )
                    framed_output = str(framed_output_path)
                    counts["framed"] += 1

            rows.append(
                {
                    "ability_id": ability_id,
                    "display_name": row.get("display_name") or "",
                    "main_svg_id": row.get("main_svg_id") or "",
                    "mana": numbers["mana"],
                    "damage": numbers["damage"],
                    "heal": numbers["heal"],
                    "group": group,
                    "source_svg": source_output,
                    "framed_svg": framed_output,
                }
            )

    manifest_output = output_dir / "butcher_split_manifest.csv"
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    with manifest_output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ability_id",
                "display_name",
                "main_svg_id",
                "mana",
                "damage",
                "heal",
                "group",
                "source_svg",
                "framed_svg",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Split butcher active ability SVGs by number slots.")
    parser.add_argument("--manifest", type=Path, default=Path("output") / "active_manifest.csv")
    parser.add_argument("--butcher-gon", type=Path, default=DEFAULT_BUTCHER_GON)
    parser.add_argument("--shapes-dir", type=Path, default=DEFAULT_SHAPES_DIR)
    parser.add_argument("--frame-rules", type=Path, default=Path("rules") / "active_frame_1_manual.json")
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "butcher_active_split")
    parser.add_argument("--class-color", default="#8a3746")
    parser.add_argument("--main-x", type=float, default=24)
    parser.add_argument("--main-y", type=float, default=22)
    parser.add_argument("--main-scale", type=float, default=1)
    args = parser.parse_args()

    counts = generate_split(
        args.manifest.resolve(),
        args.butcher_gon.resolve(),
        args.shapes_dir.resolve(),
        args.frame_rules.resolve(),
        args.output_dir.resolve(),
        args.class_color,
        args.main_x,
        args.main_y,
        args.main_scale,
    )

    print(f"output={args.output_dir.resolve()}")
    for key, value in counts.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
