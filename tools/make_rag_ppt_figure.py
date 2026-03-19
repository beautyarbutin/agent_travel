from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "assets"
PNG_PATH = OUT_DIR / "rag_ppt_figure.png"
SVG_PATH = OUT_DIR / "rag_ppt_figure.svg"

W, H = 2200, 980

BLUE = "#0F4A95"
BLUE_2 = "#2B6CB0"
TEAL = "#0F766E"
GOLD = "#C28B2C"
BG = "#FFFFFF"
PANEL = "#F6F8FB"
PANEL_2 = "#F9FBFE"
TEXT = "#162235"
MUTED = "#5A687A"
LINE = "#C8D2E1"


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    title: str
    lines: list[str]
    fill: str = PANEL
    stroke: str = LINE
    title_fill: str = TEXT
    body_fill: str = MUTED


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_round_box(draw: ImageDraw.ImageDraw, box: Box, title_font, body_font) -> None:
    draw.rounded_rectangle(
        (box.x, box.y, box.x + box.w, box.y + box.h),
        radius=24,
        fill=box.fill,
        outline=box.stroke,
        width=3,
    )
    tx = box.x + 26
    ty = box.y + 18
    draw.text((tx, ty), box.title, font=title_font, fill=box.title_fill)
    ly = ty + 52
    for line in box.lines:
        draw.text((tx, ly), line, font=body_font, fill=box.body_fill)
        ly += 38


def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color=BLUE, width=5) -> None:
    draw.line((start, end), fill=color, width=width)
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex > sx else -1
        p1 = (ex - 18 * direction, ey - 10)
        p2 = (ex - 18 * direction, ey + 10)
    else:
        direction = 1 if ey > sy else -1
        p1 = (ex - 10, ey - 18 * direction)
        p2 = (ex + 10, ey - 18 * direction)
    draw.polygon([end, p1, p2], fill=color)


def draw_label(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill=BLUE) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    pad_x = 18
    pad_y = 8
    w = bbox[2] - bbox[0] + pad_x * 2
    h = bbox[3] - bbox[1] + pad_y * 2
    draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill=fill)
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill="#FFFFFF")


def create_png() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    title_font = load_font(48, bold=True)
    subtitle_font = load_font(24, bold=False)
    panel_title_font = load_font(22, bold=True)
    panel_body_font = load_font(18, bold=False)
    section_font = load_font(22, bold=True)
    box_title_font = load_font(24, bold=True)
    box_body_font = load_font(20, bold=False)

    draw.text((84, 54), "RAG：从建库到在线回答", font=title_font, fill=BLUE)
    draw.text(
        (88, 116),
        "适合放在答辩 PPT 的宽版流程图：左边说明离线建库，右边说明在线查询和融合回答。",
        font=subtitle_font,
        fill=MUTED,
    )

    left = (74, 184, 1008, 868)
    right = (1090, 184, 2126, 868)
    draw.rounded_rectangle(left, radius=28, fill=PANEL_2, outline="#D6DFEB", width=3)
    draw.rounded_rectangle(right, radius=28, fill="#FFFCF1", outline="#E8D9A9", width=3)
    draw_label(draw, 112, 202, "离线建库", section_font, fill=TEAL)
    draw_label(draw, 1128, 202, "在线查询", section_font, fill=GOLD)

    offline_boxes = [
        Box(118, 276, 220, 118, "多源数据", ["Kaggle / CrossWOZ", "手写攻略 / China312 / HK QA"]),
        Box(370, 276, 210, 118, "统一 Schema", ["spots_knowledge.json"]),
        Box(612, 276, 210, 118, "向量构建", ["build_spot_vectors.py"]),
        Box(118, 470, 320, 128, "拼接文本", ["city + district + spot_name", "+ tags + content"]),
        Box(476, 470, 240, 128, "Embedding", ["bge-small-zh-v1.5", "512 维向量"]),
        Box(754, 470, 214, 128, "索引落盘", ["storage/doecment.json", "storage/faiss_index.bin"]),
        Box(188, 684, 700, 112, "结果", ["得到本地可运行的 CPU 版 Hybrid RAG 底座"], fill="#EDF6EE", stroke="#B7D6BD", title_fill=TEAL, body_fill=TEXT),
    ]
    for b in offline_boxes:
        draw_round_box(draw, b, box_title_font, box_body_font)

    draw_arrow(draw, (338, 335), (370, 335), color=TEAL)
    draw_arrow(draw, (580, 335), (612, 335), color=TEAL)
    draw_arrow(draw, (220, 394), (220, 470), color=TEAL)
    draw_arrow(draw, (720, 394), (720, 470), color=TEAL)
    draw_arrow(draw, (438, 534), (476, 534), color=TEAL)
    draw_arrow(draw, (716, 534), (754, 534), color=TEAL)
    draw_arrow(draw, (861, 598), (861, 684), color=TEAL)

    online_boxes = [
        Box(1136, 276, 206, 118, "用户问题", ["景点推荐 / 攻略", "避坑 / 路线相关"]),
        Box(1380, 276, 220, 118, "travel_router", ["识别为景点意图", "转发给 spot_agent"]),
        Box(1638, 276, 214, 118, "spot_agent", ["通过 MCP 调工具"]),
        Box(1890, 276, 200, 118, "问题分流", ["泛推荐 / 深问 / 都要"]),
        Box(1140, 470, 220, 118, "search_spots", ["城市级泛推荐", "优先走高德 POI"]),
        Box(1400, 470, 230, 118, "search_local_knowledge", ["具体景点深问", "走本地 RAG"]),
        Box(1670, 470, 200, 118, "search_combined", ["深度攻略 + 实时 POI"]),
        Box(1910, 470, 180, 118, "高德 POI", ["地址 / 电话", "实时候选"]),
        Box(1328, 664, 230, 118, "Hybrid RAG", ["FAISS dense", "+ BM25-like", "+ 手写攻略 bonus"]),
        Box(1596, 664, 214, 118, "融合排序", ["5*dense + bm25 + bonus", "输出 Top-5 文档"]),
        Box(1848, 648, 242, 150, "最终回答", ["POI 提供地址 / 电话", "RAG 提供攻略 / 避坑", "两类信息合并输出"], fill="#EDF6EE", stroke="#B7D6BD", title_fill=TEAL, body_fill=TEXT),
    ]
    for b in online_boxes:
        draw_round_box(draw, b, box_title_font, box_body_font)

    draw_arrow(draw, (1342, 335), (1380, 335))
    draw_arrow(draw, (1600, 335), (1638, 335))
    draw_arrow(draw, (1852, 335), (1890, 335))
    draw_arrow(draw, (1990, 394), (1990, 470), color=GOLD)
    draw_arrow(draw, (1990, 335), (1250, 470), color=GOLD)
    draw_arrow(draw, (1990, 335), (1510, 470), color=GOLD)
    draw_arrow(draw, (1990, 335), (1770, 470), color=GOLD)
    draw_arrow(draw, (1630, 588), (1443, 664), color=BLUE_2)
    draw_arrow(draw, (1870, 529), (1910, 529), color=GOLD)
    draw_arrow(draw, (1770, 588), (1770, 664), color=BLUE_2)
    draw_arrow(draw, (1558, 723), (1596, 723), color=BLUE_2)
    draw_arrow(draw, (1810, 723), (1848, 723), color=BLUE_2)
    draw_arrow(draw, (2090, 529), (2090, 684), color=GOLD)

    draw.text((1138, 836), "核心结论：城市级泛问优先 POI，具体景点深问优先本地 RAG，需要两者时再做融合。", font=panel_title_font, fill=TEXT)
    draw.text((1138, 872), "这样既保住了实时性和覆盖率，也保住了你项目里最有差异化价值的私域攻略内容。", font=panel_body_font, fill=MUTED)

    img.save(PNG_PATH)


def svg_box(box: Box) -> str:
    lines = []
    lines.append(
        f'<rect x="{box.x}" y="{box.y}" rx="24" ry="24" width="{box.w}" height="{box.h}" '
        f'fill="{box.fill}" stroke="{box.stroke}" stroke-width="3"/>'
    )
    lines.append(
        f'<text x="{box.x + 26}" y="{box.y + 46}" font-family="Microsoft YaHei, Arial" '
        f'font-size="24" font-weight="700" fill="{box.title_fill}">{escape(box.title)}</text>'
    )
    base_y = box.y + 84
    for idx, line in enumerate(box.lines):
        lines.append(
            f'<text x="{box.x + 26}" y="{base_y + idx * 38}" font-family="Microsoft YaHei, Arial" '
            f'font-size="20" fill="{box.body_fill}">{escape(line)}</text>'
        )
    return "\n".join(lines)


def escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def svg_arrow(start: tuple[int, int], end: tuple[int, int], color: str) -> str:
    sx, sy = start
    ex, ey = end
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex > sx else -1
        p1 = (ex - 18 * direction, ey - 10)
        p2 = (ex - 18 * direction, ey + 10)
    else:
        direction = 1 if ey > sy else -1
        p1 = (ex - 10, ey - 18 * direction)
        p2 = (ex + 10, ey - 18 * direction)
    return (
        f'<line x1="{sx}" y1="{sy}" x2="{ex}" y2="{ey}" stroke="{color}" stroke-width="5"/>'
        f'<polygon points="{ex},{ey} {p1[0]},{p1[1]} {p2[0]},{p2[1]}" fill="{color}"/>'
    )


def svg_label(x: int, y: int, text: str, fill: str) -> str:
    w = 150 + len(text) * 8
    return (
        f'<rect x="{x}" y="{y}" rx="16" ry="16" width="{w}" height="46" fill="{fill}"/>'
        f'<text x="{x + 18}" y="{y + 30}" font-family="Microsoft YaHei, Arial" '
        f'font-size="22" font-weight="700" fill="#FFFFFF">{escape(text)}</text>'
    )


def create_svg() -> None:
    offline_boxes = [
        Box(118, 276, 220, 118, "多源数据", ["Kaggle / CrossWOZ", "手写攻略 / China312 / HK QA"]),
        Box(370, 276, 210, 118, "统一 Schema", ["spots_knowledge.json"]),
        Box(612, 276, 210, 118, "向量构建", ["build_spot_vectors.py"]),
        Box(118, 470, 320, 128, "拼接文本", ["city + district + spot_name", "+ tags + content"]),
        Box(476, 470, 240, 128, "Embedding", ["bge-small-zh-v1.5", "512 维向量"]),
        Box(754, 470, 214, 128, "索引落盘", ["storage/doecment.json", "storage/faiss_index.bin"]),
        Box(188, 684, 700, 112, "结果", ["得到本地可运行的 CPU 版 Hybrid RAG 底座"], fill="#EDF6EE", stroke="#B7D6BD", title_fill=TEAL, body_fill=TEXT),
    ]
    online_boxes = [
        Box(1136, 276, 206, 118, "用户问题", ["景点推荐 / 攻略", "避坑 / 路线相关"]),
        Box(1380, 276, 220, 118, "travel_router", ["识别为景点意图", "转发给 spot_agent"]),
        Box(1638, 276, 214, 118, "spot_agent", ["通过 MCP 调工具"]),
        Box(1890, 276, 200, 118, "问题分流", ["泛推荐 / 深问 / 都要"]),
        Box(1140, 470, 220, 118, "search_spots", ["城市级泛推荐", "优先走高德 POI"]),
        Box(1400, 470, 230, 118, "search_local_knowledge", ["具体景点深问", "走本地 RAG"]),
        Box(1670, 470, 200, 118, "search_combined", ["深度攻略 + 实时 POI"]),
        Box(1910, 470, 180, 118, "高德 POI", ["地址 / 电话", "实时候选"]),
        Box(1328, 664, 230, 118, "Hybrid RAG", ["FAISS dense", "+ BM25-like", "+ 手写攻略 bonus"]),
        Box(1596, 664, 214, 118, "融合排序", ["5*dense + bm25 + bonus", "输出 Top-5 文档"]),
        Box(1848, 648, 242, 150, "最终回答", ["POI 提供地址 / 电话", "RAG 提供攻略 / 避坑", "两类信息合并输出"], fill="#EDF6EE", stroke="#B7D6BD", title_fill=TEAL, body_fill=TEXT),
    ]

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<text x="84" y="104" font-family="Microsoft YaHei, Arial" font-size="48" font-weight="700" fill="{BLUE}">RAG：从建库到在线回答</text>',
        f'<text x="88" y="144" font-family="Microsoft YaHei, Arial" font-size="24" fill="{MUTED}">适合放在答辩 PPT 的宽版流程图：左边说明离线建库，右边说明在线查询和融合回答。</text>',
        f'<rect x="74" y="184" rx="28" ry="28" width="934" height="684" fill="{PANEL_2}" stroke="#D6DFEB" stroke-width="3"/>',
        f'<rect x="1090" y="184" rx="28" ry="28" width="1036" height="684" fill="#FFFCF1" stroke="#E8D9A9" stroke-width="3"/>',
        svg_label(112, 202, "离线建库", TEAL),
        svg_label(1128, 202, "在线查询", GOLD),
    ]
    parts.extend(svg_box(box) for box in offline_boxes)
    parts.extend(svg_box(box) for box in online_boxes)
    for arrow in [
        svg_arrow((338, 335), (370, 335), TEAL),
        svg_arrow((580, 335), (612, 335), TEAL),
        svg_arrow((220, 394), (220, 470), TEAL),
        svg_arrow((720, 394), (720, 470), TEAL),
        svg_arrow((438, 534), (476, 534), TEAL),
        svg_arrow((716, 534), (754, 534), TEAL),
        svg_arrow((861, 598), (861, 684), TEAL),
        svg_arrow((1342, 335), (1380, 335), BLUE),
        svg_arrow((1600, 335), (1638, 335), BLUE),
        svg_arrow((1852, 335), (1890, 335), BLUE),
        svg_arrow((1990, 394), (1990, 470), GOLD),
        svg_arrow((1990, 335), (1250, 470), GOLD),
        svg_arrow((1990, 335), (1510, 470), GOLD),
        svg_arrow((1990, 335), (1770, 470), GOLD),
        svg_arrow((1630, 588), (1443, 664), BLUE_2),
        svg_arrow((1870, 529), (1910, 529), GOLD),
        svg_arrow((1770, 588), (1770, 664), BLUE_2),
        svg_arrow((1558, 723), (1596, 723), BLUE_2),
        svg_arrow((1810, 723), (1848, 723), BLUE_2),
        svg_arrow((2090, 529), (2090, 684), GOLD),
    ]:
        parts.append(arrow)
    parts.append(
        f'<text x="1138" y="836" font-family="Microsoft YaHei, Arial" font-size="22" font-weight="700" fill="{TEXT}">'
        "核心结论：城市级泛问优先 POI，具体景点深问优先本地 RAG，需要两者时再做融合。"
        "</text>"
    )
    parts.append(
        f'<text x="1138" y="872" font-family="Microsoft YaHei, Arial" font-size="18" fill="{MUTED}">'
        "这样既保住了实时性和覆盖率，也保住了你项目里最有差异化价值的私域攻略内容。"
        "</text>"
    )
    parts.append("</svg>")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    create_png()
    create_svg()
    print(PNG_PATH)
    print(SVG_PATH)


if __name__ == "__main__":
    main()
