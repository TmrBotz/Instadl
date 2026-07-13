import subprocess
import json
import re
import os
import uuid
import asyncio
from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Insta Reel Downloader", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")
TMP_DIR      = "/tmp/insta-dl"
HOME_BIN     = os.path.join(os.path.expanduser("~"), "bin")
FFMPEG_PATH  = os.path.join(HOME_BIN, "ffmpeg")
FILE_TTL     = 10 * 60  # 10 minutes baad auto-delete

os.makedirs(TMP_DIR, exist_ok=True)

# /files/* se merged MP4 serve hogi
app.mount("/files", StaticFiles(directory=TMP_DIR), name="files")

INSTAGRAM_REGEX = re.compile(
    r"(https?://)?(www\.)?instagram\.com/(reel|p|tv)/[\w\-]+/?(\?.*)?$"
)


def is_valid_instagram_url(url: str) -> bool:
    return bool(INSTAGRAM_REGEX.match(url))


def base_cmd() -> list:
    cmd = [
        "python", "-m", "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
    ]
    if os.path.exists(FFMPEG_PATH):
        cmd += ["--ffmpeg-location", FFMPEG_PATH]
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
    return cmd


def get_info(url: str) -> dict:
    """Reel ka metadata fetch karo (title, thumbnail, etc.)"""
    cmd = base_cmd() + ["--dump-json", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout. Dobara try karo.")

    if result.returncode != 0:
        err = result.stderr.strip()
        if "private" in err.lower() or "login" in err.lower():
            raise HTTPException(status_code=403, detail="Private reel ya cookies expire ho gayi.")
        if "404" in err or "not found" in err.lower():
            raise HTTPException(status_code=404, detail="Reel nahi mili.")
        if "429" in err or "rate" in err.lower():
            raise HTTPException(status_code=429, detail="Rate limited. Thodi der baad try karo.")
        raise HTTPException(status_code=500, detail=f"yt-dlp error: {err[:300]}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Response parse nahi hua.")


def download_and_merge(url: str, out_path: str):
    """
    yt-dlp + ffmpeg se best video + best audio download karke
    ek single MP4 mein merge karo. Yahi wajah hai sound aata hai.
    """
    cmd = base_cmd() + [
        # Best video (mp4) + Best audio (m4a) lo, ffmpeg merge karega
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", out_path,
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Download timeout.")

    if result.returncode != 0:
        err = result.stderr.strip()
        raise HTTPException(status_code=500, detail=f"Download failed: {err[:300]}")

    if not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="File create nahi hui.")


async def delete_after(path: str, delay: int = FILE_TTL):
    """delay seconds baad file auto-delete karo"""
    await asyncio.sleep(delay)
    try:
        os.remove(path)
    except Exception:
        pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status":   "ok",
        "version":  "4.0.0",
        "ffmpeg":   os.path.exists(FFMPEG_PATH),
        "cookies":  os.path.exists(COOKIES_FILE),
        "endpoint": "/dl?url=<instagram_url>",
    }


@app.get("/dl")
def get_reel(
    url: str = Query(..., description="Instagram reel/post/tv URL"),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
):
    # 1. URL clean karo
    url = url.split("?")[0].rstrip("/") + "/"
    if not is_valid_instagram_url(url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    # 2. Metadata fetch karo (title, thumbnail, etc.)
    data = get_info(url)

    # 3. Audio+Video merge karke download karo ← yahi fix hai
    filename = f"{uuid.uuid4().hex}.mp4"
    out_path = os.path.join(TMP_DIR, filename)
    download_and_merge(url, out_path)

    # 4. FILE_TTL seconds baad auto-delete schedule karo
    background_tasks.add_task(delete_after, out_path, FILE_TTL)

    # 5. Is server ka public URL banao
    base_url = str(request.base_url).rstrip("/")
    mp4_url  = f"{base_url}/files/{filename}"

    return {
        "success":    True,
        "mp4_url":    mp4_url,          # ← yeh URL sound ke saath hogi
        "expires_in": f"{FILE_TTL // 60} minutes",
        "title":      data.get("title", "Instagram Reel"),
        "uploader":   data.get("uploader"),
        "thumbnail":  data.get("thumbnail"),
        "duration":   data.get("duration"),
        "view_count": data.get("view_count"),
        "like_count": data.get("like_count"),
    }


@app.get("/health")
def health():
    try:
        v = subprocess.run(["python", "-m", "yt_dlp", "--version"], capture_output=True, text=True)
        ytdlp = v.stdout.strip()
    except Exception:
        ytdlp = "NOT FOUND ❌"

    ffmpeg_ok = os.path.exists(FFMPEG_PATH)
    if ffmpeg_ok:
        try:
            fv = subprocess.run([FFMPEG_PATH, "-version"], capture_output=True, text=True)
            ffmpeg = fv.stdout.split("\n")[0]
        except Exception:
            ffmpeg = "Error running ffmpeg"
    else:
        ffmpeg = f"NOT FOUND at {FFMPEG_PATH} ❌"

    return {
        "status":  "ok",
        "yt_dlp":  ytdlp,
        "ffmpeg":  ffmpeg,
        "cookies": os.path.exists(COOKIES_FILE),
    }
