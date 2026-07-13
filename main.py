import subprocess
import json
import re
import os
import uuid
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks

app = FastAPI(title="Insta Reel Downloader", version="3.1.0")

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

os.makedirs(TMP_DIR, exist_ok=True)

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
    # ffmpeg path explicitly set karo
    if os.path.exists(FFMPEG_PATH):
        cmd += ["--ffmpeg-location", FFMPEG_PATH]
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
    return cmd


def get_info(url: str) -> dict:
    cmd = base_cmd() + ["--dump-json", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout. Dobara try karo.")

    if result.returncode != 0:
        err = result.stderr.strip()
        if "private" in err.lower() or "login" in err.lower():
            raise HTTPException(status_code=403, detail="Private reel ya cookies expire.")
        if "404" in err or "not found" in err.lower():
            raise HTTPException(status_code=404, detail="Reel nahi mili.")
        if "429" in err or "rate" in err.lower():
            raise HTTPException(status_code=429, detail="Rate limited. Thodi der baad try karo.")
        raise HTTPException(status_code=500, detail=f"yt-dlp: {err[:300]}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Response parse nahi hua.")


def download_merged(url: str) -> str:
    out_path = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.mp4")
    cmd = base_cmd() + [
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

    return out_path


def cleanup(path: str):
    try:
        os.remove(path)
    except Exception:
        pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status": "ok",
        "version": "3.1.0",
        "ffmpeg": os.path.exists(FFMPEG_PATH),
        "cookies": os.path.exists(COOKIES_FILE),
        "endpoints": ["/dl", "/download", "/health"],
    }


@app.get("/dl")
def get_reel_info(url: str = Query(...)):
    url = url.split("?")[0].rstrip("/") + "/"
    if not is_valid_instagram_url(url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    data = get_info(url)

    # Audio+video dono wala format prefer karo
    mp4_url = None
    for fmt in reversed(data.get("formats", [])):
        if fmt.get("acodec") != "none" and fmt.get("vcodec") != "none":
            mp4_url = fmt.get("url")
            break
    if not mp4_url:
        mp4_url = data.get("url")

    return {
        "success":     True,
        "title":       data.get("title", "Instagram Reel"),
        "uploader":    data.get("uploader"),
        "uploader_id": data.get("uploader_id"),
        "thumbnail":   data.get("thumbnail"),
        "duration":    data.get("duration"),
        "view_count":  data.get("view_count"),
        "like_count":  data.get("like_count"),
        "mp4_url":     mp4_url,
    }


@app.get("/download")
def download_with_audio(url: str = Query(...), background_tasks: BackgroundTasks = None):
    url = url.split("?")[0].rstrip("/") + "/"
    if not is_valid_instagram_url(url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    data     = get_info(url)
    uploader = re.sub(r'[^\w\-]', '_', data.get("uploader", "reel") or "reel")
    path     = download_merged(url)

    background_tasks.add_task(cleanup, path)

    return FileResponse(
        path=path,
        media_type="video/mp4",
        filename=f"{uploader}.mp4",
    )


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
        "status":   "ok",
        "yt_dlp":   ytdlp,
        "ffmpeg":   ffmpeg,
        "cookies":  os.path.exists(COOKIES_FILE),
    }
