import subprocess
import json
import re
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Insta Reel Downloader", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Cookies file path — upload this file to your project root on Render
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")

INSTAGRAM_REGEX = re.compile(
    r"(https?://)?(www\.)?instagram\.com/(reel|p|tv)/[\w-]+/?(\?.*)?$"
)


def is_valid_instagram_url(url: str) -> bool:
    return bool(INSTAGRAM_REGEX.match(url))


def run_ytdlp(url: str) -> dict:
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        "--no-warnings",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
    ]

    # Add cookies if file exists
    if os.path.exists(COOKIES_FILE):
        cmd += ["--cookies", COOKIES_FILE]
        print(f"[yt-dlp] Using cookies from {COOKIES_FILE}")
    else:
        print("[yt-dlp] No cookies.txt found — running without login")

    cmd.append(url)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout ho gaya. Dobara try karo.")

    if result.returncode != 0:
        err = result.stderr.strip()
        print(f"[yt-dlp ERROR] {err}")

        if "Private" in err or "Login" in err or "login" in err:
            raise HTTPException(status_code=403, detail="Yeh reel private hai ya cookies expire ho gayi hain.")
        if "not found" in err.lower() or "404" in err:
            raise HTTPException(status_code=404, detail="Reel nahi mili. URL dobara check karo.")
        if "rate" in err.lower() or "429" in err:
            raise HTTPException(status_code=429, detail="Instagram ne rate limit kar diya. Thodi der baad try karo.")

        raise HTTPException(status_code=500, detail=f"yt-dlp error: {err[:300]}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Response parse nahi hua.")

    return data


@app.get("/")
def root():
    cookies_status = "✅ Loaded" if os.path.exists(COOKIES_FILE) else "❌ Not found (running without login)"
    return {
        "status": "ok",
        "message": "Insta Reel Downloader is running 🚀",
        "cookies": cookies_status,
    }


@app.get("/dl")
def download_reel(url: str = Query(..., description="Instagram Reel/Post URL")):
    # Clean URL — remove query params
    url = url.split("?")[0].rstrip("/") + "/"

    if not is_valid_instagram_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL. Instagram reel/post URL do. Example: https://www.instagram.com/reel/ABC123/"
        )

    data = run_ytdlp(url)

    # Extract best MP4 URL
    mp4_url = None

    if "requested_formats" in data:
        for fmt in data["requested_formats"]:
            if fmt.get("url"):
                mp4_url = fmt["url"]
                break

    if not mp4_url:
        mp4_url = data.get("url")

    if not mp4_url:
        raise HTTPException(status_code=500, detail="MP4 URL nahi mila.")

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
        "note": "MP4 URL temporary hai — 30 min mein expire ho sakta hai."
    }


@app.get("/cookies-status")
def cookies_status():
    exists = os.path.exists(COOKIES_FILE)
    size = os.path.getsize(COOKIES_FILE) if exists else 0
    return {
        "cookies_loaded": exists,
        "file_size_bytes": size,
        "path": COOKIES_FILE,
        "tip": "Agar False hai to cookies.txt project root mein daalo aur redeploy karo."
    }


@app.get("/health")
def health():
    try:
        result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
        version = result.stdout.strip()
    except FileNotFoundError:
        version = "NOT INSTALLED ❌"

    return {
        "status": "ok",
        "yt_dlp_version": version,
        "cookies_file": os.path.exists(COOKIES_FILE),
    }
