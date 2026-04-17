#!/usr/bin/env python
"""
Extract burned-in subtitles from Bilibili videos with OCR.

The script focuses on anthology videos (multiple parts under a single BVID).
It avoids Bilibili subtitle APIs because they can return mismatched tracks for
some videos. Instead, it:

1. Resolves each page's real video stream through playurl.
2. Uses ffmpeg to sample the subtitle strip at a fixed FPS.
3. Runs OCR on frames selected by a simple image-hash delta.
4. Builds approximate subtitle cues and writes TXT/SRT/JSON outputs.

Outputs are grouped by page under the chosen output directory.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

_OCR = None


@dataclass
class PageInfo:
    page: int
    cid: int
    title: str
    duration: int
    width: int | None = None
    height: int | None = None
    video_url: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bvid", required=True, help="Bilibili BV id")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for extracted subtitle files",
    )
    parser.add_argument(
        "--pages",
        default="all",
        help="Comma-separated page numbers to process, or 'all'",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=1.0,
        help="Sampling FPS for OCR frame extraction (default: 1.0)",
    )
    parser.add_argument(
        "--hash-threshold",
        type=int,
        default=16,
        help="Minimum dHash distance before OCR is re-run (default: 16)",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.82,
        help="Minimum OCR line confidence to keep (default: 0.82)",
    )
    parser.add_argument(
        "--ocr-workers",
        type=int,
        default=max(1, min(4, (os.cpu_count() or 4) // 2)),
        help="Parallel OCR worker count for selected frames",
    )
    parser.add_argument(
        "--keep-frames",
        action="store_true",
        help="Keep sampled frame images instead of deleting them",
    )
    parser.add_argument(
        "--start-seconds",
        type=float,
        default=0.0,
        help="Optional seek offset in seconds before extraction starts",
    )
    parser.add_argument(
        "--limit-seconds",
        type=float,
        default=0.0,
        help="Optional max seconds to process per page (0 = full page)",
    )
    return parser.parse_args()


def api_headers(referer: str) -> dict[str, str]:
    return {"user-agent": USER_AGENT, "referer": referer}


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120] or "untitled"


def srt_ts(seconds: float) -> str:
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def dhash(image_path: Path, hash_size: int = 8) -> int:
    img = Image.open(image_path).convert("L").resize(
        (hash_size + 1, hash_size), Image.Resampling.LANCZOS
    )
    px = list(img.getdata())
    rows = [px[i * (hash_size + 1) : (i + 1) * (hash_size + 1)] for i in range(hash_size)]
    bits: list[int] = []
    for row in rows:
        for i in range(hash_size):
            bits.append(1 if row[i] > row[i + 1] else 0)
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return value


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def init_ocr() -> None:
    global _OCR
    from rapidocr_onnxruntime import RapidOCR

    _OCR = RapidOCR()


def clean_line(text: str) -> str:
    text = text.replace(" ", "")
    text = re.sub(r"[|]+", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def is_noise_line(text: str) -> bool:
    if len(text) <= 1:
        return True
    if "课程" in text and len(text) <= 4:
        return True
    if any(marker in text for marker in ("课程B站", "课程站", "英字", "黄字", "中英字")):
        return True
    if len(text) < 10 and re.fullmatch(r"[0-9A-Za-z\[\]().,:;_+\-*/=#]+", text):
        return True
    return False


def ocr_frame(frame_path: str, score_threshold: float) -> dict:
    global _OCR
    if _OCR is None:
        init_ocr()
    result, _ = _OCR(frame_path)
    lines: list[tuple[float, str]] = []
    if result:
        for box, text, score in result:
            if score < score_threshold:
                continue
            cleaned = clean_line(text)
            if is_noise_line(cleaned):
                continue
            top = min(point[1] for point in box)
            lines.append((top, cleaned))
    lines.sort(key=lambda item: item[0])
    deduped: list[str] = []
    for _, line in lines:
        if not deduped or similarity(line, deduped[-1]) < 0.95:
            deduped.append(line)
    return {"frame_path": frame_path, "lines": deduped}


def fetch_pages(bvid: str) -> list[PageInfo]:
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    response = requests.get(url, headers=api_headers("https://www.bilibili.com/"), timeout=30)
    response.raise_for_status()
    data = response.json()["data"]
    pages = []
    for page in data["pages"]:
        pages.append(
            PageInfo(
                page=page["page"],
                cid=page["cid"],
                title=page["part"],
                duration=page["duration"],
            )
        )
    return pages


def fetch_playurl(bvid: str, page: PageInfo) -> None:
    referer = f"https://www.bilibili.com/video/{bvid}/?p={page.page}"
    url = (
        "https://api.bilibili.com/x/player/playurl"
        f"?bvid={bvid}&cid={page.cid}&qn=80&fnval=4048&fourk=1"
    )
    response = requests.get(url, headers=api_headers(referer), timeout=30)
    response.raise_for_status()
    dash = response.json()["data"]["dash"]["video"][0]
    page.video_url = dash["baseUrl"]
    page.width = dash["width"]
    page.height = dash["height"]


def select_pages(pages: list[PageInfo], selector: str) -> list[PageInfo]:
    if selector.lower() == "all":
        return pages
    wanted = {int(part.strip()) for part in selector.split(",") if part.strip()}
    return [page for page in pages if page.page in wanted]


def extract_frames(
    bvid: str,
    page: PageInfo,
    fps: float,
    frames_dir: Path,
    start_seconds: float,
    limit_seconds: float,
) -> None:
    if not page.video_url or not page.width or not page.height:
        raise RuntimeError(f"playurl not resolved for page {page.page}")

    x = int(page.width * 0.05)
    w = int(page.width * 0.90)
    y = int(page.height * 0.78)
    h = max(1, page.height - y - 1)
    referer = f"https://www.bilibili.com/video/{bvid}/?p={page.page}"
    pattern = str(frames_dir / "frame_%06d.png")
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-user_agent",
        USER_AGENT,
        "-headers",
        f"Referer: {referer}\r\n",
    ]
    if start_seconds > 0:
        cmd.extend(["-ss", str(start_seconds)])
    cmd.extend(
        [
        "-i",
        page.video_url,
        ]
    )
    if limit_seconds > 0:
        cmd.extend(["-t", str(limit_seconds)])
    cmd.extend(
        [
        "-vf",
        f"fps={fps},crop={w}:{h}:{x}:{y}",
        "-vsync",
        "vfr",
        pattern,
        ]
    )
    subprocess.run(cmd, check=True)


def choose_frame_candidates(frames: Iterable[Path], hash_threshold: int) -> list[tuple[Path, float]]:
    selected: list[tuple[Path, float]] = []
    prev_hash: int | None = None
    for frame_path in frames:
        current_hash = dhash(frame_path)
        if prev_hash is None or (current_hash ^ prev_hash).bit_count() >= hash_threshold:
            match = re.search(r"frame_(\d+)\.png$", frame_path.name)
            if not match:
                continue
            frame_index = int(match.group(1))
            timestamp = float(frame_index - 1)
            selected.append((frame_path, timestamp))
            prev_hash = current_hash
    return selected


def build_cues(
    ocr_rows: list[tuple[float, list[str]]],
    duration: float,
) -> list[dict]:
    cues: list[dict] = []
    current: dict | None = None
    for timestamp, lines in sorted(ocr_rows, key=lambda item: item[0]):
        if not lines:
            continue
        text = "\n".join(lines)
        if current is None:
            current = {"start": timestamp, "end": min(duration, timestamp + 1), "text": text}
            continue
        if similarity(current["text"].replace("\n", ""), text.replace("\n", "")) >= 0.88:
            current["end"] = min(duration, timestamp + 1)
            if len(text) > len(current["text"]):
                current["text"] = text
            continue
        current["end"] = min(duration, max(current["end"], timestamp))
        cues.append(current)
        current = {"start": timestamp, "end": min(duration, timestamp + 1), "text": text}
    if current is not None:
        current["end"] = max(current["end"], duration)
        cues.append(current)
    cleaned: list[dict] = []
    for cue in cues:
        text = cue["text"].strip()
        if not text:
            continue
        if cleaned and similarity(cleaned[-1]["text"].replace("\n", ""), text.replace("\n", "")) >= 0.92:
            cleaned[-1]["end"] = cue["end"]
            if len(text) > len(cleaned[-1]["text"]):
                cleaned[-1]["text"] = text
            continue
        cleaned.append(cue)
    return cleaned


def write_outputs(page: PageInfo, page_dir: Path, cues: list[dict]) -> dict:
    txt_path = page_dir / "subtitles.txt"
    srt_path = page_dir / "subtitles.srt"
    json_path = page_dir / "subtitles.json"

    with txt_path.open("w", encoding="utf-8") as handle:
        for idx, cue in enumerate(cues, 1):
            if idx > 1:
                handle.write("\n\n")
            handle.write(cue["text"])

    with srt_path.open("w", encoding="utf-8") as handle:
        for idx, cue in enumerate(cues, 1):
            handle.write(f"{idx}\n")
            handle.write(f"{srt_ts(cue['start'])} --> {srt_ts(cue['end'])}\n")
            handle.write(f"{cue['text']}\n\n")

    payload = {
        "page": page.page,
        "cid": page.cid,
        "title": page.title,
        "duration_seconds": page.duration,
        "cues": cues,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "page": page.page,
        "cid": page.cid,
        "title": page.title,
        "duration_seconds": page.duration,
        "cue_count": len(cues),
        "txt": str(txt_path),
        "srt": str(srt_path),
        "json": str(json_path),
    }


def process_page(
    bvid: str,
    page: PageInfo,
    out_root: Path,
    fps: float,
    hash_threshold: int,
    score_threshold: float,
    ocr_workers: int,
    keep_frames: bool,
    start_seconds: float,
    limit_seconds: float,
) -> dict:
    fetch_playurl(bvid, page)
    page_dir = out_root / f"P{page.page:02d}_{sanitize_filename(page.title)}"
    page_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = page_dir / "_frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    extract_frames(bvid, page, fps, frames_dir, start_seconds, limit_seconds)
    frame_files = sorted(frames_dir.glob("frame_*.png"))
    candidates = choose_frame_candidates(frame_files, hash_threshold=hash_threshold)

    ocr_rows: list[tuple[float, list[str]]] = []
    if candidates:
        with ProcessPoolExecutor(max_workers=max(1, ocr_workers), initializer=init_ocr) as pool:
            future_rows = list(
                pool.map(
                    ocr_frame,
                    (str(frame_path) for frame_path, _ in candidates),
                    (score_threshold for _ in candidates),
                )
            )
        for (frame_path, timestamp), row in zip(candidates, future_rows):
            ocr_rows.append((timestamp + start_seconds, row["lines"]))

    duration = (
        min(float(page.duration), start_seconds + limit_seconds)
        if limit_seconds > 0
        else float(page.duration)
    )
    cues = build_cues(ocr_rows, duration=duration)
    result = write_outputs(page, page_dir, cues)
    result["sampled_frames"] = len(frame_files)
    result["ocr_frames"] = len(candidates)

    if not keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)

    return result


def main() -> int:
    args = parse_args()
    out_root = Path(args.output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    pages = fetch_pages(args.bvid)
    selected_pages = select_pages(pages, args.pages)
    if not selected_pages:
        raise SystemExit("No matching pages selected")

    manifest = {
        "bvid": args.bvid,
        "fps": args.fps,
        "hash_threshold": args.hash_threshold,
        "score_threshold": args.score_threshold,
        "pages": [],
    }
    all_txt_parts: list[str] = []
    for page in selected_pages:
        print(f"[page {page.page}] extracting {page.title}", flush=True)
        page_result = process_page(
            args.bvid,
            page,
            out_root=out_root,
            fps=args.fps,
            hash_threshold=args.hash_threshold,
            score_threshold=args.score_threshold,
            ocr_workers=args.ocr_workers,
            keep_frames=args.keep_frames,
            start_seconds=args.start_seconds,
            limit_seconds=args.limit_seconds,
        )
        manifest["pages"].append(page_result)
        txt_path = Path(page_result["txt"])
        all_txt_parts.append(f"=== P{page.page:02d} {page.title} ===\n{txt_path.read_text(encoding='utf-8')}")
        print(
            f"[page {page.page}] cues={page_result['cue_count']} "
            f"sampled={page_result['sampled_frames']} ocr={page_result['ocr_frames']}",
            flush=True,
        )

    (out_root / "all_pages.txt").write_text("\n\n".join(all_txt_parts), encoding="utf-8")
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"done -> {out_root}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
