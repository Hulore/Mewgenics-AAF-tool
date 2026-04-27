from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

DEFAULT_FRAMES_XML = Path(
    r"H:\Mewgenics Projects\Passive Abilities Frame\OtherGameFiles\UnpackedImportant\ABILITYICONSHELL_161\frames.xml"
)

Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)


@dataclass
class DisplayObject:
    character_id: int
    depth: int
    matrix: Matrix = IDENTITY
    name: str = ""
    ratio: str = ""


@dataclass
class SpriteFrame:
    labels: list[str]
    objects: list[DisplayObject]


def parse_bool(value: str | None) -> bool:
    return value == "true"


def parse_matrix(node: ET.Element | None) -> Matrix:
    if node is None:
        return IDENTITY
    has_scale = parse_bool(node.get("hasScale"))
    has_rotate = parse_bool(node.get("hasRotate"))
    scale_x = float(node.get("scaleX") or 1) if has_scale else 1
    scale_y = float(node.get("scaleY") or 1) if has_scale else 1
    skew_0 = float(node.get("rotateSkew0") or 0) if has_rotate else 0
    skew_1 = float(node.get("rotateSkew1") or 0) if has_rotate else 0
    translate_x = float(node.get("translateX") or 0) / 20
    translate_y = float(node.get("translateY") or 0) / 20
    return (scale_x, skew_1, skew_0, scale_y, translate_x, translate_y)


def multiply(left: Matrix, right: Matrix) -> Matrix:
    la, lb, lc, ld, le, lf = left
    ra, rb, rc, rd, re, rf = right
    return (
        la * ra + lc * rb,
        lb * ra + ld * rb,
        la * rc + lc * rd,
        lb * rc + ld * rd,
        la * re + lc * rf + le,
        lb * re + ld * rf + lf,
    )


def matrix_dict(matrix: Matrix) -> dict[str, float]:
    a, b, c, d, e, f = matrix
    return {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f}


def class_recolor() -> dict[str, str]:
    return {
        "#111111": "$classColor",
        "#666666": "$classColor",
        "#767676": "$classColor",
    }


def color_from_node(node: ET.Element | None) -> str:
    if node is None:
        return "#000000"
    red = int(node.get("red") or 0)
    green = int(node.get("green") or 0)
    blue = int(node.get("blue") or 0)
    return f"#{red:02x}{green:02x}{blue:02x}"


def alpha_from_node(node: ET.Element | None) -> str | None:
    if node is None or node.get("alpha") is None:
        return None
    alpha = int(node.get("alpha") or 255) / 255
    return f"{alpha:.4g}"


def parse_fill_styles(shape: ET.Element) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    fill_styles = shape.find("./shapes/fillStyles/fillStyles")
    if fill_styles is None:
        return result
    for index, item in enumerate(fill_styles.findall("item"), start=1):
        color = item.find("color")
        result[index] = {"fill": color_from_node(color)}
        alpha = alpha_from_node(color)
        if alpha is not None:
            result[index]["fill-opacity"] = alpha
    return result


def parse_line_styles(shape: ET.Element) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    line_styles = shape.find("./shapes/lineStyles/lineStyles2")
    if line_styles is None or not list(line_styles):
        line_styles = shape.find("./shapes/lineStyles/lineStyles")
    if line_styles is None:
        return result
    for index, item in enumerate(line_styles.findall("item"), start=1):
        color = item.find("color")
        result[index] = {
            "stroke": color_from_node(color),
            "stroke-width": str(float(item.get("width") or 20) / 20),
            "fill": "none",
        }
        alpha = alpha_from_node(color)
        if alpha is not None:
            result[index]["stroke-opacity"] = alpha
    return result


def export_shape(shape: ET.Element, output: Path) -> None:
    shape_id = shape.get("shapeId")
    bounds = shape.find("shapeBounds")
    xmin = float(bounds.get("Xmin") or 0) / 20 if bounds is not None else 0
    ymin = float(bounds.get("Ymin") or 0) / 20 if bounds is not None else 0
    xmax = float(bounds.get("Xmax") or 0) / 20 if bounds is not None else 72
    ymax = float(bounds.get("Ymax") or 0) / 20 if bounds is not None else 72
    width = max(1.0, xmax - xmin)
    height = max(1.0, ymax - ymin)

    fills = parse_fill_styles(shape)
    lines = parse_line_styles(shape)
    root = ET.Element(
        f"{{{SVG_NS}}}svg",
        {
            "width": f"{width:g}px",
            "height": f"{height:g}px",
            "viewBox": f"{xmin:g} {ymin:g} {width:g} {height:g}",
            "data-shape-id": str(shape_id),
        },
    )

    records = shape.findall("./shapes/shapeRecords/item")
    x = 0.0
    y = 0.0
    fill_style = 0
    line_style = 0
    path = ""

    def flush() -> None:
        nonlocal path
        if not path:
            return
        attrs = {"d": path.strip()}
        if line_style and line_style in lines:
            attrs.update(lines[line_style])
        elif fill_style and fill_style in fills:
            attrs.update(fills[fill_style])
            attrs["fill-rule"] = "evenodd"
            attrs["stroke"] = "none"
        else:
            attrs.update({"fill": "none", "stroke": "none"})
        ET.SubElement(root, f"{{{SVG_NS}}}path", attrs)
        path = ""

    for record in records:
        record_type = record.get("type")
        if record_type == "StyleChangeRecord":
            if record.get("stateNewStyles") == "true":
                flush()
                fills.update(parse_fill_styles(record))
                lines.update(parse_line_styles(record))
            if record.get("stateFillStyle1") == "true" or record.get("stateFillStyle0") == "true" or record.get("stateLineStyle") == "true":
                flush()
                if record.get("stateFillStyle1") == "true":
                    fill_style = int(record.get("fillStyle1") or 0)
                elif record.get("stateFillStyle0") == "true":
                    fill_style = int(record.get("fillStyle0") or 0)
                if record.get("stateLineStyle") == "true":
                    line_style = int(record.get("lineStyle") or 0)
            if record.get("stateMoveTo") == "true":
                x = float(record.get("moveDeltaX") or 0) / 20
                y = float(record.get("moveDeltaY") or 0) / 20
                path += f"M{x:g} {y:g} "
        elif record_type == "StraightEdgeRecord":
            dx = float(record.get("deltaX") or 0) / 20
            dy = float(record.get("deltaY") or 0) / 20
            x += dx
            y += dy
            path += f"L{x:g} {y:g} "
        elif record_type == "CurvedEdgeRecord":
            cx = x + float(record.get("controlDeltaX") or 0) / 20
            cy = y + float(record.get("controlDeltaY") or 0) / 20
            x = cx + float(record.get("anchorDeltaX") or 0) / 20
            y = cy + float(record.get("anchorDeltaY") or 0) / 20
            path += f"Q{cx:g} {cy:g} {x:g} {y:g} "
        elif record_type == "EndShapeRecord":
            flush()

    flush()
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)


def parse_display_object(place: ET.Element, previous: DisplayObject | None) -> DisplayObject | None:
    has_character = parse_bool(place.get("placeFlagHasCharacter"))
    character_id = int(place.get("characterId") or 0) if has_character else (previous.character_id if previous else 0)
    if not character_id:
        return previous
    depth = int(place.get("depth") or (previous.depth if previous else 0))
    matrix = parse_matrix(place.find("matrix")) if parse_bool(place.get("placeFlagHasMatrix")) else (previous.matrix if previous else IDENTITY)
    name = place.get("name") or (previous.name if previous else "")
    ratio = place.get("ratio") or (previous.ratio if previous else "")
    return DisplayObject(character_id, depth, matrix, name, ratio)


def parse_sprite_frames(sprite: ET.Element) -> list[SpriteFrame]:
    display: dict[int, DisplayObject] = {}
    frames: list[SpriteFrame] = []
    pending_labels: list[str] = []
    for item in sprite.find("subTags").findall("item"):
        item_type = item.get("type")
        if item_type == "FrameLabelTag":
            pending_labels.append(item.get("name") or "")
        elif item_type == "PlaceObject2Tag":
            depth = int(item.get("depth") or 0)
            obj = parse_display_object(item, display.get(depth))
            if obj:
                display[depth] = obj
        elif item_type == "RemoveObject2Tag":
            display.pop(int(item.get("depth") or 0), None)
        elif item_type == "ShowFrameTag":
            frames.append(SpriteFrame(pending_labels, [display[d] for d in sorted(display)]))
            pending_labels = []
    return frames


def build_assets(frames_xml: Path, output_dir: Path) -> dict:
    root = ET.parse(frames_xml).getroot()
    tags = root.find("tags")
    shapes: dict[int, ET.Element] = {}
    sprites: dict[int, list[SpriteFrame]] = {}

    for item in tags.findall("item"):
        item_type = item.get("type") or ""
        if item_type.startswith("DefineShape"):
            shapes[int(item.get("shapeId") or 0)] = item
        elif item_type == "DefineSpriteTag":
            sprites[int(item.get("spriteId") or 0)] = parse_sprite_frames(item)

    assets_dir = output_dir / "assets" / "shell_shapes"
    for shape_id, shape in shapes.items():
        if 2750 <= shape_id <= 2835:
            export_shape(shape, assets_dir / f"{shape_id}.svg")

    def flatten(character_id: int, matrix: Matrix, prefix: str, frame_index: int = 0) -> list[dict]:
        if character_id in shapes:
            return [
                {
                    "id": prefix,
                    "label": prefix,
                    "source": f"../assets/shell_shapes/{character_id}.svg",
                    "x": 0,
                    "y": 0,
                    "scaleX": 1,
                    "scaleY": 1,
                    "rotation": 0,
                    "matrix": matrix_dict(matrix),
                    "recolor": class_recolor(),
                    "visible": True,
                }
            ]
        if character_id not in sprites or not sprites[character_id]:
            return []

        frame = sprites[character_id][min(frame_index, len(sprites[character_id]) - 1)]
        layers: list[dict] = []
        for obj in frame.objects:
            child_prefix = f"{prefix}_{obj.name or obj.character_id}_d{obj.depth}"
            layers.extend(flatten(obj.character_id, multiply(matrix, obj.matrix), child_prefix))
        return layers

    shell = sprites[2832]
    variants = {}
    for index, frame in enumerate(shell, start=1):
        frame_key = f"frame_{index}"
        layers = []
        for obj in frame.objects:
            name = obj.name or f"char_{obj.character_id}"
            if name in {"damage", "mana"}:
                continue
            if name == "icon":
                layers.append(
                    {
                        "id": "main_picture",
                        "label": "Main picture",
                        "source": "$main",
                        "x": 0,
                        "y": 0,
                        "scaleX": 1,
                        "scaleY": 1,
                        "rotation": 0,
                        "matrix": matrix_dict(obj.matrix),
                        "visible": True,
                    }
                )
                continue
            prefix = f"{name}_d{obj.depth}"
            layers.extend(flatten(obj.character_id, obj.matrix, prefix))

        variants[frame_key] = {
            "label": f"Shell frame {index}",
            "source_frame": index,
            "layers": layers,
        }

    frame_variants = {
        "canvas": {"width": 116.05, "height": 178, "viewBox": "0 0 116.05 178"},
        "variants": variants,
    }
    (output_dir / "rules").mkdir(parents=True, exist_ok=True)
    (output_dir / "rules" / "frame_variants.json").write_text(json.dumps(frame_variants, indent=2), encoding="utf-8")
    classes = {
        "butcher": {"color": "#ac4457"},
        "cleric": {"color": "#fdfdfd"},
        "colorless": {"color": "#817b77"},
        "druid": {"color": "#5b4237"},
        "fighter": {"color": "#b17373"},
        "hunter": {"color": "#425d3d"},
        "jester": {"color": "#817b77"},
        "mage": {"color": "#787899"},
        "monk": {"color": "#787878"},
        "necromancer": {"color": "#232425"},
        "psychic": {"color": "#645379"},
        "tank": {"color": "#857348"},
        "thief": {"color": "#fffbb5"},
        "tinkerer": {"color": "#b5eadc"},
    }
    for key, variant in variants.items():
        rules = {
            "canvas": frame_variants["canvas"],
            "classes": classes,
            "frame_variant": key,
            "layers": variant["layers"],
        }
        (output_dir / "rules" / f"{key}_manual.json").write_text(json.dumps(rules, indent=2), encoding="utf-8")
    return frame_variants


def main() -> None:
    parser = argparse.ArgumentParser(description="Export active shell frame SVG assets and variants.")
    parser.add_argument("--frames-xml", type=Path, default=DEFAULT_FRAMES_XML)
    parser.add_argument("--output-root", type=Path, default=Path("."))
    args = parser.parse_args()
    data = build_assets(args.frames_xml.resolve(), args.output_root.resolve())
    print(f"variants={len(data['variants'])}")
    print(args.output_root.resolve() / "rules" / "frame_variants.json")


if __name__ == "__main__":
    main()
