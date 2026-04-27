from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_GON_DIRS = [
    Path(r"H:\Mewgenics Projects\Passive Abilities Frame\gpak-all\data\ability_templates"),
    Path(r"H:\Mewgenics Projects\Passive Abilities Frame\gpak-all\data\abilities"),
]

TYPE_ICON_SHAPES = {
    "melee": 2777,
    "movement": 2779,
    "defense": 2781,
    "misc": 2783,
    "heal": 2785,
    "ranged": 2787,
    "debuff": 2789,
    "buff": 2791,
    "spawn": 2793,
    "magic": 2795,
    "unknown": 2797,
}

TYPE_ICON_ALIASES = {
    "attack": "melee",
    "move": "movement",
}

TEMPLATE_TYPE_ICONS = {
    "template_move": "movement",
    "template_teleport": "movement",
    "template_swap": "movement",
    "template_jump_move": "movement",
    "template_leave": "movement",
    "template_return": "movement",
    "template_melee_attack": "melee",
    "template_melee_spell": "melee",
    "template_dash_attack": "melee",
    "template_trample_dash": "melee",
    "template_jump_attack": "melee",
    "template_throw_attack": "melee",
    "template_tile_targeted_melee_attack": "melee",
    "template_ranged_attack": "ranged",
    "template_lobbed_attack": "ranged",
    "template_straightshot_attack": "ranged",
    "template_spell": "magic",
    "template_laser": "magic",
    "template_self_buff": "buff",
    "template_multihit_self_buff": "buff",
    "template_targeted_status": "debuff",
    "template_spawn": "spawn",
    "template_placeholder": "unknown",
}


def strip_line_comment(line: str) -> str:
    in_quote = False
    escaped = False
    for index, char in enumerate(line):
        if char == "\\" and not escaped:
            escaped = True
            continue
        if char == '"' and not escaped:
            in_quote = not in_quote
        if not in_quote and line[index : index + 2] == "//":
            return line[:index]
        escaped = False
    return line


def parse_gon_blocks(path: Path) -> dict[str, dict[str, str]]:
    blocks: dict[str, dict[str, str]] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    depth = 0

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = strip_line_comment(raw_line)
        if current_name is None:
            match = re.match(r"^\s*([A-Za-z_][\w]*)\s*\{", line)
            if not match:
                continue
            current_name = match.group(1)
            current_lines = [line]
            depth = line.count("{") - line.count("}")
            if depth <= 0:
                blocks[current_name] = parse_block(current_lines, path)
                current_name = None
            continue

        current_lines.append(line)
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            blocks[current_name] = parse_block(current_lines, path)
            current_name = None

    return blocks


def parse_block(lines: list[str], path: Path) -> dict[str, str]:
    text = "\n".join(lines)
    data = {"source_file": str(path)}

    for key in ("template", "variant_of", "type_icon"):
        match = re.search(rf"^\s*{key}\s+\"?([A-Za-z_][\w]*)\"?", text, flags=re.MULTILINE)
        if match:
            data[key] = match.group(1)

    return data


def normalize_type_icon(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return TYPE_ICON_ALIASES.get(value, value)


def template_key(value: str | None) -> str | None:
    if not value:
        return None
    return value if value.startswith("template_") else f"template_{value}"


def resolve_type_icon(name: str, blocks: dict[str, dict[str, str]], stack: tuple[str, ...] = ()) -> str | None:
    if name in stack:
        return None
    block = blocks.get(name)
    if not block:
        return None

    direct = normalize_type_icon(block.get("type_icon"))
    if direct:
        return direct

    template_default = TEMPLATE_TYPE_ICONS.get(name)
    if template_default:
        return template_default

    inherited = block.get("variant_of")
    if inherited:
        resolved = resolve_type_icon(inherited, blocks, stack + (name,))
        if resolved:
            return resolved

    tmpl = template_key(block.get("template"))
    if tmpl:
        resolved = resolve_type_icon(tmpl, blocks, stack + (name,))
        if resolved:
            return resolved

    return None


def build(gon_dirs: list[Path], output: Path) -> dict:
    blocks: dict[str, dict[str, str]] = {}
    for gon_dir in gon_dirs:
        for path in sorted(gon_dir.glob("*.gon")):
            blocks.update(parse_gon_blocks(path))

    abilities = {}
    for name, block in sorted(blocks.items()):
        if name.startswith("template_"):
            continue
        type_icon = resolve_type_icon(name, blocks) or "unknown"
        shape_id = TYPE_ICON_SHAPES.get(type_icon, TYPE_ICON_SHAPES["unknown"])
        abilities[name] = {
            "type_icon": type_icon,
            "top_icon_svg_id": str(shape_id),
            "top_icon_svg": f"{shape_id}.svg",
            "source_file": block.get("source_file", ""),
        }

    payload = {
        "source": [str(path) for path in gon_dirs],
        "type_icon_shapes": {key: str(value) for key, value in TYPE_ICON_SHAPES.items()},
        "aliases": TYPE_ICON_ALIASES,
        "abilities": abilities,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build active ability top icon mapping from game GON files.")
    parser.add_argument("--gon-dir", action="append", type=Path, dest="gon_dirs")
    parser.add_argument("--output", type=Path, default=Path("rules") / "active_type_icons.json")
    args = parser.parse_args()

    payload = build(args.gon_dirs or DEFAULT_GON_DIRS, args.output)
    print(f"output={args.output.resolve()}")
    print(f"abilities={len(payload['abilities'])}")
    counts: dict[str, int] = {}
    for item in payload["abilities"].values():
        counts[item["type_icon"]] = counts.get(item["type_icon"], 0) + 1
    for type_icon, count in sorted(counts.items()):
        print(f"{type_icon}={count}")


if __name__ == "__main__":
    main()
