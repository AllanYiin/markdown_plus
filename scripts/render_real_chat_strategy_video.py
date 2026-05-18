from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import cv2
import imageio.v2 as imageio
import numpy as np
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out" / "real-chat-demo"
REPORT_PATH = OUT_DIR / "real_chat_recording_report.json"
SOURCE_VIDEO = OUT_DIR / "real_chat_demo.webm"
VISUAL_VIDEO = OUT_DIR / "real_chat_strategy_visual.mp4"
FINAL_VIDEO = OUT_DIR / "real_chat_strategy_narrated.mp4"
NARRATION_AUDIO = OUT_DIR / "real_chat_strategy_narration.m4a"
SEGMENT_DIR = OUT_DIR / "tts_segments"
REPORT_OUT = OUT_DIR / "real_chat_strategy_video_report.json"

MODEL = "gpt-4o-mini-tts"
VOICE = "coral"
FPS = 15
W, H = 1280, 720

INK = (20, 28, 45)
MUTED = (83, 95, 116)
WHITE = (255, 255, 255)
PANEL = (248, 250, 252)
BLUE = (55, 92, 255)
CYAN = (12, 148, 190)
GREEN = (30, 158, 88)
ORANGE = (230, 133, 45)
RED = (204, 70, 70)
BORDER = (210, 220, 235)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return float(result.stdout.strip())


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/NotoSansTC-Bold.ttf" if bold else "C:/Windows/Fonts/NotoSansTC-Regular.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for item in candidates:
        try:
            return ImageFont.truetype(item, size)
        except OSError:
            continue
    return ImageFont.load_default()


F = {
    "title": font(42, True),
    "h1": font(34, True),
    "h2": font(26, True),
    "body": font(22),
    "body_b": font(22, True),
    "small": font(17),
    "tiny": font(14),
    "mono": font(17),
}


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, outline=BORDER, radius=16, width=1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        current = ""
        for ch in para:
            probe = current + ch
            if draw.textlength(probe, font=font_obj) <= max_width:
                current = probe
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
        if not para:
            lines.append("")
    return lines


def draw_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font_obj: ImageFont.FreeTypeFont,
    fill=INK,
    max_width: int = 600,
    gap: int = 8,
) -> int:
    x, y = xy
    for line in wrap_text(draw, text, font_obj, max_width):
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += font_obj.size + gap
    return y


class VideoFrames:
    def __init__(self, path: Path):
        self.path = path
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
        self.count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        self.duration = self.count / self.fps
        self.cache: dict[int, Image.Image] = {}

    def frame(self, seconds: float) -> Image.Image:
        seconds = max(0.0, min(seconds, max(0.0, self.duration - 0.05)))
        idx = int(seconds * self.fps)
        if idx not in self.cache:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, self.count - 2))
                ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError(f"Cannot read frame at {seconds}")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.cache[idx] = Image.fromarray(frame).resize((W, H), Image.Resampling.LANCZOS)
        return self.cache[idx].copy()


def darken(img: Image.Image, amount: int = 72) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (8, 14, 28, amount))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def glass_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill_alpha: int = 235) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=18, fill=(255, 255, 255, fill_alpha), outline=(205, 216, 235, 255), width=1)
    draw.line((x1 + 22, y1 + 58, x2 - 22, y1 + 58), fill=(222, 229, 240, 255), width=1)


def status_tokens(status: str) -> tuple[int, int, int, int]:
    import re

    input_total = int(re.search(r"input ([\d,]+) tok", status).group(1).replace(",", ""))
    uncached_match = re.search(r"\(([\d,]+) uncached", status)
    uncached = int(uncached_match.group(1).replace(",", "")) if uncached_match else input_total
    output = int(re.search(r"output ([\d,]+) tok", status).group(1).replace(",", ""))
    total = int(re.search(r"total ([\d,]+) tok", status).group(1).replace(",", ""))
    return input_total, uncached, output, total


def extract_commands(report: dict) -> dict:
    blocks_calls = [c for c in report["blocks"]["cards"] if c["kind"] == "CALL"]
    plain_calls = [c for c in report["plain"]["cards"] if c["kind"] == "CALL"]
    return {
        "blocks": [c["name"] for c in blocks_calls],
        "plain": [json.loads(c["body"])["command"] for c in plain_calls],
    }


def script_segments(report: dict) -> list[dict]:
    b_input, b_uncached, b_output, b_total = status_tokens(report["blocks"]["status"])
    p_input, p_uncached, p_output, p_total = status_tokens(report["plain"]["status"])
    if b_total <= p_total:
        total_compare = f"本次 Markdown plus 較省，少用約 {((1 - b_total / p_total) * 100):.1f}% total tokens。"
    else:
        total_compare = f"本次 Plain CLI 較省，少用約 {((1 - p_total / b_total) * 100):.1f}% total tokens。"
    if b_uncached <= p_uncached:
        uncached_compare = f"只看 uncached input，Markdown plus 也較低，少約 {((1 - b_uncached / p_uncached) * 100):.1f}%。"
    else:
        uncached_compare = f"只看 uncached input，Plain CLI 也較低，少約 {((1 - p_uncached / b_uncached) * 100):.1f}%。"

    return [
        {
            "id": "hook",
            "style": "explain",
            "title": "真實查詢 UI：row 讀取 vs block 讀取",
            "tts": (
                "這版影片改用真實 chat.html 操作錄影，不再只做抽象動畫。"
                "同一個測試題目是，從性價比來看該選擇哪個向量資料庫。"
                "答案本身不是重點，重點是模型怎麼用工具找到證據，以及每一邊花了多少 token。"
            ),
            "source": (0, 8),
        },
        {
            "id": "setup_operation",
            "style": "operation",
            "title": "乾淨操作：載入兩份文件",
            "tts": (
                "先看完整介面操作。這一段不加任何後製標題、卡片或字幕，"
                "只保留真實 chat.html 畫面與滑鼠游標。Markdown plus 分頁載入 markdown_plus.md，"
                "Plain CLI 分頁載入 markdown.md。"
            ),
            "source": (8, 18),
        },
        {
            "id": "setup",
            "style": "explain",
            "title": "操作完成後再補充載入設定",
            "tts": (
                "載入動作完成後，才出現說明標註。兩份文件各自留在對應分頁；"
                "這次已依照你的批准，文件透過本機頁面與本機 API 送到 OpenAI，"
                "用於錄製真實查詢 UI 與工具調用流程。旁白合成只送旁白稿，不送原始 research report 全文。"
            ),
            "source": (18, 18),
        },
        {
            "id": "blocks_operation",
            "style": "operation",
            "title": "乾淨操作：Markdown+ 查詢",
            "tts": (
                "接著看 Markdown plus 分頁的查詢操作。這段仍然不遮擋畫面。"
                "你可以直接看到送出問題、工具卡逐步出現，以及最後回答的 UI 狀態。"
            ),
            "source": (18, 37),
        },
        {
            "id": "blocks_analysis",
            "style": "explain",
            "title": "Markdown+ 實際工具鏈",
            "tts": (
                "操作完成後再看標註。實際工具卡顯示，Markdown plus 先呼叫 mdp_search_blocks，"
                "用性價比、向量資料庫，以及 vector database 這類關鍵字找候選 block。"
                "接著它讀 summary，連同 core-conclusions、cost-summary 等子區塊，"
                "又讀了 Milvus、Weaviate、Pinecone 三個 overview block。"
                "也就是說，這輪 Markdown plus 能找到答案，但策略偏保守，讀了比必要更多的比較背景。"
            ),
            "source": (35, 35),
        },
        {
            "id": "plain_operation",
            "style": "operation",
            "title": "乾淨操作：Plain CLI 查詢",
            "tts": (
                "再看 Plain CLI 分頁。這段同樣只看操作，不加遮擋物。"
                "模型在真實限制下自己下 bash，工具卡會展示它實際送出的命令和回傳結果。"
            ),
            "source": (39, 58),
        },
        {
            "id": "plain_analysis",
            "style": "explain",
            "title": "Plain CLI 實際搜尋策略",
            "tts": (
                "Plain CLI 操作完成後再補說明。這裡不是另外開發 plain_read_lines 或 plain_search，"
                "而是讓模型自己下 bash。這輪它先用 grep 搜尋 vector、向量、性價比、cost、price、performance 等關鍵字，"
                "很快在文件前段找到成本表。"
                "第二步嘗試用 sed 讀兩段行號，其中一段命令在 fallback 中有 printf 限制警告；"
                "第三步改用 python3 heredoc 把指定行號區間印出來。"
                "也就是說，row 讀取不是只看前 N 行的硬限制；模型會自己組合搜尋、行號閱讀與替代命令。"
            ),
            "source": (58, 66),
        },
        {
            "id": "token_compare",
            "style": "explain",
            "title": "這一次哪邊 token 較省？",
            "tts": (
                f"以頁面查詢後顯示的 usage 來看，Markdown plus 這題 total 是 {b_total:,} tokens，"
                f"Plain CLI 是 {p_total:,} tokens。{total_compare}"
                f"如果只看 uncached input，Markdown plus 是 {b_uncached:,}，Plain CLI 是 {p_uncached:,}，"
                f"{uncached_compare}"
            ),
            "source": (66, 66),
        },
        {
            "id": "strategy_compare",
            "style": "explain",
            "title": "差異不在工具名字，而在上下文邊界",
            "tts": (
                "兩邊其實都有工具定義，也都會有工具呼叫和工具結果。"
                "Plain CLI 的優點是接近真實終端機，grep、sed、nl 都透明；缺點是上下文邊界靠模型自己抓。"
                "Markdown plus 的優點是文件先被切成 block，搜尋回來的是比較小且有語義邊界的片段，"
                "所以更容易少帶無關內容。"
            ),
            "source": (30, 66),
        },
        {
            "id": "answer",
            "style": "explain",
            "title": "測試題答案只是驗證路徑",
            "tts": (
                "這題最後兩邊都回答 Milvus。"
                "Markdown plus 的證據來自 core-conclusions block，Plain CLI 的證據來自行號二五四三、二五六五與九十九附近。"
                "但這不是在證明 Milvus 永遠最好，而是在證明兩種讀取機制能不能穩定找到證據，"
                "以及同一題下哪個機制比較節省上下文。"
            ),
            "source": (66, 70),
        },
        {
            "id": "closing",
            "style": "explain",
            "title": "結論",
            "tts": (
                "結論是，這次真實 UI 查詢中，Markdown plus 以 block 搜尋加 block 讀取完成定位，"
                "Plain CLI 則以 grep 加行號範圍閱讀完成定位。"
                "兩者都能答對，但實際 token 成本會受到搜尋策略影響。"
                "這次 Markdown plus 多讀了幾個 overview block，因此不應該硬說它必然較省。"
                "影片要強調的是機制差異、工具策略與可觀察的 token 成本，而不是那個向量資料庫答案本身。"
            ),
            "source": (66, 70),
        },
    ]


def synthesize_tts(segments: list[dict]) -> list[Path]:
    client = OpenAI()
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for idx, segment in enumerate(segments, start=1):
        out = SEGMENT_DIR / f"real_{idx:02d}_{segment['id']}.mp3"
        text_marker = out.with_suffix(".txt")
        needs_regen = (
            not out.is_file()
            or out.stat().st_size == 0
            or not text_marker.is_file()
            or text_marker.read_text(encoding="utf-8") != segment["tts"]
        )
        if needs_regen:
            response = client.audio.speech.create(
                model=MODEL,
                voice=VOICE,
                input=segment["tts"],
                instructions=(
                    "使用自然、穩定、專業的台灣華語技術解說語氣。"
                    "語速不要忽快忽慢，保留停頓讓觀眾看清楚畫面。"
                    "請注意：這是 AI 生成旁白。"
                ),
            )
            out.write_bytes(response.read())
            text_marker.write_text(segment["tts"], encoding="utf-8")
        paths.append(out)
    return paths


def draw_badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, color) -> int:
    width = int(draw.textlength(text, font=F["small"])) + 24
    draw.rounded_rectangle((x, y, x + width, y + 30), radius=15, fill=color)
    draw.text((x + 12, y + 5), text, font=F["small"], fill=WHITE)
    return x + width + 10


def overlay_header(img: Image.Image, title: str, subtitle: str | None = None) -> Image.Image:
    base = darken(img, 58).convert("RGBA")
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((38, 28, 1242, 124), radius=18, fill=(255, 255, 255, 238), outline=(209, 219, 235, 255))
    draw.text((66, 48), title, font=F["h1"], fill=INK)
    if subtitle:
        draw.text((68, 92), subtitle, font=F["small"], fill=MUTED)
    return base.convert("RGB")


def draw_token_chart(draw: ImageDraw.ImageDraw, report: dict, x: int, y: int, w: int) -> None:
    b_input, b_uncached, b_output, b_total = status_tokens(report["blocks"]["status"])
    p_input, p_uncached, p_output, p_total = status_tokens(report["plain"]["status"])
    max_total = max(b_total, p_total)
    rows = [
        ("Markdown+", b_total, b_uncached, GREEN),
        ("Plain CLI", p_total, p_uncached, ORANGE),
    ]
    for idx, (label, total, uncached, color) in enumerate(rows):
        yy = y + idx * 92
        draw.text((x, yy), label, font=F["body_b"], fill=INK)
        bar_w = int((w - 230) * total / max_total)
        draw.rounded_rectangle((x + 150, yy + 4, x + 150 + bar_w, yy + 36), radius=8, fill=color)
        draw.text((x + w - 60, yy + 4), f"{total:,}", font=F["body_b"], fill=INK, anchor="ra")
        draw.text((x + 150, yy + 46), f"uncached input {uncached:,}", font=F["small"], fill=MUTED)


def render_scene_frame(frames: VideoFrames, report: dict, segment: dict, local_t: float, duration: float) -> Image.Image:
    src_start, src_end = segment["source"]
    if src_end > src_start:
        src_time = src_start + min(local_t, src_end - src_start)
    else:
        src_time = src_start
    img = frames.frame(src_time)
    progress = local_t / max(duration, 0.01)

    if segment.get("style") == "operation":
        return img

    if segment["id"] == "hook":
        img = darken(img, 92).convert("RGBA")
        draw = ImageDraw.Draw(img)
        draw.text((72, 90), "Row vs Block", font=F["title"], fill=WHITE)
        draw.text((76, 150), "真實 UI 錄影解析", font=F["h1"], fill=(215, 225, 255))
        rounded(draw, (74, 242, 684, 410), (255, 255, 255, 235), radius=20)
        draw.text((112, 282), "測試題", font=F["small"], fill=MUTED)
        draw_lines(draw, (112, 318), "從性價比來看該選擇哪個向量資料庫？", F["h2"], max_width=520)
        rounded(draw, (740, 242, 1118, 410), (235, 255, 243, 240), outline=(180, 230, 198, 255), radius=20)
        draw.text((782, 285), "答案：Milvus", font=F["title"], fill=GREEN)
        draw.text((78, 608), "重點是搜尋策略與 token 成本，不是向量資料庫評比。", font=F["body_b"], fill=WHITE)
        return img.convert("RGB")

    img = overlay_header(img, segment["title"])
    rgba = img.convert("RGBA")
    draw = ImageDraw.Draw(rgba)

    if segment["id"] == "setup":
        glass_panel(draw, (54, 470, 1226, 662))
        draw.text((84, 492), "載入設定", font=F["h2"], fill=INK)
        x = draw_badge(draw, 84, 558, "Markdown+ / markdown_plus.md", BLUE)
        draw_badge(draw, x, 558, "Plain CLI / markdown.md", ORANGE)
        draw_lines(draw, (84, 602), "兩份文件各自留在對應分頁；清空對話不會清掉已載入文件。", F["body"], max_width=1000)

    elif segment["id"] == "blocks_live":
        glass_panel(draw, (48, 454, 1232, 665))
        draw.text((78, 476), "實際呼叫", font=F["h2"], fill=INK)
        x = draw_badge(draw, 78, 532, "mdp_search_blocks", CYAN)
        draw_badge(draw, x, 532, "mdp_read_block", GREEN)
        draw_lines(draw, (78, 586), "策略：先用 query / any_of 搜尋語意區塊，再讀命中的 block。", F["body_b"], max_width=1080)

    elif segment["id"] == "blocks_analysis":
        glass_panel(draw, (54, 152, 616, 645))
        draw.text((86, 176), "Markdown+ 工具鏈", font=F["h2"], fill=INK)
        y = 238
        for i, item in enumerate(["mdp_search_blocks", "query: 性價比 向量資料庫", "mdp_read_block", "id: core-conclusions"]):
            color = CYAN if i < 2 else GREEN
            y_next = y + 52
            draw.ellipse((90, y + 4, 116, y + 30), fill=color)
            draw.text((132, y), item, font=F["body_b" if i in (0, 2) else "body"], fill=INK)
            if i < 3:
                draw.line((103, y + 32, 103, y_next - 10), fill=(145, 158, 180), width=3)
            y = y_next
        draw_lines(draw, (86, 492), "block 結果有 id、line、title、summary，證據邊界比單純行號更清楚。", F["body"], max_width=470)

    elif segment["id"] == "plain_live":
        glass_panel(draw, (48, 454, 1232, 665))
        draw.text((78, 476), "實際呼叫", font=F["h2"], fill=INK)
        x = draw_badge(draw, 78, 532, "bash", ORANGE)
        x = draw_badge(draw, x, 532, "grep -nEi ... | head", ORANGE)
        draw_badge(draw, x, 532, "nl -ba | sed -n", ORANGE)
        draw_lines(draw, (78, 586), "策略：先搜尋候選行，再依行號回讀上下文。", F["body_b"], max_width=1080)

    elif segment["id"] == "plain_analysis":
        commands = extract_commands(report)["plain"]
        glass_panel(draw, (54, 146, 1224, 660))
        draw.text((86, 170), "Plain CLI 實際 bash", font=F["h2"], fill=INK)
        y = 230
        for idx, cmd in enumerate(commands, start=1):
            rounded(draw, (86, y, 1188, y + 92), (245, 247, 251, 255), radius=10)
            draw.text((108, y + 16), f"{idx}.", font=F["body_b"], fill=ORANGE)
            draw_lines(draw, (150, y + 15), cmd, F["mono"], fill=INK, max_width=980, gap=4)
            y += 112

    elif segment["id"] == "token_compare":
        blurred = rgba.filter(ImageFilter.GaussianBlur(4))
        draw = ImageDraw.Draw(blurred)
        glass_panel(draw, (92, 150, 1188, 620))
        draw.text((126, 176), "查詢後 usage 對比", font=F["h1"], fill=INK)
        draw_token_chart(draw, report, 134, 270, 930)
        b_input, b_uncached, b_output, b_total = status_tokens(report["blocks"]["status"])
        p_input, p_uncached, p_output, p_total = status_tokens(report["plain"]["status"])
        if b_total <= p_total:
            saved_text = f"本次 Markdown+ total 少用約 {(1 - b_total / p_total) * 100:.1f}%"
            saved_color = GREEN
        else:
            saved_text = f"本次 Plain CLI total 少用約 {(1 - p_total / b_total) * 100:.1f}%"
            saved_color = ORANGE
        draw.text((134, 502), saved_text, font=F["h1"], fill=saved_color)
        draw.text((134, 556), "注意：這是本頁 query 顯示的 usage，含 cached / uncached 拆分。", font=F["body"], fill=MUTED)
        rgba = blurred

    elif segment["id"] == "strategy_compare":
        glass_panel(draw, (56, 148, 610, 642))
        glass_panel(draw, (670, 148, 1224, 642))
        draw.text((90, 174), "Plain CLI", font=F["h2"], fill=ORANGE)
        draw_lines(draw, (90, 236), "工具是 bash。模型自己決定 grep 什麼、讀哪幾行、是否回頭補證據。透明但上下文邊界較鬆。", F["body"], max_width=460)
        draw.text((704, 174), "Markdown+", font=F["h2"], fill=GREEN)
        draw_lines(draw, (704, 236), "工具是 mdp_*。先用 block 索引定位，再讀具語義邊界的區塊。通常更少帶無關文字。", F["body"], max_width=460)
        draw.text((90, 512), "兩邊都算工具調用，也都會有工具定義與結果。", font=F["body_b"], fill=INK)

    elif segment["id"] == "answer":
        glass_panel(draw, (66, 468, 1214, 658))
        draw.text((96, 492), "答案路徑", font=F["h2"], fill=INK)
        draw_lines(draw, (96, 548), "Markdown+：core-conclusions block。Plain CLI：第 2543 / 2565 / 99 行附近。", F["body_b"], max_width=980)
        draw_lines(draw, (96, 600), "這裡驗證的是能否穩定找到證據，而不是向量資料庫評比。", F["body"], max_width=980)

    elif segment["id"] == "closing":
        img2 = darken(img, 92).convert("RGBA")
        draw = ImageDraw.Draw(img2)
        draw.text((84, 110), "結論", font=F["title"], fill=WHITE)
        y = 210
        for color, text in [
            (GREEN, "Markdown+：mdp_search_blocks → mdp_read_block"),
            (ORANGE, "Plain CLI：grep → nl/sed 讀行號範圍"),
            (BLUE, "本次查詢 Markdown+ total token 較省"),
        ]:
            draw.ellipse((100, y + 8, 126, y + 34), fill=color)
            draw.text((150, y), text, font=F["h2"], fill=WHITE)
            y += 82
        return img2.convert("RGB")

    draw.rectangle((0, H - 8, int(W * progress), H), fill=BLUE)
    return rgba.convert("RGB")


def render_visual(report: dict, segments: list[dict], durations: list[float]) -> None:
    frames = VideoFrames(SOURCE_VIDEO)
    writer = imageio.get_writer(
        VISUAL_VIDEO,
        fps=FPS,
        codec="libx264",
        quality=8,
        macro_block_size=None,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    try:
        for segment, duration in zip(segments, durations, strict=True):
            frame_count = max(1, int(math.ceil(duration * FPS)))
            for idx in range(frame_count):
                local_t = idx / FPS
                img = render_scene_frame(frames, report, segment, local_t, duration)
                writer.append_data(np.asarray(img))
    finally:
        writer.close()


def concat_audio(paths: list[Path]) -> None:
    concat = OUT_DIR / "real_chat_strategy_audio_concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in paths), encoding="utf-8")
    run([
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(NARRATION_AUDIO),
    ])


def mux() -> None:
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(VISUAL_VIDEO),
        "-i",
        str(NARRATION_AUDIO),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(FINAL_VIDEO),
    ])


def main() -> None:
    if not REPORT_PATH.is_file():
        raise FileNotFoundError(REPORT_PATH)
    if not SOURCE_VIDEO.is_file():
        raise FileNotFoundError(SOURCE_VIDEO)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    segments = script_segments(report)
    audio_paths = synthesize_tts(segments)
    durations = [ffprobe_duration(p) for p in audio_paths]
    render_visual(report, segments, durations)
    concat_audio(audio_paths)
    mux()

    result = {
        "model": MODEL,
        "voice": VOICE,
        "source_video": str(SOURCE_VIDEO),
        "visual_video": str(VISUAL_VIDEO),
        "narration_audio": str(NARRATION_AUDIO),
        "output": str(FINAL_VIDEO),
        "duration_sec": round(ffprobe_duration(FINAL_VIDEO), 3),
        "policy": "Only the narration script was sent to OpenAI TTS. The final video timeline follows original TTS durations; no atempo speed changes are applied.",
        "segments": [
            {
                "id": segment["id"],
                "title": segment["title"],
                "audio_sec": round(duration, 3),
                "chars_sent_to_tts": len(segment["tts"]),
            }
            for segment, duration in zip(segments, durations, strict=True)
        ],
    }
    REPORT_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
