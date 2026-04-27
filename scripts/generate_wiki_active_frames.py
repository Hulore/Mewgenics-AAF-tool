from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.classify_active_abilities_from_wiki import prepare_frame_rules
from scripts.generate_from_rules import build_from_rules


DEFAULT_SHAPES_DIR = Path(
    r"H:\Mewgenics Projects\Passive Abilities Frame\OtherGameFiles\UnpackedImportant\Ability Passive Svg\shapes"
)

DEFAULT_FRAME_RULES = {
    "Dmg_Mana": Path("rules") / "active_frame_1_manual.json",
    "Xdmg_Mana": Path("rules") / "active_frame_2_manual.json",
    "Mana": Path("rules") / "active_frame_3_manual.json",
}

DEFAULT_TOP_ICON_RULES = Path("rules") / "active_type_icons.json"
DEFAULT_TOP_ICON_SHAPES_DIR = Path(
    r"H:\Mewgenics Projects\Active Abilities Frame\SVG Important\Svg Up Active Icons\shapes"
)

NUMBER_ICON_SOURCES = {
    "damage": Path(r"H:\Mewgenics Projects\Active Abilities Frame\SVG Important\Svg number icons\shapes\2762.svg"),
    "heal": Path(r"H:\Mewgenics Projects\Active Abilities Frame\SVG Important\Svg number icons\shapes\2763.svg"),
    "damage_or_heal": Path(r"H:\Mewgenics Projects\Active Abilities Frame\SVG Important\Svg number icons\shapes\2764.svg"),
}


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w\- ]+", "", value, flags=re.UNICODE).strip()
    value = re.sub(r"\s+", "_", value)
    return value or "active"


def load_frame_rules(frame_rules: dict[str, Path]) -> dict[str, tuple[dict, Path]]:
    loaded: dict[str, tuple[dict, Path]] = {}
    for frame_type, rules_path in frame_rules.items():
        resolved = rules_path.resolve()
        loaded[frame_type] = (prepare_frame_rules(resolved), resolved.parent)
    return loaded


def number_overrides(ability: dict) -> dict[str, dict]:
    numbers = ability.get("numbers") or {}
    overrides: dict[str, dict] = {
        "damage_number_text": {"text": numbers.get("value") or ""},
        "mana_number_text": {"text": numbers.get("mana") or ""},
    }

    if numbers.get("frame_type") == "Xdmg_Mana":
        overrides["damage_number_text"]["text"] = numbers.get("value") or numbers.get("raw") or ""

    value_kind = ability.get("value_kind") or ""
    icon_source = NUMBER_ICON_SOURCES.get(value_kind)
    if icon_source:
        overrides["damage_type_icon"] = {"source": str(icon_source)}

    return overrides


def load_top_icon_rules(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("abilities", {})


def ability_top_icon(ability: dict, top_icon_rules: dict[str, dict], top_icon_shapes_dir: Path) -> dict:
    manifest = ability.get("manifest") or {}
    ability_id = manifest.get("ability_id") or ""
    icon_data = top_icon_rules.get(ability_id)
    if not icon_data and ability_id.endswith("2"):
        icon_data = top_icon_rules.get(ability_id[:-1])
    if not icon_data:
        return {}

    svg_id = icon_data.get("top_icon_svg_id")
    if not svg_id:
        return {}

    return {
        "top_active_icon": {
            "source": str(top_icon_shapes_dir / f"{svg_id}.svg"),
            "rotation": 0,
        }
    }


def layer_overrides(ability: dict, top_icon_rules: dict[str, dict], top_icon_shapes_dir: Path) -> dict[str, dict]:
    overrides = number_overrides(ability)
    overrides.update(ability_top_icon(ability, top_icon_rules, top_icon_shapes_dir))
    return overrides


def generate(
    *,
    rules_dir: Path,
    shapes_dir: Path,
    output_dir: Path,
    frame_rules: dict[str, Path],
    top_icon_rules_path: Path,
    top_icon_shapes_dir: Path,
) -> tuple[int, list[str], dict[str, int]]:
    loaded_rules = load_frame_rules(frame_rules)
    top_icon_rules = load_top_icon_rules(top_icon_rules_path)
    generated = 0
    errors: list[str] = []
    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    for ability_file in sorted(rules_dir.glob("*/*.json")):
        data = json.loads(ability_file.read_text(encoding="utf-8"))
        frame_type = data["frame_type"]
        if frame_type not in loaded_rules:
            errors.append(f"{ability_file}: no frame rules for {frame_type}")
            continue

        frame_rules_data, frame_rules_dir = loaded_rules[frame_type]
        for ability in data.get("abilities", []):
            manifest = ability.get("manifest") or {}
            main_svg_id = manifest.get("main_svg_id")
            ability_id = manifest.get("ability_id") or ability.get("wiki_name") or "ability"
            if not main_svg_id:
                errors.append(f"{ability_id}: missing main_svg_id")
                continue

            main_svg = shapes_dir / f"{main_svg_id}.svg"
            if not main_svg.exists():
                errors.append(f"{ability_id}: missing {main_svg}")
                continue

            class_name = (manifest.get("tool_class") or ability.get("class") or "colorless").lower()
            wiki_class = safe_name(ability.get("class") or class_name)
            variant = safe_name(ability.get("variant") or "normal")
            output_name = f"{safe_name(ability.get('wiki_name') or ability_id)}_{safe_name(ability_id)}_{variant}.svg"
            output_svg = output_dir / wiki_class / frame_type / variant / output_name

            try:
                build_from_rules(
                    deepcopy(frame_rules_data),
                    frame_rules_dir,
                    main_svg.resolve(),
                    class_name,
                    output_svg.resolve(),
                    layer_overrides(ability, top_icon_rules, top_icon_shapes_dir),
                )
            except Exception as exc:
                errors.append(f"{ability_id} [{frame_type}/{variant}]: {exc}")
                continue

            generated += 1
            counts[frame_type] = counts.get(frame_type, 0) + 1
            rows.append(
                {
                    "class": ability.get("class") or "",
                    "frame_type": frame_type,
                    "variant": ability.get("variant") or "",
                    "wiki_name": ability.get("wiki_name") or "",
                    "ability_id": ability_id,
                    "main_svg_id": main_svg_id,
                    "value_kind": ability.get("value_kind") or "",
                    "value": str((ability.get("numbers") or {}).get("value") or ""),
                    "mana": str((ability.get("numbers") or {}).get("mana") or ""),
                    "top_icon_type": (top_icon_rules.get(ability_id) or {}).get("type_icon", ""),
                    "top_icon_svg_id": (top_icon_rules.get(ability_id) or {}).get("top_icon_svg_id", ""),
                    "output_svg": str(output_svg),
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "generation_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as file:
        fieldnames = [
            "class",
            "frame_type",
            "variant",
            "wiki_name",
            "ability_id",
            "main_svg_id",
            "value_kind",
            "value",
            "mana",
            "top_icon_type",
            "top_icon_svg_id",
            "output_svg",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    errors_path = output_dir / "generation_errors.txt"
    errors_path.write_text("\n".join(errors) + ("\n" if errors else ""), encoding="utf-8")
    return generated, errors, counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate framed active ability SVGs from wiki ability rule JSON.")
    parser.add_argument("--rules-dir", type=Path, default=Path("rules") / "wiki_active_abilities")
    parser.add_argument("--shapes-dir", type=Path, default=DEFAULT_SHAPES_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "wiki_active_frames_framed")
    parser.add_argument("--dmg-mana-rules", type=Path, default=DEFAULT_FRAME_RULES["Dmg_Mana"])
    parser.add_argument("--xdmg-mana-rules", type=Path, default=DEFAULT_FRAME_RULES["Xdmg_Mana"])
    parser.add_argument("--mana-rules", type=Path, default=DEFAULT_FRAME_RULES["Mana"])
    parser.add_argument("--top-icon-rules", type=Path, default=DEFAULT_TOP_ICON_RULES)
    parser.add_argument("--top-icon-shapes-dir", type=Path, default=DEFAULT_TOP_ICON_SHAPES_DIR)
    args = parser.parse_args()

    generated, errors, counts = generate(
        rules_dir=args.rules_dir.resolve(),
        shapes_dir=args.shapes_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        frame_rules={
            "Dmg_Mana": args.dmg_mana_rules,
            "Xdmg_Mana": args.xdmg_mana_rules,
            "Mana": args.mana_rules,
        },
        top_icon_rules_path=args.top_icon_rules.resolve(),
        top_icon_shapes_dir=args.top_icon_shapes_dir.resolve(),
    )

    print(f"generated={generated} errors={len(errors)}")
    print(f"output={args.output_dir.resolve()}")
    for frame_type, count in sorted(counts.items()):
        print(f"{frame_type}={count}")
    if errors:
        print("errors:")
        for error in errors[:50]:
            print(error)


if __name__ == "__main__":
    main()
