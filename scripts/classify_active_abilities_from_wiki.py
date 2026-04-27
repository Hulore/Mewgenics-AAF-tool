from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_from_rules import build_from_rules


WIKI_URL = "https://mewgenics.wiki.gg/wiki/Abilities"
DEFAULT_SHAPES_DIR = Path(
    r"H:\Mewgenics Projects\Passive Abilities Frame\OtherGameFiles\UnpackedImportant\Ability Passive Svg\shapes"
)

FRAME_FOLDER_NAMES = {
    "mana": "Mana",
    "damage_mana": "Dmg_Mana",
    "multi_damage_mana": "Xdmg_Mana",
    "unknown": "Unknown",
}


class WikiTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.table_depth = 0
        self.in_cell = False
        self.cell: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []
        self.tables: list[list[list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table" and "wikitable" in (attrs_dict.get("class") or ""):
            self.in_table = True
            self.table_depth = 1
            self.rows = []
        elif self.in_table and tag == "table":
            self.table_depth += 1
        elif self.in_table and tag == "tr":
            self.row = []
        elif self.in_table and tag in ("td", "th"):
            self.in_cell = True
            self.cell = []

        if self.in_cell and tag == "br":
            self.cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in ("td", "th") and self.in_cell:
            self.row.append(clean_text("".join(self.cell)))
            self.in_cell = False
        elif self.in_table and tag == "tr":
            if self.row:
                self.rows.append(self.row)
        elif self.in_table and tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.tables.append(self.rows)
                self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell.append(data)


@dataclass
class WikiAbility:
    name: str
    class_name: str
    description: str
    attributes: str


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u2060", "")).strip()


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w\- ]+", "", value, flags=re.UNICODE).strip()
    value = re.sub(r"\s+", "_", value)
    return value or "active"


def normalize_name(value: str) -> str:
    value = value.lower()
    value = value.replace("&", "and")
    value = re.sub(r"\(.*?\)", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def fetch_wiki_html(url: str) -> str:
    request = Request(url, headers={"User-Agent": "MewgenicsAAFTool/0.1"})
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def parse_wiki_abilities(html: str) -> list[WikiAbility]:
    parser = WikiTableParser()
    parser.feed(html)
    for table in parser.tables:
        if not table or table[0] != ["Icon", "Name", "Class", "Type", "Description", "Attributes"]:
            continue

        abilities: list[WikiAbility] = []
        for row in table[1:]:
            if len(row) < 6 or row[3] != "Active":
                continue
            abilities.append(
                WikiAbility(
                    name=row[1],
                    class_name=row[2],
                    description=row[4],
                    attributes=row[5],
                )
            )
        return abilities

    raise RuntimeError("Could not find the Abilities wiki table.")


def split_normal_upgraded(attributes: str) -> tuple[str, str]:
    attributes = clean_text(attributes)
    if "Upgraded:" not in attributes:
        return attributes, ""
    normal, upgraded = attributes.split("Upgraded:", 1)
    return normal.strip(), upgraded.strip()


def classify_attributes(attributes: str) -> str:
    attributes = clean_text(attributes)
    if not attributes:
        return "unknown"

    tokens = attributes.split()
    damage_tokens = [token for token in tokens if re.fullmatch(r"\d+\s*x\s*[\d?]+", token, flags=re.IGNORECASE)]
    if damage_tokens:
        return "multi_damage_mana"

    numeric_tokens = [
        token
        for token in tokens
        if re.fullmatch(r"(?:\d+|X|All|N/A)", token, flags=re.IGNORECASE)
        or re.fullmatch(r"\d+(?:\+\w+|\-\w+)?", token)
    ]

    if len(numeric_tokens) >= 2:
        return "damage_mana"
    if len(numeric_tokens) == 1:
        return "mana"
    return "unknown"


def read_manifest(manifest_path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with manifest_path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            keys = {
                normalize_name(row.get("display_name") or ""),
                normalize_name(row.get("ability_id") or ""),
                normalize_name(row.get("icon_label") or ""),
                normalize_name(row.get("resolved_icon_label") or ""),
            }
            for key in keys:
                if key:
                    rows.setdefault(key, row)
    return rows


def load_class_colors(path: Path) -> dict[str, str]:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))

    colors: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name, color = parts[0].strip().lower(), parts[1].strip()
        if not color.startswith("#"):
            color = f"#{color}"
        colors[name] = color
        if name == "collarless":
            colors["colorless"] = color
    return colors


def prepare_frame_rules(rules_path: Path, class_colors_path: Path | None = None) -> dict:
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    class_colors = {
        "butcher": "#8a3746",
        "cleric": "#fdfdfd",
        "colorless": "#817b77",
        "druid": "#5b4237",
        "fighter": "#b17373",
        "hunter": "#425d3d",
        "jester": "#817b77",
        "mage": "#787899",
        "monk": "#787878",
        "necromancer": "#232425",
        "psychic": "#645379",
        "tank": "#857348",
        "thief": "#fffbb5",
        "tinkerer": "#b5eadc",
    }
    if class_colors_path and class_colors_path.exists():
        class_colors.update(load_class_colors(class_colors_path))

    rules["classes"] = {name: {"color": color} for name, color in class_colors.items()}
    for layer in rules.get("layers", []):
        if layer.get("source") != "$main":
            layer["recolor"] = {"#111111": "$classColor"}
    return rules


def copy_or_frame_svg(
    *,
    group: str,
    variant: str,
    wiki_ability: WikiAbility,
    manifest_row: dict[str, str] | None,
    shapes_dir: Path,
    output_dir: Path,
    frame_rules: dict,
    frame_rules_dir: Path,
) -> tuple[str, str]:
    if not manifest_row or not manifest_row.get("main_svg_id"):
        return "", ""

    source_svg = shapes_dir / f"{manifest_row['main_svg_id']}.svg"
    if not source_svg.exists():
        return "", ""

    class_folder = safe_name(wiki_ability.class_name)
    frame_folder = FRAME_FOLDER_NAMES[group]
    output_name = f"{safe_name(wiki_ability.name)}_{manifest_row['ability_id']}_{variant}.svg"
    target_dir = output_dir / class_folder / frame_folder / variant
    target_dir.mkdir(parents=True, exist_ok=True)

    output_svg = target_dir / output_name
    if group == "damage_mana":
        class_name = (manifest_row.get("tool_class") or wiki_ability.class_name).lower()
        try:
            build_from_rules(frame_rules, frame_rules_dir, source_svg.resolve(), class_name, output_svg.resolve())
            return str(source_svg), str(output_svg)
        except Exception:
            pass

    shutil.copy2(source_svg, output_svg)
    return str(source_svg), str(output_svg)


def classify_and_export(
    *,
    wiki_url: str,
    manifest_path: Path,
    shapes_dir: Path,
    output_dir: Path,
    frame_rules_path: Path,
) -> dict[str, int]:
    wiki_abilities = parse_wiki_abilities(fetch_wiki_html(wiki_url))
    manifest = read_manifest(manifest_path)
    frame_rules = prepare_frame_rules(frame_rules_path)

    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}

    for ability in wiki_abilities:
        manifest_row = manifest.get(normalize_name(ability.name))
        normal_attrs, upgraded_attrs = split_normal_upgraded(ability.attributes)

        variants = [("normal", normal_attrs)]
        if upgraded_attrs:
            variants.append(("upgraded", upgraded_attrs))

        for variant, attrs in variants:
            group = classify_attributes(attrs)
            counts[group] = counts.get(group, 0) + 1
            source_svg, output_svg = copy_or_frame_svg(
                group=group,
                variant=variant,
                wiki_ability=ability,
                manifest_row=manifest_row,
                shapes_dir=shapes_dir,
                output_dir=output_dir,
                frame_rules=frame_rules,
                frame_rules_dir=frame_rules_path.parent.resolve(),
            )
            rows.append(
                {
                    "wiki_name": ability.name,
                    "class": ability.class_name,
                    "variant": variant,
                    "attributes": attrs,
                    "frame_group": FRAME_FOLDER_NAMES[group],
                    "manifest_ability_id": manifest_row.get("ability_id", "") if manifest_row else "",
                    "main_svg_id": manifest_row.get("main_svg_id", "") if manifest_row else "",
                    "source_svg": source_svg,
                    "output_svg": output_svg,
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_output = output_dir / "wiki_active_frame_manifest.csv"
    with manifest_output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify active abilities by wiki Attributes and export SVG folders.")
    parser.add_argument("--wiki-url", default=WIKI_URL)
    parser.add_argument("--manifest", type=Path, default=Path("output") / "active_manifest.csv")
    parser.add_argument("--shapes-dir", type=Path, default=DEFAULT_SHAPES_DIR)
    parser.add_argument("--frame-rules", type=Path, default=Path("rules") / "active_frame_1_manual.json")
    parser.add_argument("--output-dir", type=Path, default=Path("output") / "wiki_active_frames")
    args = parser.parse_args()

    counts = classify_and_export(
        wiki_url=args.wiki_url,
        manifest_path=args.manifest.resolve(),
        shapes_dir=args.shapes_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        frame_rules_path=args.frame_rules.resolve(),
    )

    print(f"output={args.output_dir.resolve()}")
    for group, count in sorted(counts.items()):
        print(f"{FRAME_FOLDER_NAMES[group]}={count}")


if __name__ == "__main__":
    main()
