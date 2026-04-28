from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path


def ability_key(ability: dict) -> tuple[str, str]:
    return (ability.get("class") or "", ability.get("wiki_name") or "")


def ensure_upgraded(rules_dir: Path) -> tuple[int, int]:
    files = sorted(rules_dir.glob("*/*.json"))
    by_key: dict[tuple[str, str], set[str]] = {}
    normal_entries: dict[tuple[str, str], tuple[Path, dict]] = {}

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        for ability in data.get("abilities", []):
            key = ability_key(ability)
            variant = ability.get("variant") or ""
            by_key.setdefault(key, set()).add(variant)
            if variant == "normal":
                normal_entries.setdefault(key, (path, ability))

    added_by_file: dict[Path, list[dict]] = {}
    for key, variants in by_key.items():
        if "normal" not in variants or "upgraded" in variants:
            continue
        path, normal = normal_entries[key]
        upgraded = deepcopy(normal)
        upgraded["variant"] = "upgraded"
        added_by_file.setdefault(path, []).append(upgraded)

    for path, additions in added_by_file.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        data["abilities"].extend(additions)
        data["abilities"].sort(key=lambda item: (item.get("wiki_name", "").lower(), item.get("variant", "")))
        data["count"] = len(data["abilities"])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return len(added_by_file), sum(len(items) for items in added_by_file.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure every wiki active ability has an upgraded rule entry.")
    parser.add_argument("--rules-dir", type=Path, default=Path("rules") / "wiki_active_abilities")
    args = parser.parse_args()

    touched_files, added_entries = ensure_upgraded(args.rules_dir.resolve())
    print(f"touched_files={touched_files} added_entries={added_entries}")


if __name__ == "__main__":
    main()
