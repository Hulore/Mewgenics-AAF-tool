from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_from_rules import build


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w\- ]+", "", value, flags=re.UNICODE).strip()
    value = re.sub(r"\s+", "_", value)
    return value or "active"


def generate_all(
    manifest_path: Path,
    shapes_dir: Path,
    rules_path: Path,
    output_dir: Path,
) -> tuple[list[Path], list[str]]:
    generated: list[Path] = []
    errors: list[str] = []

    with manifest_path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if not row.get("main_svg_id"):
                errors.append(f"{row['ability_id']}: missing main_svg_id")
                continue

            main_svg = shapes_dir / f"{row['main_svg_id']}.svg"
            if not main_svg.exists():
                errors.append(f"{row['ability_id']}: missing {main_svg}")
                continue

            class_name = row.get("tool_class") or "colorless"
            display_name = safe_name(row.get("display_name") or row["ability_id"])
            output = output_dir / class_name / f"{display_name}_{row['ability_id']}.svg"

            try:
                build(rules_path, main_svg, class_name, output)
            except Exception as exc:
                errors.append(f"{row['ability_id']}: {exc}")
                continue

            generated.append(output)

    return generated, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate active ability icons from active_manifest.csv.")
    parser.add_argument("--manifest", type=Path, default=Path("output") / "active_manifest.csv")
    parser.add_argument(
        "--shapes-dir",
        type=Path,
        default=Path(r"H:\Mewgenics Projects\Passive Abilities Frame\OtherGameFiles\UnpackedImportant\Ability Passive Svg\shapes"),
    )
    parser.add_argument("--rules", type=Path, default=Path("rules") / "active_manual.json")
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "all_actives")
    args = parser.parse_args()

    generated, errors = generate_all(
        args.manifest.resolve(),
        args.shapes_dir.resolve(),
        args.rules.resolve(),
        args.output_dir.resolve(),
    )

    print(f"generated={len(generated)} errors={len(errors)}")
    print(f"output={args.output_dir.resolve()}")
    if errors:
        print("errors:")
        for error in errors[:30]:
            print(error)


if __name__ == "__main__":
    main()
