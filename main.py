import subprocess
import json
import re
import os
import uuid
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse

app = FastAPI(title="Insta Reel Downloader", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")
TMP_DIR = "/tmp/insta-dl"
os.makedirs(TMP_DIR, exist_ok=True)

INSTAGRAM_REGEX = re.compile(
    r"(https?://)?(www\.)?instagram\.com/(reel|p|tv)/[\w-]+/?(\?.*)?$"
)


def is_valid_instagram_url(url: str) -> bool:
    return bool(INSTAGRAM_REGEX.match(url))


def base_cmd():
    cmd = [
        "python", "-m", "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
    ]
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
    return cmd


def get_info(url: str) -> dict:
    """Sirf metadata fetch karo — no download"""
    cmd = base_cmd() + ["--dump-json", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout. Dobara try karo.")

    if result.returncode != 0:
        err = result.stderr.strip()
        if "Private" in err or "login" in err.lower():
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
    """
    ffmpeg se video+audio merge karke ek MP4 file download karo.
    Returns: path to merged MP4 file
    """
    out_path = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}.mp4")

    cmd = base_cmd() + [
        # Best video + best audio, ffmpeg se merge
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", out_path,
        url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Download timeout. Dobara try karo.")

    if result.returncode != 0:
        err = result.stderr.strip()
        raise HTTPException(status_code=500, detail=f"Download failed: {err[:300]}")

    if not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="File create nahi hui.")

    return out_path


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Insta Reel Downloader v3 🚀",
        "cookies": "✅ Loaded" if os.path.exists(COOKIES_FILE) else "❌ Not found",
        "endpoints": ["/dl", "/download", "/health"]
    }


@app.get("/dl")
def get_reel_info(url: str = Query(...)):
    """
    Metadata + best single stream URL return karta hai (watch ke liye).
    Note: Ye URL sirf video ya sirf audio ho sakta hai — watch ke liye theek hai.
    Download ke liye /download use karo.
    """
    url = url.split("?")[0].rstrip("/") + "/"

    if not is_valid_instagram_url(url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    data = get_info(url)

    # Best available single-file URL (with audio) prefer karo
    mp4_url = None

    # Pehle check karo koi format hai jisme audio+video dono hain
    formats = data.get("formats", [])
    for fmt in reversed(formats):  # reversed = best quality pehle
        if fmt.get("acodec") != "none" and fmt.get("vcodec") != "none":
            mp4_url = fmt.get("url")
            break

    # Fallback
    if not mp4_url:
        mp4_url = data.get("url")

    return {
        "success": True,
        "title": data.get("title", "Instagram Reel"),
        "uploader": data.get("uploader"),
        "uploader_id": data.get("uploader_id"),
        "thumbnail": data.get("thumbnail"),
        "duration": data.get("duration"),
        "view_count": data.get("view_count"),
        "like_count": data.get("like_count"),
        "mp4_url": mp4_url,
        "note": "Watch ke liye mp4_url use karo. Sound ke saath download ke liye /download endpoint use karo."
    }


@app.get("/download")
def download_with_audio(url: str = Query(...)):
    """
    Video + Audio merge karke complete MP4 file return karta hai.
    ffmpeg use hota hai — thoda slow lekin sound included hoga.
    """
    url = url.split("?")[0].rstrip("/") + "/"

    if not is_valid_instagram_url(url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    # Pehle info lo for filename
    data = get_info(url)
    uploader = data.get("uploader", "reel") or "reel"
    safe_name = re.sub(r'[^\w\-]', '_', uploader)

    # Download + merge
    file_path = download_merged(url)

    def cleanup_after_send():
        try:
            os.remove(file_path)
        except Exception:
            pass

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=f"{safe_name}.mp4",
        background=None,
    )


@app.get("/health")
def health():
    # Check yt-dlp
    try:
        r = subprocess.run(["python", "-m", "yt_dlp", "--version"], capture_output=True, text=True)
        ytdlp = r.stdout.strip()
    except Exception:
        ytdlp = "NOT FOUND ❌"

    # Check ffmpeg
    try:
        r2 = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        ffmpeg = r2.stdout.split("\n")[0] if r2.returncode == 0 else "NOT FOUND ❌"
    except Exception:
        ffmpeg = "NOT FOUND ❌"

    return {
        "status": "ok",
        "yt_dlp": ytdlp,
        "ffmpeg": ffmpeg,
        "cookies": os.path.exists(COOKIES_FILE),
    }
