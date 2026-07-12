# 📥 Insta Reel Downloader API

FastAPI + yt-dlp based Instagram Reel downloader — Render pe deploy karo free mein.

---

## 🚀 Deploy on Render

### Step 1 — GitHub Repo banao
- Ye saari files ek GitHub repo mein daalo
- Repo name: `insta-reel-dl` (ya kuch bhi)

### Step 2 — Render pe Web Service banao
1. [render.com](https://render.com) pe jao → **New → Web Service**
2. GitHub repo connect karo
3. Settings:
   - **Build Command:** `chmod +x build.sh && ./build.sh`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment:** Python 3
   - **Plan:** Free
4. **Deploy** karo ✅

---

## 🍪 Cookies Setup (Optional but Recommended)

Cookies se reliability bahut badhti hai.

### Cookies kaise export karein:
1. Chrome mein install karo: **"Get cookies.txt LOCALLY"** extension
2. `instagram.com` pe **apne account se login** karo
3. Extension icon → **Export** → `cookies.txt` download hoga
4. Downloaded file se **`cookies.txt` replace** karo (project root mein)
5. GitHub pe **commit + push** karo → Render auto redeploy karega

### Cookies kitne din kaam karti hain:
- Normal use: **60–90 din**
- Heavy use / suspicious activity: jaldi expire ho sakti hain
- Renew karna easy hai — same steps repeat karo

---

## 📡 API Endpoints

### `GET /dl?url=<instagram_url>`
Reel ka MP4 URL return karta hai.

**Example:**
```
GET https://your-app.onrender.com/dl?url=https://www.instagram.com/reel/ABC123/
```

**Response:**
```json
{
  "success": true,
  "title": "Reel title",
  "uploader": "username",
  "uploader_id": "@username",
  "thumbnail": "https://...",
  "duration": 30,
  "view_count": 12345,
  "like_count": 500,
  "mp4_url": "https://instagram.cdn.../video.mp4",
  "note": "MP4 URL temporary hai — 30 min mein expire ho sakta hai."
}
```

### `GET /cookies-status`
Check karo ki cookies load hain ya nahi.

### `GET /health`
yt-dlp version aur status check.

### `GET /`
Basic status check.

---

## ⚠️ Important Notes

- MP4 URL **~30 min mein expire** ho jata hai — user ko turant download karna chahiye
- Free Render instance **15 min inactivity** ke baad sleep karta hai — pehli request slow hogi
- Agar `403 error` aaye → cookies expire ho gayi hain, renew karo
- Agar `429 error` aaye → Instagram ne rate limit kiya, thodi der baad try karo
