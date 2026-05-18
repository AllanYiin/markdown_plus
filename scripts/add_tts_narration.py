from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
SRC_VIDEO = (
    ROOT.parent
    / "benchmark"
    / "results"
    / "research_report"
    / "research_report_03"
    / "row_vs_block_reading_explainer.mp4"
)
TIMED_VIDEO = ROOT / "out" / "row_vs_block_reading_explainer_tts_timed_video.mp4"
WORK_OUT = ROOT / "out" / "row_vs_block_reading_explainer_narrated_natural.mp4"
SEGMENT_DIR = ROOT / "out" / "tts_segments"
SCENE_DURATIONS_JSON = ROOT / "out" / "tts_scene_durations.json"

VOICE = "coral"
MODEL = "gpt-4o-mini-tts"

SEGMENTS = [
    "這段影片比較兩種長文件讀取方式。題目是，從性價比來看該選擇哪個向量資料庫。答案是 Milvus。我們會看 Plain CLI 的按列讀取，以及 Markdown plus 的按 block 讀取。請注意，這裡展示的是本地重現的工具流程，不是把完整文件送到雲端模型。",
    "測試基礎來自 research report 03。同一份內容有兩個版本，傳統 markdown 檔放在 Plain CLI 分頁，Markdown plus 檔放在 Markdown plus 分頁。因為安全限制，原始文件全文沒有外送；這裡只把旁白稿送到 OpenAI TTS 產生語音。",
    "先看 Plain CLI。它只有一個 bash 工具，可以使用 grep、head、sed、nl 等一般命令。策略通常是先用多關鍵字 grep 找候選行，再用行號去讀上下文。這很接近真實終端機，但模型必須自己決定接下來要讀哪幾行。",
    "Plain CLI 找到很多包含 Milvus 或成本的候選行。最後關鍵證據在一千零七十三行附近的成本優先排序，以及一千二百八十三行附近的推薦決策。這些行指出，最低長期成本與高性能的選擇是 Milvus 自管。",
    "再看 Markdown plus。它不是用行號猜位置，而是先呼叫 mdp search blocks。搜尋詞包含性價比、成本優先、最低長期成本與性能最佳化。回傳結果直接帶出 block id，例如 cost first ranking 和 recommended decision。",
    "接著只需要 read block 讀取相關小段。cost first ranking 說明成本優先時，排序第一是 Milvus 自管。recommended decision 則說明最低長期成本與高性能時，選擇 Milvus 自管。證據的邊界很清楚，也方便引用 block id。",
    "從工具輸出的上下文 token 來看，Plain CLI 約一千九百八十九個 token，Markdown plus 約一千零七十七個 token。也就是這一題中，Markdown plus 約少百分之四十六的工具上下文。即使 Markdown plus 原檔比較大，查詢時仍只回傳相關 block。",
    "兩者的本質差異在索引粒度。Plain CLI 是列與行號導向，先找到候選，再拉上下文。Markdown plus 是 block 導向，先找語意區塊，再讀精準內容。前者通用，後者更節省上下文，而且更容易產生穩定引用。",
    "結論是，若從性價比，也就是長期成本與性能綜合來看，這份報告建議選擇 Milvus 自管。但這個答案有條件，團隊需要具備 Kubernetes、監控、效能調校與平台工程能力。影片的重點，是 Markdown plus 用 block 工具把搜尋範圍縮小，因此在本題更省 token。",
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def duration(path: Path) -> float:
    p = subprocess.run(
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
        text=True,
        stdout=subprocess.PIPE,
    )
    return float(p.stdout.strip())


def main() -> None:
    if not SRC_VIDEO.is_file():
        raise FileNotFoundError(SRC_VIDEO)

    client = OpenAI()
    ROOT.joinpath("out").mkdir(parents=True, exist_ok=True)
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    raw_segments: list[Path] = []
    metadata: list[dict] = []
    scene_durations: list[float] = []
    for idx, text in enumerate(SEGMENTS, start=1):
        raw = SEGMENT_DIR / f"seg_{idx:02d}.mp3"
        if not raw.is_file() or raw.stat().st_size == 0:
            response = client.audio.speech.create(
                model=MODEL,
                voice=VOICE,
                input=text,
                instructions=(
                    "使用自然、專業、清楚的台灣華語旁白語氣。"
                    "節奏穩定，適合技術解說影片。"
                    "請注意：這是 AI 生成旁白，不是真人錄音。"
                ),
            )
            raw.write_bytes(response.read())
        raw_sec = duration(raw)
        raw_segments.append(raw)
        # Keep the original TTS speed. The video timeline follows the audio
        # duration instead of time-stretching narration to a fixed scene length.
        scene_sec = raw_sec
        scene_durations.append(scene_sec)
        metadata.append({
            "scene": idx,
            "audio_sec": round(raw_sec, 3),
            "video_scene_sec": round(scene_sec, 3),
            "chars_sent_to_tts": len(text),
            "audio_path": str(raw),
        })

    SCENE_DURATIONS_JSON.write_text(
        json.dumps(scene_durations, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["ROW_BLOCK_SCENE_DURATIONS"] = str(SCENE_DURATIONS_JSON)
    env["ROW_BLOCK_VIDEO_OUT"] = str(TIMED_VIDEO)
    subprocess.run(
        ["python", str(ROOT / "scripts" / "render_row_vs_block_video.py")],
        check=True,
        cwd=str(ROOT),
        env=env,
    )

    concat = ROOT / "out" / "tts_concat.txt"
    concat.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in raw_segments),
        encoding="utf-8",
    )
    narration = ROOT / "out" / "narration_natural.m4a"
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
        str(narration),
    ])
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(TIMED_VIDEO),
        "-i",
        str(narration),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(WORK_OUT),
    ])

    report = {
        "model": MODEL,
        "voice": VOICE,
        "source_video": str(TIMED_VIDEO),
        "source_policy": "Video duration follows the original TTS audio. No atempo compression is applied.",
        "narration_audio": str(narration),
        "output": str(WORK_OUT),
        "duration_sec": round(duration(WORK_OUT), 3),
        "segments": metadata,
    }
    (ROOT / "out" / "tts_narration_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
