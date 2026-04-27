from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def read_svg_children(path: Path, recolor: dict[str, str]) -> list[ET.Element]:
    root = ET.parse(path).getroot()
    for node in root.iter():
        for attr in ("fill", "stroke"):
            value = node.attrib.get(attr)
            if value in recolor:
                node.set(attr, recolor[value])
    return [deepcopy(child) for child in list(root)]


def resolve_source(source: str, rules_dir: Path, main_svg: Path) -> Path:
    if source == "$main":
        return main_svg.resolve()
    path = Path(source)
    if not path.is_absolute():
        path = (rules_dir / path).resolve()
    return path


def build(
    rules_path: Path,
    main_svg: Path,
    class_name: str,
    output: Path,
    layer_overrides: dict[str, dict] | None = None,
) -> None:
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    build_from_rules(rules, rules_path.parent, main_svg, class_name, output, layer_overrides)


def build_from_rules(
    rules: dict,
    rules_dir: Path,
    main_svg: Path,
    class_name: str,
    output: Path,
    layer_overrides: dict[str, dict] | None = None,
) -> None:
    class_data = rules.get("classes", {}).get(class_name)
    if class_data is None:
        known = ", ".join(sorted(rules.get("classes", {})))
        raise KeyError(f"Unknown class '{class_name}'. Known classes: {known}")

    canvas = rules["canvas"]
    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "width": str(canvas["width"]),
            "height": str(canvas["height"]),
            "viewBox": canvas["viewBox"],
            "version": "1.1",
        },
    )

    for layer in rules["layers"]:
        if not layer.get("visible", True):
            continue
        if layer["id"] in class_data.get("hide_layers", []):
            continue

        layer = deepcopy(layer)
        if layer_overrides and layer["id"] in layer_overrides:
            layer.update(layer_overrides[layer["id"]])

        source = resolve_source(layer["source"], rules_dir, main_svg)
        if not source.exists():
            raise FileNotFoundError(source)

        recolor = {}
        for source_color, target_color in layer.get("recolor", {}).items():
            if target_color == "$classColor":
                recolor[source_color] = class_data["color"]
            else:
                recolor[source_color] = target_color

        transform_parts = [f"translate({layer.get('x', 0)} {layer.get('y', 0)})"]
        matrix = layer.get("matrix")
        if matrix:
            transform_parts.append(
                "matrix("
                f"{matrix.get('a', 1)} "
                f"{matrix.get('b', 0)} "
                f"{matrix.get('c', 0)} "
                f"{matrix.get('d', 1)} "
                f"{matrix.get('e', 0)} "
                f"{matrix.get('f', 0)}"
                ")"
            )
        transform_parts.extend(
            [
                f"rotate({layer.get('rotation', 0)})",
                f"scale({layer.get('scaleX', 1)} {layer.get('scaleY', 1)})",
            ]
        )

        group = ET.SubElement(
            root,
            f"{{{SVG_NS}}}g",
            {
                "id": layer["id"],
                "transform": " ".join(transform_parts),
            },
        )
        for child in read_svg_children(source, recolor):
            group.append(child)

    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an active ability icon from manual layout rules.")
    parser.add_argument("--rules", type=Path, default=Path("rules") / "active_manual.json")
    parser.add_argument("--main-svg", type=Path, required=True)
    parser.add_argument("--class-name", default="butcher")
    parser.add_argument("--output", type=Path, default=Path("output") / "manual_active.svg")
    parser.add_argument("--layer-overrides-json", default="")
    parser.add_argument("--layer-overrides-file", type=Path)
    args = parser.parse_args()

    if args.layer_overrides_file:
        layer_overrides = json.loads(args.layer_overrides_file.read_text(encoding="utf-8"))
    else:
        layer_overrides = json.loads(args.layer_overrides_json) if args.layer_overrides_json else None

    build(args.rules.resolve(), args.main_svg.resolve(), args.class_name, args.output.resolve(), layer_overrides)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
