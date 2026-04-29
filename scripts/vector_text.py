from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen


SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class GlyphData:
    path: str
    advance: float
    bounds: tuple[float, float, float, float] | None


class VectorFont:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.font = TTFont(path)
        self.glyph_set = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap() or {}
        self.units_per_em = float(self.font["head"].unitsPerEm)
        self.ascent = float(getattr(self.font["OS/2"], "sTypoAscender", self.font["hhea"].ascent))
        self.descent = float(getattr(self.font["OS/2"], "sTypoDescender", self.font["hhea"].descent))
        self.glyphs: dict[str, GlyphData] = {}

    def glyph_for_char(self, char: str) -> GlyphData | None:
        if char not in self.glyphs:
            glyph_name = self.cmap.get(ord(char))
            if not glyph_name:
                return None
            pen = SVGPathPen(self.glyph_set)
            self.glyph_set[glyph_name].draw(pen)
            bounds_pen = BoundsPen(self.glyph_set)
            self.glyph_set[glyph_name].draw(bounds_pen)
            advance_width, _left_bearing = self.font["hmtx"][glyph_name]
            self.glyphs[char] = GlyphData(pen.getCommands(), float(advance_width), bounds_pen.bounds)
        return self.glyphs[char]

    def text_width(self, text: str, font_size: float) -> float:
        scale = font_size / self.units_per_em
        return sum((self.glyph_for_char(char).advance if self.glyph_for_char(char) else self.units_per_em * 0.5) * scale for char in text)

    def text_bounds(self, text: str) -> tuple[float, float, float, float] | None:
        cursor_x = 0.0
        bounds: list[tuple[float, float, float, float]] = []
        for char in text:
            glyph = self.glyph_for_char(char)
            if glyph and glyph.bounds:
                min_x, min_y, max_x, max_y = glyph.bounds
                bounds.append((cursor_x + min_x, min_y, cursor_x + max_x, max_y))
            cursor_x += (glyph.advance if glyph else self.units_per_em * 0.5)
        if not bounds:
            return None
        return (
            min(item[0] for item in bounds),
            min(item[1] for item in bounds),
            max(item[2] for item in bounds),
            max(item[3] for item in bounds),
        )

    def render_paths(
        self,
        text: str,
        *,
        x: float,
        y: float,
        font_size: float,
        fill: str = "#000000",
        anchor: str = "middle",
        dominant_baseline: str = "central",
    ) -> list[ET.Element]:
        scale = font_size / self.units_per_em
        width = self.text_width(text, font_size)
        if anchor == "middle":
            cursor_x = x - width / 2
        elif anchor == "end":
            cursor_x = x - width
        else:
            cursor_x = x

        bounds = self.text_bounds(text)
        if bounds and anchor == "middle":
            bounds_center_x = ((bounds[0] + bounds[2]) / 2) * scale
            cursor_x = x - bounds_center_x

        if dominant_baseline == "central" and bounds:
            bounds_center_y = ((bounds[1] + bounds[3]) / 2) * scale
            baseline_y = y + bounds_center_y
        elif dominant_baseline == "central":
            baseline_y = y + ((self.ascent + self.descent) / 2) * scale
        else:
            baseline_y = y

        paths: list[ET.Element] = []
        for char in text:
            glyph = self.glyph_for_char(char)
            if glyph and glyph.path:
                paths.append(
                    ET.Element(
                        f"{{{SVG_NS}}}path",
                        {
                            "fill": fill,
                            "d": glyph.path,
                            "transform": f"translate({round(cursor_x, 4)} {round(baseline_y, 4)}) scale({round(scale, 6)} {-round(scale, 6)})",
                        },
                    )
                )
            cursor_x += (glyph.advance if glyph else self.units_per_em * 0.5) * scale
        return paths
