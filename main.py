import subprocess
import json
import re
import os
import uuid
import asyncio
from fastapi import FastAPI, HTTPException, Query, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Insta Reel Downloader", version="4.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")
TMP_DIR      = "/tmp/insta-dl"
FILE_TTL     = 10 * 60

os.makedirs(TMP_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=TMP_DIR), name="files")

INSTAGRAM_REGEX = re.compile(
    r"(https?://)?(www\.)?instagram\.com/(reel|p|tv)/[\w\-]+/?(\?.*)?$"
)


def find_ffmpeg() -> tuple[str | None, str | None]:
    """ffmpeg aur ffprobe ka path dhundho — multiple locations check karo"""
    home_bin = os.path.join(os.path.expanduser("~"), "bin")
    candidates = [
        os.path.join(home_bin, "ffmpeg"),   # build.sh wala (primary)
        "/usr/bin/ffmpeg",                   # system install
        "/usr/local/bin/ffmpeg",             # homebrew / manual install
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            ffprobe = path.replace("ffmpeg", "ffprobe")
            return path, (ffprobe if os.path.isfile(ffprobe) else None)

    # PATH mein bhi check karo
    try:
        r = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            path = r.stdout.strip()
            ffprobe = path.replace("ffmpeg", "ffprobe")
            return path, (ffprobe if os.path.isfile(ffprobe) else None)
    except Exception:
        pass

    return None, None


def is_valid_instagram_url(url: str) -> bool:
    return bool(INSTAGRAM_REGEX.match(url))


def base_cmd() -> list:
    ffmpeg, ffprobe = find_ffmpeg()
    cmd = [
        "python", "-m", "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "--add-header", "Accept-Language:en-US,en;q=0.9",
    ]
    if ffmpeg:
        cmd += ["--ffmpeg-location", ffmpeg]
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


def download_merged(url: str, out_path: str):
    """
    bestvideo+bestaudio — koi extension restriction NAHI.
    Instagram ka audio m4a nahi hota, isliye [ext=m4a] silently fail
    karta tha aur video-only 'best' pe fall ho jata tha.
    ffmpeg audio ko aac mein re-encode karta hai taaki sab players mein chale.
    """
    ffmpeg, _ = find_ffmpeg()
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="ffmpeg nahi mila. /health check karo.")

    cmd = base_cmd() + [
        "-f", "bestvideo+bestaudio/best",          # ← FIX: no [ext=] restriction
        "--merge-output-format", "mp4",
        "--postprocessor-args",
        "ffmpeg:-c:v copy -c:a aac -b:a 128k",    # ← FIX: audio aac mein re-encode
        "-o", out_path,
        url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Download timeout.")

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Download failed: {result.stderr.strip()[:300]}")

    if not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="File create nahi hui.")

    # ffprobe se verify karo ke audio stream hai ya nahi
    _, ffprobe = find_ffmpeg()
    if ffprobe:
        probe = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_streams", out_path],
            capture_output=True, text=True, timeout=10,
        )
        try:
            streams = json.loads(probe.stdout).get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            if not has_audio:
                raise HTTPException(status_code=500, detail="Merge ke baad bhi audio stream nahi mila.")
        except json.JSONDecodeError:
            pass  # ffprobe output parse nahi hua, continue karo


async def delete_after(path: str, delay: int = FILE_TTL):
    await asyncio.sleep(delay)
    try:
        os.remove(path)
    except Exception:
        pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    ffmpeg, _ = find_ffmpeg()
    return {
        "status": "ok",
        "version": "4.1.0",
        "ffmpeg": ffmpeg or "NOT FOUND ❌",
        "cookies": os.path.exists(COOKIES_FILE),
        "endpoints": ["/dl", "/health"],
    }


@app.get("/dl")
def get_reel_info(
    url: str = Query(...),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
):
    url = url.split("?")[0].rstrip("/") + "/"
    if not is_valid_instagram_url(url):
        raise HTTPException(status_code=400, detail="Invalid Instagram URL.")

    data = get_info(url)

    filename = f"{uuid.uuid4().hex}.mp4"
    out_path = os.path.join(TMP_DIR, filename)
    download_merged(url, out_path)

    background_tasks.add_task(delete_after, out_path, FILE_TTL)

    base_url = str(request.base_url).rstrip("/")
    mp4_url  = f"{base_url}/files/{filename}"

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


@app.get("/health")
def health():
    try:
        v = subprocess.run(["python", "-m", "yt_dlp", "--version"], capture_output=True, text=True)
        ytdlp = v.stdout.strip()
    except Exception:
        ytdlp = "NOT FOUND ❌"

    ffmpeg, ffprobe = find_ffmpeg()
    if ffmpeg:
        try:
            fv = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True)
            ffmpeg_ver = fv.stdout.split("\n")[0]
        except Exception:
            ffmpeg_ver = "Error running ffmpeg"
    else:
        ffmpeg_ver = "NOT FOUND ❌"

    return {
        "status":   "ok",
        "yt_dlp":   ytdlp,
        "ffmpeg":   ffmpeg_ver,
        "ffprobe":  ffprobe or "NOT FOUND ❌",
        "cookies":  os.path.exists(COOKIES_FILE),
        "tmp_dir":  os.path.exists(TMP_DIR),
    }
