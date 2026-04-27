from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from extract_active_manifest import DEFAULT_PROJECT_ROOT, find_section, iter_top_level_blocks, scalar


def first_scalar(section: str, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = scalar(section, key)
        if value:
            return value
    return ""


def build_numbers(project_root: Path, manifest_path: Path, output: Path) -> dict:
    manifest_ids = set()
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8-sig", newline="") as file:
            manifest_ids = {row["ability_id"] for row in csv.DictReader(file)}

    numbers = {}
    for path in sorted((project_root / "gpak-all" / "data" / "abilities").glob("*_abilities.gon")):
        for ability_id, block, _full_block in iter_top_level_blocks(path.read_text(encoding="utf-8")):
            if manifest_ids and ability_id not in manifest_ids:
                continue

            cost = find_section(block, "cost")
            damage_instance = find_section(block, "damage_instance")
            self_damage = find_section(block, "self_damage")
            numbers[ability_id] = {
                "mana": scalar(cost, "mana"),
                "move_points": scalar(cost, "move_points"),
                "act_points": scalar(cost, "act_points"),
                "damage": first_scalar(damage_instance, ("damage", "blocked_damage")),
                "heal": scalar(damage_instance, "heal"),
                "self_damage": scalar(self_damage, "damage"),
            }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(numbers, indent=2, ensure_ascii=False), encoding="utf-8")
    return numbers


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract active ability cost/damage numbers into JSON.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--manifest", type=Path, default=Path("output") / "active_manifest.csv")
    parser.add_argument("--output", type=Path, default=Path("rules") / "active_numbers.json")
    args = parser.parse_args()
    data = build_numbers(args.project_root.resolve(), args.manifest.resolve(), args.output.resolve())
    print(f"rows={len(data)}")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
