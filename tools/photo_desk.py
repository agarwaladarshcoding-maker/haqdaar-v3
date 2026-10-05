"""tools/photo_desk.py

 starts two FastAPI apps:
- photo app on 0.0.0.0:PHOTO_PORT (default 8002): public photo upload page & endpoints.
- desk app on 127.0.0.1:DESK_PORT (default 8003): laptop-only helper dashboard.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from haqdaar.photo import cases, reader

PHOTO_PORT = int(os.getenv("PHOTO_PORT", "8002"))
DESK_PORT = int(os.getenv("DESK_PORT", "8003"))

# --- Rate limiting state for photo app ---
_wrong_token_attempts: dict[str, list[float]] = {}
_blocked_until: dict[str, float] = {}
_rate_lock = threading.Lock()

# --- Cached scheme searcher ---
_SCHEME_CACHE: Any = None


def _get_scheme_searcher() -> Any:
    global _SCHEME_CACHE
    if _SCHEME_CACHE is None:
        from haqdaar.data import corpus, scheme_index
        from haqdaar.data.scheme_text import SchemeText

        c = corpus.Corpus.load("CURRENT")
        idx = scheme_index.get(c.snapshot_id)
        st = SchemeText.load(c.snapshot_id)
        _SCHEME_CACHE = (idx, st)
    return _SCHEME_CACHE


def pick_scheme(search: str) -> tuple[str, str]:
    search = (search or "").strip()
    if not search:
        return ("", "")
    try:
        idx, st = _get_scheme_searcher()
        hits = idx.search(search, 1)
        if not hits:
            return ("", "")
        sid = str(hits[0].scheme_id)
        card_text = st.card(sid, "en")
        lines = [l.strip() for l in card_text.split("\n") if l.strip()]
        name = lines[1] if len(lines) > 1 else sid
        name = name.removeprefix("name: ").strip()
        return (sid, name)
    except Exception:
        return ("", "")


def call_back(case: cases.Case) -> None:
    folder = os.getenv("PHOTO_DIR", "data_cache/photo")
    base = Path(folder)
    base.mkdir(parents=True, exist_ok=True)
    target = base / "next_call.json"
    payload = {
        "token": case.token,
        "lang": case.lang,
        "say": case.say,
        "made": case.made,
    }
    cases._write_json_atomic(target, payload)


def _log_state(token: str, state: str) -> None:
    t3 = (token or "")[:3]
    t_str = time.strftime("%H:%M:%S")
    print(f"[{t_str}] token:{t3}*** state:{state}", flush=True)


def _record_bad_attempt(client_ip: str) -> None:
    now = time.time()
    with _rate_lock:
        recent = [t for t in _wrong_token_attempts.get(client_ip, []) if now - t <= 60.0]
        recent.append(now)
        _wrong_token_attempts[client_ip] = recent
        if len(recent) >= 10:
            _blocked_until[client_ip] = now + 60.0


def _is_rate_limited(client_ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        blocked_end = _blocked_until.get(client_ip, 0.0)
        return now < blocked_end


def _process_done(token: str) -> None:
    case = cases.get(token)
    if not case or not case.photos:
        return

    photo_list: list[bytes] = []
    for i in range(len(case.photos)):
        try:
            data, _ = cases.photo_bytes(token, i)
            photo_list.append(data)
        except Exception:
            pass

    finding = reader.read(photo_list, lang=case.lang)
    search_term = finding.get("search", "")
    scheme_id, scheme_name = pick_scheme(search_term)

    by = finding.get("by", "")
    if by == "stand-in" or by.startswith("stand-in"):
        say = "We got your photos. A helper will look at them."
    else:
        shows = finding.get("shows", "").strip()
        wrong = finding.get("wrong", "").strip()
        parts = ["We looked at your photos."]
        if shows:
            parts.append(shows if shows.endswith((".", "!", "?", "।", "\n")) else shows + ".")
        if wrong:
            parts.append(wrong if wrong.endswith((".", "!", "?", "।", "\n")) else wrong + ".")
        if scheme_name:
            parts.append(f"A scheme that may help is {scheme_name}.")
        parts.append("You can ask me about it now.")
        say = " ".join(parts)

    cases.set_finding(token, finding, scheme_id, say)
    _log_state(token, "read")


# ==============================================================================
# 1. PHOTO APP (port 8002, 0.0.0.0)
# ==============================================================================
photo_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@photo_app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if _is_rate_limited(client_ip):
        return Response(content="Too many attempts. Try again later.", status_code=429, media_type="text/plain")
    return await call_next(request)


PHOTO_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Haqdaar - Photo Upload</title>
<style>
:root {
  --bg: #0f172a;
  --card: #1e293b;
  --text: #f8fafc;
  --text-dim: #94a3b8;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --border: #334155;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg);
  color: var(--text);
  line-height: 1.5;
  padding: 16px;
  max-width: 480px;
  margin: 0 auto;
}
header { text-align: center; margin-bottom: 20px; }
.brand { font-size: 24px; font-weight: 700; color: #38bdf8; margin-bottom: 4px; }
.phone-info { font-size: 15px; color: var(--text-dim); font-weight: 500; min-height: 22px; }
.btn-grid { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 54px;
  padding: 12px 18px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  font-size: 17px;
  font-weight: 600;
  cursor: pointer;
  touch-action: manipulation;
}
.action-btn:active { background: #2d3748; }
.send-btn {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  min-height: 56px;
  font-size: 19px;
  width: 100%;
}
.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.count-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-dim);
}
.photos-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}
.thumb-box {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
  background: var(--card);
  border: 1px solid var(--border);
}
.thumb-box img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.del-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  border: 1px solid rgba(255,255,255,0.3);
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.status-box {
  display: none;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
  margin-bottom: 16px;
}
.status-text { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.progress-bar-bg {
  width: 100%;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--primary);
  width: 0%;
  transition: width 0.3s;
}
.error-msg {
  color: #f87171;
  font-size: 14px;
  margin-top: 6px;
  text-align: center;
}
.success-card {
  display: none;
  background: #064e3b;
  border: 1px solid #059669;
  border-radius: 12px;
  padding: 24px 16px;
  text-align: center;
}
.success-msg {
  font-size: 20px;
  font-weight: 700;
  color: #ecfdf5;
  line-height: 1.4;
}
</style>
</head>
<body>
<header>
  <div class="brand">Haqdaar</div>
  <div class="phone-info">__PHONE_HEADER__</div>
</header>

<main id="main-section">
  <div class="btn-grid" id="controls-grid">
    <button type="button" class="action-btn" id="camera-btn">
      <span>📷</span>
      <span>__TAKE_BTN__</span>
    </button>
    <button type="button" class="action-btn" id="gallery-btn">
      <span>🖼️</span>
      <span>__PICK_BTN__</span>
    </button>
  </div>

  <input type="file" id="camera-input" accept="image/*" capture="environment" style="display:none">
  <input type="file" id="gallery-input" accept="image/*" multiple style="display:none">

  <div class="count-bar">
    <span>Photos</span>
    <span id="photo-counter">0 / 6</span>
  </div>

  <div class="photos-container" id="thumbs-grid"></div>
  <div class="error-msg" id="limit-warning" style="display:none;">__LIMIT_ERR__</div>

  <div class="status-box" id="status-box">
    <div class="status-text" id="status-text">Sending...</div>
    <div class="progress-bar-bg">
      <div class="progress-bar-fill" id="progress-fill"></div>
    </div>
    <div class="error-msg" id="upload-err" style="display:none;"></div>
  </div>

  <button type="button" class="action-btn send-btn" id="send-btn" disabled>
    __SEND_BTN__
  </button>
</main>

<div class="success-card" id="success-card">
  <div style="font-size:40px;margin-bottom:12px;">✓</div>
  <div class="success-msg">__DONE_MSG__</div>
</div>

<script>
const TOKEN = "__TOKEN__";
let files = [];

const cameraInput = document.getElementById('camera-input');
const galleryInput = document.getElementById('gallery-input');
const cameraBtn = document.getElementById('camera-btn');
const galleryBtn = document.getElementById('gallery-btn');
const counter = document.getElementById('photo-counter');
const thumbsGrid = document.getElementById('thumbs-grid');
const sendBtn = document.getElementById('send-btn');
const limitWarning = document.getElementById('limit-warning');
const statusBox = document.getElementById('status-box');
const statusText = document.getElementById('status-text');
const progressFill = document.getElementById('progress-fill');
const uploadErr = document.getElementById('upload-err');
const mainSection = document.getElementById('main-section');
const successCard = document.getElementById('success-card');

cameraBtn.addEventListener('click', () => cameraInput.click());
galleryBtn.addEventListener('click', () => galleryInput.click());

cameraInput.addEventListener('change', (e) => {
  if (e.target.files && e.target.files.length > 0) {
    addFile(e.target.files[0]);
    e.target.value = '';
  }
});

galleryInput.addEventListener('change', (e) => {
  if (e.target.files) {
    for (let i = 0; i < e.target.files.length; i++) {
      addFile(e.target.files[i]);
    }
    e.target.value = '';
  }
});

function addFile(file) {
  if (!file) return;
  if (files.length >= 6) {
    limitWarning.style.display = 'block';
    return;
  }
  limitWarning.style.display = 'none';
  files.push(file);
  renderThumbs();
}

function removeFile(index) {
  files.splice(index, 1);
  limitWarning.style.display = 'none';
  renderThumbs();
}

function renderThumbs() {
  counter.textContent = files.length + ' / 6';
  sendBtn.disabled = files.length === 0;
  thumbsGrid.innerHTML = '';
  files.forEach((f, idx) => {
    const box = document.createElement('div');
    box.className = 'thumb-box';
    const img = document.createElement('img');
    img.src = URL.createObjectURL(f);
    const del = document.createElement('button');
    del.className = 'del-btn';
    del.innerHTML = '&times;';
    del.onclick = (e) => {
      e.stopPropagation();
      removeFile(idx);
    };
    box.appendChild(img);
    box.appendChild(del);
    thumbsGrid.appendChild(box);
  });
}

function resizePhoto(file) {
  return new Promise((resolve) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      let w = img.width, h = img.height;
      const maxSide = 1024;
      if (w > maxSide || h > maxSide) {
        if (w > h) {
          h = Math.round((h * maxSide) / w);
          w = maxSide;
        } else {
          w = Math.round((w * maxSide) / h);
          h = maxSide;
        }
      }
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, w, h);
      canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.7);
    };
    img.onerror = () => resolve(file);
    img.src = url;
  });
}

async function sendOnePhoto(blob) {
  try {
    const r = await fetch('/p/' + TOKEN + '/photo', {
      method: 'POST',
      headers: { 'Content-Type': 'image/jpeg' },
      body: blob
    });
    if (r.ok) return true;
  } catch(e) {}
  try {
    const r2 = await fetch('/p/' + TOKEN + '/photo', {
      method: 'POST',
      headers: { 'Content-Type': 'image/jpeg' },
      body: blob
    });
    return r2.ok;
  } catch(e) {
    return false;
  }
}

sendBtn.addEventListener('click', async () => {
  if (files.length === 0) return;

  sendBtn.disabled = true;
  cameraBtn.disabled = true;
  galleryBtn.disabled = true;
  statusBox.style.display = 'block';
  uploadErr.style.display = 'none';

  const total = files.length;
  let sent = 0;
  const remainingFiles = [];

  for (let i = 0; i < files.length; i++) {
    statusText.textContent = sent + ' of ' + total + ' sent';
    progressFill.style.width = Math.round((sent / total) * 100) + '%';

    const blob = await resizePhoto(files[i]);
    const ok = await sendOnePhoto(blob);
    if (ok) {
      sent++;
      statusText.textContent = sent + ' of ' + total + ' sent';
      progressFill.style.width = Math.round((sent / total) * 100) + '%';
    } else {
      remainingFiles.push(files[i]);
    }
  }

  if (remainingFiles.length === 0) {
    try {
      await fetch('/p/' + TOKEN + '/done', { method: 'POST' });
    } catch(e) {}
    mainSection.style.display = 'none';
    successCard.style.display = 'block';
  } else {
    files = remainingFiles;
    renderThumbs();
    sendBtn.disabled = false;
    cameraBtn.disabled = false;
    galleryBtn.disabled = false;
    uploadErr.textContent = sent + ' of ' + total + ' sent. Some failed to send.';
    uploadErr.style.display = 'block';
  }
});
</script>
</body>
</html>"""


def _render_photo_page(case: cases.Case) -> str:
    lang = case.lang
    if lang == "mr":
        langs = ["mr", "hi", "en"]
    elif lang == "en":
        langs = ["en", "hi", "mr"]
    else:
        langs = ["hi", "mr", "en"]

    phrases = {
        "take": {"hi": "फोटो खींचें", "mr": "फोटो काढा", "en": "Take a photo"},
        "pick": {"hi": "फोटो चुनें", "mr": "फोटो निवडा", "en": "Pick photos"},
        "send": {"hi": "भेजें", "mr": "पाठवा", "en": "Send"},
        "done_msg": {"hi": "भेज दिया, आपको कॉल आएगा", "mr": "पाठवले, तुम्हाला कॉल येईल", "en": "sent, you will get a call"},
        "limit_err": {"hi": "अधिकतम 6 फोटो भेज सकते हैं", "mr": "जास्तीत जास्त 6 फोटो पाठवू शकता", "en": "six photos at most"},
        "for_phone": {"hi": "फोन नंबर के लिए ...{tail}", "mr": "फोन नंबरसाठी ...{tail}", "en": "for the phone ending {tail}"},
    }

    tail = cases.number_tail(case)
    if tail:
        phone_parts = [phrases["for_phone"][l].format(tail=tail) for l in langs]
        phone_header = " / ".join(phone_parts)
    else:
        phone_header = ""

    take_btn = " / ".join(phrases["take"][l] for l in langs)
    pick_btn = " / ".join(phrases["pick"][l] for l in langs)
    send_btn = " / ".join(phrases["send"][l] for l in langs)
    done_msg = " / ".join(phrases["done_msg"][l] for l in langs)
    limit_err = " / ".join(phrases["limit_err"][l] for l in langs)

    html_out = PHOTO_HTML_TEMPLATE
    html_out = html_out.replace("__LANG__", html.escape(case.lang))
    html_out = html_out.replace("__PHONE_HEADER__", html.escape(phone_header))
    html_out = html_out.replace("__TAKE_BTN__", html.escape(take_btn))
    html_out = html_out.replace("__PICK_BTN__", html.escape(pick_btn))
    html_out = html_out.replace("__SEND_BTN__", html.escape(send_btn))
    html_out = html_out.replace("__DONE_MSG__", html.escape(done_msg))
    html_out = html_out.replace("__LIMIT_ERR__", html.escape(limit_err))
    html_out = html_out.replace("__TOKEN__", html.escape(case.token))
    return html_out


@photo_app.get("/p/{token}")
async def get_photo_page(token: str, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not token or not cases.TOKEN_RE.match(token):
        _record_bad_attempt(client_ip)
        err_page = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Not Found</title></head><body style='font-family:sans-serif;padding:2rem;text-align:center;'><h2>this link is no longer good / यह लिंक अब काम नहीं करता / ही लिंक आता चालत नाही</h2></body></html>"
        return HTMLResponse(content=err_page, status_code=404, headers={"Cache-Control": "no-store"})

    case = cases.get(token)
    if case is None:
        _record_bad_attempt(client_ip)
        err_page = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Not Found</title></head><body style='font-family:sans-serif;padding:2rem;text-align:center;'><h2>this link is no longer good / यह लिंक अब काम नहीं करता / ही लिंक आता चालत नाही</h2></body></html>"
        return HTMLResponse(content=err_page, status_code=404, headers={"Cache-Control": "no-store"})

    _log_state(token, case.state)
    page_html = _render_photo_page(case)
    return HTMLResponse(content=page_html, status_code=200, headers={"Cache-Control": "no-store"})


@photo_app.post("/p/{token}/photo")
async def post_photo(token: str, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not token or not cases.TOKEN_RE.match(token):
        _record_bad_attempt(client_ip)
        return JSONResponse(status_code=404, content={"ok": False, "why": "case not found"})

    case = cases.get(token)
    if case is None:
        _record_bad_attempt(client_ip)
        return JSONResponse(status_code=404, content={"ok": False, "why": "case not found"})

    body = bytearray()
    max_len = cases.MAX_BYTES
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_len:
            return JSONResponse(status_code=413, content={"ok": False, "why": "the photo is too big"})

    raw_bytes = bytes(body)
    try:
        updated = cases.add_photo(token, raw_bytes)
        _log_state(token, updated.state)
        return JSONResponse(status_code=200, content={"ok": True, "n": len(updated.photos)})
    except ValueError as e:
        err = str(e)
        if "too big" in err:
            return JSONResponse(status_code=413, content={"ok": False, "why": err})
        elif "case not found" in err:
            _record_bad_attempt(client_ip)
            return JSONResponse(status_code=404, content={"ok": False, "why": err})
        else:
            return JSONResponse(status_code=400, content={"ok": False, "why": err})


@photo_app.post("/p/{token}/done")
async def post_done(token: str, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not token or not cases.TOKEN_RE.match(token):
        _record_bad_attempt(client_ip)
        return JSONResponse(status_code=404, content={"ok": False, "why": "case not found"})

    case = cases.get(token)
    if case is None:
        _record_bad_attempt(client_ip)
        return JSONResponse(status_code=404, content={"ok": False, "why": "case not found"})

    if case.state in ("read", "approved", "called") or not case.photos:
        return JSONResponse(status_code=200, content={"ok": True})

    _process_done(token)
    return JSONResponse(status_code=200, content={"ok": True})


# ==============================================================================
# 2. DESK APP (port 8003, 127.0.0.1 only)
# ==============================================================================
desk_app = FastAPI()


def _format_age(made_ts: float) -> str:
    diff = max(0.0, time.time() - made_ts)
    if diff < 60:
        return f"{int(diff)}s ago"
    mins = int(diff // 60)
    if mins < 60:
        return f"{mins}m ago"
    hours = int(mins // 60)
    return f"{hours}h ago"


DESK_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Haqdaar Photo Desk</title>
<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background: #f1f5f9;
  color: #1e293b;
  margin: 0;
  padding: 24px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  background: #fff;
  padding: 16px 20px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
h1 { margin: 0; font-size: 22px; }
.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #fff;
  cursor: pointer;
  font-weight: 600;
  font-size: 14px;
}
.btn:hover { background: #f8fafc; }
.btn-new { background: #2563eb; color: #fff; border-color: #2563eb; }
.btn-new:hover { background: #1d4ed8; }
.btn-save { background: #e2e8f0; }
.btn-call { background: #16a34a; color: #fff; border-color: #16a34a; }
.btn-call:hover { background: #15803d; }
.case-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.case-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  margin-right: 8px;
}
.state-waiting { background: #fef3c7; color: #b45309; }
.state-photo { background: #e0e7ff; color: #4338ca; }
.state-read { background: #dbeafe; color: #1d4ed8; }
.state-approved { background: #dcfce7; color: #15803d; }
.state-called { background: #f1f5f9; color: #64748b; }
.case-number { font-weight: 600; }
.case-age { color: #64748b; font-size: 13px; }
.case-link { color: #2563eb; text-decoration: none; font-size: 13px; }
.case-link:hover { text-decoration: underline; }
.photos-row {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.desk-thumb {
  height: 90px;
  width: 90px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
}
.stand-in-box {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
}
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  font-size: 14px;
  margin-bottom: 12px;
}
.say-box { margin-bottom: 12px; }
.say-box textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  font-family: inherit;
  font-size: 14px;
  margin-top: 4px;
}
.action-row { display: flex; gap: 10px; }
.dim { color: #94a3b8; }
</style>
</head>
<body>
<div class="top-bar">
  <h1>Photo Desk (Helper)</h1>
  <button type="button" onclick="createTestCase()" class="btn btn-new">+ New Test Case</button>
</div>

<div id="cases-container">
  __BODY_CARDS__
</div>

<script>
async function createTestCase() {
  try {
    const res = await fetch('/new', { method: 'POST' });
    const d = await res.json();
    if (d.ok) {
      window.open(d.link, '_blank');
      setTimeout(() => location.reload(), 500);
    }
  } catch(e) {
    alert('Failed to create test case: ' + e);
  }
}

async function saveText(token) {
  const txt = document.getElementById('say-' + token).value;
  try {
    const res = await fetch('/save/' + token, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: txt
    });
    if (res.ok) {
      alert('Saved text for ' + token);
      location.reload();
    } else {
      const d = await res.json().catch(() => ({}));
      alert('Could not save: ' + (d.detail || res.statusText));
    }
  } catch(e) {
    alert('Error saving text: ' + e);
  }
}

async function callBack(token) {
  const txt = document.getElementById('say-' + token).value;
  try {
    const res = await fetch('/approve/' + token, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: txt
    });
    if (res.ok) {
      alert('Approved and queued call back for ' + token);
      location.reload();
    } else {
      const d = await res.json().catch(() => ({}));
      alert('Could not approve: ' + (d.detail || res.statusText));
    }
  } catch(e) {
    alert('Error approving call back: ' + e);
  }
}

setInterval(() => {
  const active = document.activeElement;
  if (active && active.tagName === 'TEXTAREA') {
    return;
  }
  location.reload();
}, 5000);
</script>
</body>
</html>"""


@desk_app.get("/", response_class=HTMLResponse)
async def get_desk_home():
    open_list = cases.open_cases()

    cases_html_parts: list[str] = []
    for c in open_list:
        tail = cases.number_tail(c)
        number_label = f"number: ...{html.escape(tail)}" if tail else "number: none (Mac call)"
        case_link = cases.link(c)
        age_str = _format_age(c.made)

        photos_html = ""
        for idx in range(len(c.photos)):
            p_tok = html.escape(c.token)
            photos_html += f'<a href="/photo/{p_tok}/{idx}" target="_blank"><img src="/photo/{p_tok}/{idx}" alt="Photo {idx + 1}" class="desk-thumb"></a> '

        by = c.finding.get("by", "")
        stand_in_banner = ""
        if by == "stand-in" or "stand-in" in by:
            stand_in_banner = '<div class="stand-in-box">no reader set, write the answer yourself</div>'

        shows = html.escape(str(c.finding.get("shows", "")))
        wrong = html.escape(str(c.finding.get("wrong", "")))
        sure = html.escape(str(c.finding.get("sure", 0.0)))
        by_esc = html.escape(str(by))
        scheme_esc = html.escape(str(c.scheme))
        say_esc = html.escape(str(c.say))
        c_tok = html.escape(c.token)
        c_state = html.escape(c.state)
        c_link = html.escape(case_link)

        card_html = f"""
        <div class="case-card" id="card-{c_tok}">
          <div class="case-header">
            <div>
              <span class="badge state-{c_state}">{c_state}</span>
              <span class="case-number">{number_label}</span>
              <span class="case-age">({age_str})</span>
            </div>
            <div>
              <a href="{c_link}" target="_blank" class="case-link">{c_link}</a>
            </div>
          </div>

          <div class="photos-row">
            {photos_html if photos_html else '<span class="dim">No photos uploaded yet</span>'}
          </div>

          {stand_in_banner}

          <div class="meta-grid">
            <div><strong>Shows:</strong> {shows or '<span class="dim">-</span>'}</div>
            <div><strong>Wrong:</strong> {wrong or '<span class="dim">-</span>'}</div>
            <div><strong>Sure:</strong> {sure} | <strong>By:</strong> {by_esc or '<span class="dim">-</span>'}</div>
            <div><strong>Scheme:</strong> {scheme_esc or '<span class="dim">None</span>'}</div>
          </div>

          <div class="say-box">
            <label for="say-{c_tok}"><strong>Call-back Say:</strong></label>
            <textarea id="say-{c_tok}" rows="2">{say_esc}</textarea>
          </div>

          <div class="action-row">
            <button type="button" onclick="saveText('{c_tok}')" class="btn btn-save">Save text</button>
            <button type="button" onclick="callBack('{c_tok}')" class="btn btn-call">Call back</button>
          </div>
        </div>
        """
        cases_html_parts.append(card_html)

    body_cards = "\n".join(cases_html_parts) if cases_html_parts else "<div class='dim' style='padding:20px;'>No open cases</div>"

    html_content = DESK_HTML_TEMPLATE.replace("__BODY_CARDS__", body_cards)
    return HTMLResponse(content=html_content, status_code=200)


@desk_app.get("/photo/{token}/{n}")
async def get_desk_photo(token: str, n: int):
    if not token or not cases.TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        data, mime = cases.photo_bytes(token, n)
        return Response(content=data, media_type=mime)
    except (ValueError, IndexError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="Photo not found")


@desk_app.post("/approve/{token}")
async def post_desk_approve(token: str, request: Request):
    if not token or not cases.TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="Case not found")
    body_text = (await request.body()).decode("utf-8")
    try:
        case = cases.approve(token, body_text)
        call_back(case)
        _log_state(token, case.state)
        return JSONResponse(status_code=200, content={"ok": True, "state": case.state})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@desk_app.post("/save/{token}")
async def post_desk_save(token: str, request: Request):
    if not token or not cases.TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="Case not found")
    body_text = (await request.body()).decode("utf-8")
    try:
        case = cases.approve(token, body_text)
        _log_state(token, case.state)
        return JSONResponse(status_code=200, content={"ok": True, "state": case.state})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@desk_app.post("/new")
async def post_desk_new():
    case = cases.new_case("hi")
    _log_state(case.token, case.state)
    return JSONResponse(
        status_code=200,
        content={"ok": True, "token": case.token, "link": cases.link(case)},
    )


# ==============================================================================
# 3. SERVER ENTRYPOINT
# ==============================================================================
def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    photo_port = int(os.getenv("PHOTO_PORT", "8002"))
    desk_port = int(os.getenv("DESK_PORT", "8003"))
    local_ip = _local_ip()

    print(f"Photo app: http://0.0.0.0:{photo_port} (local: http://{local_ip}:{photo_port})")
    print(f"Desk app:  http://127.0.0.1:{desk_port}")

    desk_thread = threading.Thread(
        target=uvicorn.run,
        args=(desk_app,),
        kwargs={"host": "127.0.0.1", "port": desk_port, "log_level": "warning", "access_log": False},
        daemon=True,
    )
    desk_thread.start()

    uvicorn.run(photo_app, host="0.0.0.0", port=photo_port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
