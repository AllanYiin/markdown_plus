from __future__ import annotations

import json
import math
import os
import textwrap
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "codex-local-analysis.json"
OUT = (
    ROOT
    / "out"
    / "row_vs_block_reading_explainer.mp4"
)

W, H = 1280, 720
FPS = 12

BG = (246, 248, 252)
INK = (18, 28, 45)
MUTED = (85, 99, 120)
BLUE = (55, 92, 255)
CYAN = (10, 148, 190)
GREEN = (28, 157, 90)
ORANGE = (238, 142, 46)
RED = (210, 76, 76)
CARD = (255, 255, 255)
BORDER = (211, 220, 235)
CODE_BG = (23, 30, 45)
CODE_FG = (221, 232, 245)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


F = {
    "title": font(46, True),
    "h1": font(34, True),
    "h2": font(26, True),
    "body": font(22),
    "body_b": font(22, True),
    "small": font(17),
    "mono": font(17),
    "mono_s": font(14),
}


def draw_round(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, outline=BORDER, radius=14, width=1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fnt, fill=INK, max_width: int | None = None, line_gap: int = 8) -> int:
    x, y = xy
    if not max_width:
        draw.text((x, y), text, font=fnt, fill=fill)
        return y + draw.textbbox((x, y), text, font=fnt)[3] - y
    avg = max(1, int(max_width / max(8, fnt.size * 0.58)))
    lines: list[str] = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(para, width=avg, break_long_words=False, replace_whitespace=False))
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + line_gap
    return y


def code_block(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, lines: list[str], title: str | None = None) -> None:
    draw_round(draw, (x, y, x + w, y + h), CODE_BG, outline=(39, 52, 76), radius=12)
    yy = y + 16
    if title:
        draw.text((x + 18, yy), title, font=F["small"], fill=(132, 218, 255))
        yy += 30
    for line in lines[: int((h - 40) / 24)]:
        draw.text((x + 18, yy), line, font=F["mono_s"], fill=CODE_FG)
        yy += 24


def pill(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fill, fg=(255, 255, 255)) -> int:
    bbox = draw.textbbox((0, 0), text, font=F["small"])
    w = bbox[2] + 24
    draw.rounded_rectangle((x, y, x + w, y + 30), radius=15, fill=fill)
    draw.text((x + 12, y + 6), text, font=F["small"], fill=fg)
    return x + w + 10


def ui_header(draw: ImageDraw.ImageDraw, active: str = "Markdown+") -> None:
    draw_round(draw, (40, 34, 1240, 104), CARD, radius=10)
    x = 64
    for label, hint in [("Markdown+", "tools"), ("Plain CLI", "bash")]:
        active_tab = label == active
        color = BLUE if active_tab else INK
        draw.text((x, 58), label, font=F["body_b"], fill=color)
        draw.text((x + 142, 63), hint, font=F["small"], fill=(80, 95, 140))
        if active_tab:
            draw.line((x, 100, x + 172, 100), fill=BLUE, width=4)
        x += 220
    draw.text((1040, 58), "✓ local replay", font=F["small"], fill=GREEN)


def draw_progress(draw: ImageDraw.ImageDraw, frame: int, total_frames: int) -> None:
    p = frame / max(1, total_frames - 1)
    draw.rectangle((0, H - 8, W, H), fill=(218, 225, 238))
    draw.rectangle((0, H - 8, int(W * p), H), fill=BLUE)


def bars(draw: ImageDraw.ImageDraw, x: int, y: int, plain: int, block: int, anim: float) -> None:
    max_v = max(plain, block)
    for i, (label, value, color) in enumerate([("Plain CLI", plain, ORANGE), ("Markdown+", block, GREEN)]):
        yy = y + i * 74
        draw.text((x, yy), label, font=F["body_b"], fill=INK)
        bw = int(500 * value / max_v * min(1, anim))
        draw.rounded_rectangle((x + 170, yy + 4, x + 170 + bw, yy + 32), radius=7, fill=color)
        draw.text((x + 690, yy + 2), f"{value:,} tokens", font=F["body"], fill=INK)


def base_frame(title: str, subtitle: str | None = None, active: str = "Markdown+") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    ui_header(draw, active)
    draw.text((58, 132), title, font=F["h1"], fill=INK)
    if subtitle:
        draw.text((60, 176), subtitle, font=F["body"], fill=MUTED)
    return img, draw


def scene_title(t: float, data: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.text((74, 88), "Row reading vs Block reading", font=F["title"], fill=INK)
    draw.text((78, 154), "同一題：從性價比來看該選擇哪個向量資料庫？", font=F["h2"], fill=MUTED)
    pulse = 0.6 + 0.4 * math.sin(t * math.pi * 2)
    draw.rounded_rectangle((78, 240, 1202, 410), radius=22, fill=(255, 255, 255), outline=BORDER)
    draw.text((118, 282), "答案：Milvus", font=F["title"], fill=GREEN)
    draw.text((118, 350), "資料來源：research_report_03 / markdown.md + markdown_plus.md", font=F["body"], fill=MUTED)
    draw.ellipse((980, 252, 1080, 352), fill=(55, 92, 255, int(255 * pulse)))
    draw.text((1005, 284), "M", font=F["h1"], fill=(255, 255, 255))
    return img


def scene_setup(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("測試設計", "因安全限制，未將本機文件外送到 OpenAI；以下是本地重現工具流程。")
    x = 78
    y = 235
    x = pill(draw, x, y, "Markdown+ tab 載 markdown_plus.md", BLUE)
    pill(draw, x, y, "Plain CLI tab 載 markdown.md", ORANGE)
    draw_round(draw, (76, 306, 590, 510), CARD, radius=14)
    draw_round(draw, (690, 306, 1204, 510), CARD, radius=14)
    draw.text((112, 334), "Plain Markdown", font=F["h2"], fill=INK)
    draw.text((112, 382), f"{data['files']['plain']['lines']:,} lines", font=F["body"], fill=MUTED)
    draw.text((112, 424), f"{data['files']['plain']['tokens']:,} raw doc tokens", font=F["body"], fill=MUTED)
    draw.text((724, 334), "Markdown+", font=F["h2"], fill=INK)
    draw.text((724, 382), f"{data['files']['markdown_plus']['lines']:,} lines", font=F["body"], fill=MUTED)
    draw.text((724, 424), f"{data['files']['markdown_plus']['tokens']:,} raw doc tokens", font=F["body"], fill=MUTED)
    draw.text((82, 565), "比較的是工具輸出的上下文 token，不是雲端模型實際 usage。", font=F["body_b"], fill=RED)
    return img


def scene_plain_mech(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("Plain CLI：按 row / line 逐步定位", "策略：先 grep 找候選行，再用 nl + sed 拉出附近上下文。", active="Plain CLI")
    cmds = [x["command"] for x in data["plain_cli"]]
    code_block(draw, 70, 228, 1140, 300, cmds, "工具調用：bash(command)")
    draw_text(draw, (78, 560), "它沒有 block id，也不知道章節語意。搜尋結果回來的是行號，因此下一步必須手動決定要讀哪一段行範圍。", F["body"], fill=INK, max_width=1100)
    return img


def scene_plain_evidence(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("Plain CLI 找到的證據", "行號視角：候選很多，最後靠 1073 與 1283 附近確認答案。", active="Plain CLI")
    lines = [
        "1073  ## 14.1 若以成本優先",
        "1077  1. **Milvus 自管**",
        "1083  - Milvus 自管在大規模資料量下單位成本較低。",
        "",
        "1279  ## 16.2 推薦決策",
        "1283  - **最低長期成本與高性能**：選擇 **Milvus 自管**",
        "1287  建議以 **Milvus 作為主要 PoC 對象**",
    ]
    code_block(draw, 70, 218, 1140, 350, lines, "stdout excerpt")
    draw.text((80, 600), "優點：接近真實 terminal。代價：需要讀較多行與候選命中。", font=F["body_b"], fill=ORANGE)
    return img


def scene_block_mech(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("Markdown+：按 block 漸進式讀取", "策略：先 search block metadata/snippet，再 read 精準 block body。")
    search = data["markdown_plus"][0]
    code_block(
        draw,
        70,
        220,
        1140,
        245,
        [
            "mdp_search_blocks({",
            "  any_of: ['性價比','成本優先','最低長期成本','性能最佳化'],",
            "  limit: 8",
            "})",
        ],
        "第一步：只回傳 block 摘要與片段",
    )
    ids = [r["id"] for r in search["result"]]
    x = 78
    for bid in ids:
        x = pill(draw, x, 500, "#" + bid, GREEN if bid in {"cost-first-ranking", "recommended-decision"} else CYAN)
    draw.text((80, 565), "工具輸出直接帶出可讀的 block id，模型不需要猜行號。", font=F["body_b"], fill=GREEN)
    return img


def scene_block_evidence(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("Markdown+ 讀到的兩個關鍵 block", "block 視角：證據本身帶有 id、type、line 與完整小段內容。")
    lines = [
        "mdp_read_block(id='cost-first-ranking', include_children=true)",
        "  若以成本優先，建議排序：",
        "  1. Milvus 自管",
        "  2. Weaviate 自管",
        "  3. Pinecone",
        "",
        "mdp_read_block(id='recommended-decision', include_children=true)",
        "  最低長期成本與高性能：選擇 Milvus 自管",
    ]
    code_block(draw, 70, 218, 1140, 355, lines, "函數調用與回傳重點")
    draw.text((80, 608), "優點：上下文小、引用穩定，可直接說明證據來自哪個 block。", font=F["body_b"], fill=GREEN)
    return img


def scene_tokens(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("哪一邊比較省 tokens？", "本地估算：只計工具 command + 工具輸出上下文。")
    plain = data["context_token_summary"]["plain_cli"]
    block = data["context_token_summary"]["markdown_plus"]
    bars(draw, 170, 260, plain, block, min(1, t / 1.5))
    saved = round((1 - block / plain) * 100)
    draw.text((170, 470), f"Markdown+ 約少 {saved}% 工具上下文 tokens", font=F["h1"], fill=GREEN)
    draw.text((170, 535), "即使 markdown_plus.md 原檔較大，block 工具只回傳相關 block，因此查詢時仍較省。", font=F["body"], fill=MUTED)
    return img


def scene_strategy(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("搜索策略差異", "兩者都不是全文直接貼給模型；差在可用索引粒度。")
    draw_round(draw, (70, 220, 600, 560), CARD, radius=16)
    draw_round(draw, (680, 220, 1210, 560), CARD, radius=16)
    draw.text((110, 255), "Plain CLI", font=F["h2"], fill=ORANGE)
    draw_text(draw, (110, 315), "1. grep 多關鍵字\n2. head 限制候選\n3. sed/nl 拉行號區間\n4. 人工整理答案", F["body"], max_width=430)
    draw.text((720, 255), "Markdown+", font=F["h2"], fill=GREEN)
    draw_text(draw, (720, 315), "1. search_blocks 找 block\n2. 用 id 選證據\n3. read_block 讀小段內容\n4. 以 block id 回答", F["body"], max_width=430)
    return img


def scene_answer(t: float, data: dict) -> Image.Image:
    img, draw = base_frame("結論", "從性價比來看，答案是 Milvus。")
    draw_round(draw, (90, 235, 1190, 455), CARD, radius=24)
    draw.text((135, 280), "Milvus 自管", font=F["title"], fill=GREEN)
    draw.text((135, 352), "最低長期成本與高性能；但需要 Kubernetes / SRE / 平台工程能力。", font=F["h2"], fill=INK)
    draw_text(draw, (96, 520), "影片重點：Plain CLI 更像逐列搜尋；Markdown+ 透過 block metadata 與 id 將搜尋範圍縮小，所以本題工具上下文較省。", F["body_b"], max_width=1080)
    return img


SCENES = [
    (16, scene_title),
    (20, scene_setup),
    (24, scene_plain_mech),
    (24, scene_plain_evidence),
    (24, scene_block_mech),
    (24, scene_block_evidence),
    (24, scene_tokens),
    (22, scene_strategy),
    (22, scene_answer),
]


def scene_specs() -> list[tuple[float, object]]:
    durations_path = os.environ.get("ROW_BLOCK_SCENE_DURATIONS")
    if not durations_path:
        return SCENES
    durations = json.loads(Path(durations_path).read_text(encoding="utf-8"))
    if len(durations) != len(SCENES):
        raise RuntimeError(f"expected {len(SCENES)} scene durations, got {len(durations)}")
    return [(float(duration), fn) for duration, (_, fn) in zip(durations, SCENES, strict=True)]


def output_path() -> Path:
    override = os.environ.get("ROW_BLOCK_VIDEO_OUT")
    return Path(override) if override else OUT


def main() -> None:
    data = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    out = output_path()
    scenes = scene_specs()
    out.parent.mkdir(parents=True, exist_ok=True)
    total_frames = sum(max(1, math.ceil(duration * FPS)) for duration, _ in scenes)
    frame_index = 0
    with imageio.get_writer(
        str(out),
        fps=FPS,
        codec="libx264",
        quality=8,
        macro_block_size=16,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    ) as writer:
        for duration, fn in scenes:
            scene_frames = max(1, math.ceil(duration * FPS))
            for i in range(scene_frames):
                t = i / FPS
                img = fn(t, data)
                overlay = ImageDraw.Draw(img)
                draw_progress(overlay, frame_index, total_frames)
                writer.append_data(np.array(img))
                frame_index += 1
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"video writer did not create output: {out}")
    print(f"rendered {out}")
    print(f"duration_sec={total_frames / FPS:.3f}")


if __name__ == "__main__":
    main()
