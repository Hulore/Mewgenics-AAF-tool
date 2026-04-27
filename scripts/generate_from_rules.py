from __future__ import annotations

import argparse
import base64
import json
import re
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from PIL import ImageFont
except ImportError:  # pragma: no cover - local tool fallback
    ImageFont = None


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

DEFAULT_FONT_PATHS = {
    "MewgenicsNumber": Path(
        r"H:\Mewgenics Projects\Active Abilities Frame\SVG Important\Number Fonts\fonts\1_TikaFont_TikaFont Adjusted Regular.ttf"
    ),
}


def text_width(text: str, font_size: float, font_family: str) -> float:
    font_path = DEFAULT_FONT_PATHS.get(font_family)
    if ImageFont and font_path and font_path.exists():
        font = ImageFont.truetype(str(font_path), int(round(font_size)))
        return float(font.getlength(text))
    return len(text) * font_size * 0.6


def fitted_font_size(layer: dict) -> float:
    text = str(layer.get("text", ""))
    font_family = layer.get("fontFamily", "")
    font_size = float(layer.get("fontSize", 12))
    box_width = float(layer.get("boxWidth", 0) or 0)
    box_height = float(layer.get("boxHeight", 0) or 0)
    min_font_size = float(layer.get("minFontSize", 4))
    if not text or box_width <= 0 or box_height <= 0:
        return font_size

    fitted = font_size
    while fitted > min_font_size:
        if text_width(text, fitted, font_family) <= box_width and fitted <= box_height:
            return round(fitted, 2)
        fitted -= 0.25
    return min_font_size


def parse_svg_length(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.match(r"[-+]?\d*\.?\d+", str(value))
    return float(match.group(0)) if match else None


def svg_viewport(path: Path) -> tuple[float, float, float, float]:
    root = ET.parse(path).getroot()
    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = [float(part) for part in re.split(r"[,\s]+", view_box.strip()) if part]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    width = parse_svg_length(root.attrib.get("width")) or 0
    height = parse_svg_length(root.attrib.get("height")) or 0
    return 0, 0, width, height


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


def font_face_style(font_families: set[str]) -> str:
    rules: list[str] = []
    for family in sorted(font_families):
        path = DEFAULT_FONT_PATHS.get(family)
        if not path or not path.exists():
            continue
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            "@font-face { "
            f"font-family: '{family}'; "
            f"src: url(data:font/ttf;base64,{encoded}) format('truetype'); "
            "font-weight: 400; "
            "font-style: normal; "
            "}"
        )
    return "\n".join(rules)


def layer_anchor(layer: dict, rules_dir: Path, main_svg: Path) -> tuple[float, float]:
    if "anchorX" in layer and "anchorY" in layer:
        return float(layer["anchorX"]), float(layer["anchorY"])
    if layer.get("type") == "text":
        return float(layer.get("boxWidth", 0) or 0) / 2, float(layer.get("boxHeight", 0) or 0) / 2
    source = resolve_source(layer["source"], rules_dir, main_svg)
    min_x, min_y, width, height = svg_viewport(source)
    return min_x + width / 2, min_y + height / 2


def layer_scale(layer: dict, rules_dir: Path, main_svg: Path) -> tuple[float, float]:
    scale_x = float(layer.get("scaleX", 1))
    scale_y = float(layer.get("scaleY", 1))
    fit_mode = layer.get("fitMode")
    box_width = float(layer.get("boxWidth", 0) or 0)
    box_height = float(layer.get("boxHeight", 0) or 0)
    if layer.get("type") == "text" or not fit_mode or box_width <= 0 or box_height <= 0:
        return scale_x, scale_y

    source = resolve_source(layer["source"], rules_dir, main_svg)
    _min_x, _min_y, source_width, source_height = svg_viewport(source)
    if source_width <= 0 or source_height <= 0:
        return scale_x, scale_y

    fit_x = box_width / source_width
    fit_y = box_height / source_height
    if fit_mode == "contain":
        fit_x = fit_y = min(fit_x, fit_y)
    return scale_x * fit_x, scale_y * fit_y


def layer_has_box(layer: dict) -> bool:
    return bool(
        layer.get("boxWidth")
        and layer.get("boxHeight")
        and layer.get("type") != "text"
        and layer.get("fitMode")
    )


def box_fit_transform(layer: dict, rules_dir: Path, main_svg: Path) -> str:
    source = resolve_source(layer["source"], rules_dir, main_svg)
    source_min_x, source_min_y, source_width, source_height = svg_viewport(source)
    box_width = float(layer.get("boxWidth", 0) or 0)
    box_height = float(layer.get("boxHeight", 0) or 0)
    if source_width <= 0 or source_height <= 0 or box_width <= 0 or box_height <= 0:
        return ""

    fit_x = box_width / source_width
    fit_y = box_height / source_height
    if layer.get("fitMode") == "contain":
        fit_x = fit_y = min(fit_x, fit_y)

    source_anchor_x = source_min_x + source_width / 2
    source_anchor_y = source_min_y + source_height / 2
    return (
        f"translate({box_width / 2} {box_height / 2}) "
        f"scale({fit_x} {fit_y}) "
        f"translate({-source_anchor_x} {-source_anchor_y})"
    )


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
    classes = rules.get("classes", {})
    class_data = classes.get(class_name)
    if class_data is None and not classes:
        class_data = {"color": rules.get("preview_recolor", {}).get("#111111", "#8a3746")}
    elif class_data is None:
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
    text_font_families = {
        layer.get("fontFamily")
        for layer in rules.get("layers", [])
        if layer.get("type") == "text" and layer.get("fontFamily")
    }
    style_text = font_face_style(text_font_families)
    if style_text:
        defs = ET.SubElement(root, f"{{{SVG_NS}}}defs")
        style = ET.SubElement(defs, f"{{{SVG_NS}}}style", {"type": "text/css"})
        style.text = style_text

    for layer in rules["layers"]:
        if not layer.get("visible", True):
            continue
        if layer["id"] in class_data.get("hide_layers", []):
            continue

        layer = deepcopy(layer)
        if layer_overrides and layer["id"] in layer_overrides:
            layer.update(layer_overrides[layer["id"]])

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
        scale_x, scale_y = layer_scale(layer, rules_dir, main_svg)
        if layer_has_box(layer):
            scale_x = float(layer.get("scaleX", 1))
            scale_y = float(layer.get("scaleY", 1))
        transform_parts.extend([f"rotate({layer.get('rotation', 0)})", f"scale({scale_x} {scale_y})"])
        if layer.get("anchor", "top_left") == "center":
            if layer_has_box(layer):
                anchor_x = float(layer.get("boxWidth", 0) or 0) / 2
                anchor_y = float(layer.get("boxHeight", 0) or 0) / 2
            else:
                anchor_x, anchor_y = layer_anchor(layer, rules_dir, main_svg)
            transform_parts.append(f"translate({-anchor_x} {-anchor_y})")

        group = ET.SubElement(
            root,
            f"{{{SVG_NS}}}g",
            {
                "id": layer["id"],
                "transform": " ".join(transform_parts),
            },
        )

        if layer.get("type") == "text":
            box_width = layer.get("boxWidth")
            box_height = layer.get("boxHeight")
            if box_width and box_height:
                text_attrs = {
                    "x": str(float(box_width) / 2),
                    "y": str(float(box_height) / 2),
                    "fill": layer.get("fill", "#000000"),
                    "font-family": layer.get("fontFamily", "sans-serif"),
                    "font-size": str(fitted_font_size(layer)),
                    "text-anchor": "middle",
                    "dominant-baseline": "central",
                }
            else:
                text_attrs = {
                    "x": "0",
                    "y": "0",
                    "fill": layer.get("fill", "#000000"),
                    "font-family": layer.get("fontFamily", "sans-serif"),
                    "font-size": str(layer.get("fontSize", 12)),
                    "text-anchor": layer.get("textAnchor", "start"),
                    "dominant-baseline": "hanging",
                }
            text_node = ET.SubElement(
                group,
                f"{{{SVG_NS}}}text",
                text_attrs,
            )
            text_node.text = str(layer.get("text", ""))
            continue

        source = resolve_source(layer["source"], rules_dir, main_svg)
        if not source.exists():
            raise FileNotFoundError(source)

        recolor = {}
        for source_color, target_color in layer.get("recolor", {}).items():
            if target_color == "$classColor":
                recolor[source_color] = class_data["color"]
            else:
                recolor[source_color] = target_color

        parent = group
        if layer_has_box(layer):
            fit_group = ET.SubElement(group, f"{{{SVG_NS}}}g", {"transform": box_fit_transform(layer, rules_dir, main_svg)})
            parent = fit_group

        for child in read_svg_children(source, recolor):
            parent.append(child)

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
