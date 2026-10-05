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
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta charset="utf-8">
<title>Haqdaar</title>
<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}
body {
  font-family: system-ui, sans-serif;
  background-color: #ffffff;
  color: #000000;
  font-size: 18px;
  line-height: 1.4;
  padding: 12px;
  width: 100%;
  max-width: 480px;
  margin: 0 auto;
}
header {
  text-align: center;
  margin-bottom: 16px;
}
.brand {
  font-size: 26px;
  font-weight: bold;
  color: #000000;
  margin-bottom: 4px;
}
.phone-info {
  font-size: 18px;
  color: #111111;
  font-weight: 500;
  min-height: 24px;
}
.btn-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}
.action-btn {
  display: block;
  width: 100%;
  min-height: 56px;
  padding: 14px 16px;
  border-radius: 8px;
  border: 2px solid #000000;
  background-color: #f2f2f2;
  color: #000000;
  font-size: 18px;
  font-weight: bold;
  cursor: pointer;
  text-align: center;
}
.send-btn {
  background-color: #004488;
  color: #ffffff;
  border: 2px solid #002244;
  margin-top: 12px;
}
.send-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.count-bar {
  display: flex;
  justify-content: space-between;
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 12px;
  color: #111111;
}
.photos-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}
.thumb-box {
  position: relative;
  width: 30%;
  min-width: 80px;
  aspect-ratio: 1;
  border: 2px solid #000000;
  border-radius: 6px;
  overflow: hidden;
  background-color: #f9f9f9;
}
.thumb-box img {
  width: 100%;
  height: 100%;
  max-width: 100%;
  object-fit: cover;
  display: block;
}
.del-btn {
  position: absolute;
  top: 0;
  right: 0;
  width: 44px;
  height: 44px;
  min-width: 44px;
  min-height: 44px;
  background-color: #000000;
  color: #ffffff;
  border: 2px solid #ffffff;
  font-size: 24px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.notice-text {
  font-size: 18px;
  color: #333333;
  text-align: center;
  margin-top: 12px;
  line-height: 1.4;
}
.error-msg {
  color: #990000;
  font-size: 18px;
  font-weight: bold;
  margin-top: 8px;
  text-align: center;
}
.status-box {
  display: none;
  background-color: #f0f0f0;
  border: 2px solid #000000;
  border-radius: 8px;
  padding: 14px;
  text-align: center;
  margin-bottom: 16px;
}
.status-text {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 8px;
  color: #000000;
}
.progress-bar-bg {
  width: 100%;
  height: 12px;
  background-color: #cccccc;
  border: 1px solid #000000;
  border-radius: 6px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background-color: #004488;
  width: 0%;
}
.success-card {
  display: none;
  background-color: #e8f5e9;
  border: 2px solid #2e7d32;
  border-radius: 8px;
  padding: 24px 16px;
  text-align: center;
}
.success-msg {
  font-size: 20px;
  font-weight: bold;
  color: #1b5e20;
  line-height: 1.4;
}
</style>
</head>
<body>
<header>
  <div class="brand">Haqdaar</div>
  <div class="phone-info">__PHONE_HEADER__</div>
</header>

<noscript>
  <div class="error-msg" style="padding:14px;border:2px solid #990000;margin-bottom:14px;">
    This page needs JavaScript to send photos. / फोटो भेजने के लिए जावास्क्रिप्ट चालू करें। / फोटो पाठवण्यासाठी जावास्क्रिप्ट सुरू करा.
  </div>
</noscript>

<main id="main-section">
  <div class="btn-grid" id="controls-grid">
    <button type="button" class="action-btn" id="camera-btn">
      __TAKE_BTN__
    </button>
    <button type="button" class="action-btn" id="gallery-btn">
      __PICK_BTN__
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
  <div class="notice-text">__NOTICE__</div>
</main>

<div class="success-card" id="success-card">
  <div style="font-size:40px;margin-bottom:12px;">✓</div>
  <div class="success-msg">__DONE_MSG__</div>
</div>

<script>
var TOKEN = "__TOKEN__";
var files = [];
var networkErrorMsg = "__NETWORK_ERR__";
var cannotSendMsg = "__CANNOT_SEND_ERR__";

var cameraInput = document.getElementById("camera-input");
var galleryInput = document.getElementById("gallery-input");
var cameraBtn = document.getElementById("camera-btn");
var galleryBtn = document.getElementById("gallery-btn");
var counter = document.getElementById("photo-counter");
var thumbsGrid = document.getElementById("thumbs-grid");
var sendBtn = document.getElementById("send-btn");
var limitWarning = document.getElementById("limit-warning");
var statusBox = document.getElementById("status-box");
var statusText = document.getElementById("status-text");
var progressFill = document.getElementById("progress-fill");
var uploadErr = document.getElementById("upload-err");
var mainSection = document.getElementById("main-section");
var successCard = document.getElementById("success-card");

cameraBtn.onclick = function() {
  cameraInput.click();
};

galleryBtn.onclick = function() {
  galleryInput.click();
};

cameraInput.onchange = function(e) {
  var tFiles = (e && e.target && e.target.files) ? e.target.files : cameraInput.files;
  if (tFiles && tFiles.length > 0) {
    addFile(tFiles[0]);
    cameraInput.value = "";
  }
};

galleryInput.onchange = function(e) {
  var tFiles = (e && e.target && e.target.files) ? e.target.files : galleryInput.files;
  if (tFiles) {
    for (var i = 0; i < tFiles.length; i++) {
      addFile(tFiles[i]);
    }
    galleryInput.value = "";
  }
};

function addFile(file) {
  if (!file) return;
  if (files.length >= 6) {
    limitWarning.style.display = "block";
    return;
  }
  limitWarning.style.display = "none";
  files.push(file);
  renderThumbs();
}

function removeFile(index) {
  files.splice(index, 1);
  limitWarning.style.display = "none";
  renderThumbs();
}

function renderThumbs() {
  counter.textContent = files.length + " / 6";
  sendBtn.disabled = files.length === 0;
  thumbsGrid.innerHTML = "";
  for (var i = 0; i < files.length; i++) {
    (function(idx) {
      var f = files[idx];
      var box = document.createElement("div");
      box.className = "thumb-box";
      var img = document.createElement("img");
      if (window.URL && window.URL.createObjectURL) {
        img.src = window.URL.createObjectURL(f);
      }
      var del = document.createElement("button");
      del.type = "button";
      del.className = "del-btn";
      del.innerHTML = "&times;";
      del.onclick = function(e) {
        if (e && e.stopPropagation) e.stopPropagation();
        removeFile(idx);
      };
      box.appendChild(img);
      box.appendChild(del);
      thumbsGrid.appendChild(box);
    })(i);
  }
}

function dataURLToBlob(dataURL) {
  var parts = dataURL.split(",");
  var byteString = atob(parts[1]);
  var mimeMatch = parts[0].match(/:(.*?);/);
  var mime = mimeMatch ? mimeMatch[1] : "image/jpeg";
  var ab = new ArrayBuffer(byteString.length);
  var ia = new Uint8Array(ab);
  for (var i = 0; i < byteString.length; i++) {
    ia[i] = byteString.charCodeAt(i);
  }
  return new Blob([ab], {type: mime});
}

function resizePhoto(file, callback) {
  if (!window.Image || !document.createElement("canvas")) {
    if (file.size <= 5 * 1024 * 1024) {
      callback(file, true);
    } else {
      callback(null, false);
    }
    return;
  }
  var img = new Image();
  var url = "";
  if (window.URL && window.URL.createObjectURL) {
    url = window.URL.createObjectURL(file);
  }
  img.onload = function() {
    if (url && window.URL && window.URL.revokeObjectURL) {
      window.URL.revokeObjectURL(url);
    }
    var w = img.width;
    var h = img.height;
    var maxSide = 1024;
    if (w > maxSide || h > maxSide) {
      if (w > h) {
        h = Math.round((h * maxSide) / w);
        w = maxSide;
      } else {
        w = Math.round((w * maxSide) / h);
        h = maxSide;
      }
    }
    var canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    var ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, w, h);
    if (canvas.toBlob) {
      canvas.toBlob(function(b) {
        if (b) {
          callback(b, true);
        } else {
          try {
            var dUrl = canvas.toDataURL("image/jpeg", 0.7);
            callback(dataURLToBlob(dUrl), true);
          } catch(err) {
            if (file.size <= 5 * 1024 * 1024) {
              callback(file, true);
            } else {
              callback(null, false);
            }
          }
        }
      }, "image/jpeg", 0.7);
    } else if (canvas.toDataURL) {
      try {
        var dUrl2 = canvas.toDataURL("image/jpeg", 0.7);
        callback(dataURLToBlob(dUrl2), true);
      } catch(err2) {
        if (file.size <= 5 * 1024 * 1024) {
          callback(file, true);
        } else {
          callback(null, false);
        }
      }
    } else {
      if (file.size <= 5 * 1024 * 1024) {
        callback(file, true);
      } else {
        callback(null, false);
      }
    }
  };
  img.onerror = function() {
    if (url && window.URL && window.URL.revokeObjectURL) {
      window.URL.revokeObjectURL(url);
    }
    if (file.size <= 5 * 1024 * 1024) {
      callback(file, true);
    } else {
      callback(null, false);
    }
  };
  if (url) {
    img.src = url;
  } else {
    var reader = new FileReader();
    reader.onload = function(evt) {
      img.src = evt.target.result;
    };
    reader.onerror = function() {
      if (file.size <= 5 * 1024 * 1024) {
        callback(file, true);
      } else {
        callback(null, false);
      }
    };
    reader.readAsDataURL(file);
  }
}

function sendOnePhoto(blob, callback) {
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/p/" + TOKEN + "/photo", true);
  xhr.setRequestHeader("Content-Type", "image/jpeg");
  xhr.onreadystatechange = function() {
    if (xhr.readyState === 4) {
      if (xhr.status >= 200 && xhr.status < 300) {
        callback(true);
      } else {
        callback(false);
      }
    }
  };
  xhr.onerror = function() {
    callback(false);
  };
  xhr.send(blob);
}

function sendWithRetry(blob, doneCb) {
  sendOnePhoto(blob, function(ok) {
    if (ok) {
      doneCb(true);
    } else {
      sendOnePhoto(blob, function(ok2) {
        doneCb(ok2);
      });
    }
  });
}

sendBtn.onclick = function() {
  if (files.length === 0) return;
  sendBtn.disabled = true;
  cameraBtn.disabled = true;
  galleryBtn.disabled = true;
  statusBox.style.display = "block";
  uploadErr.style.display = "none";

  var total = files.length;
  var sent = 0;
  var remainingFiles = [];

  function processIndex(i) {
    if (i >= total) {
      if (remainingFiles.length === 0) {
        var doneXhr = new XMLHttpRequest();
        doneXhr.open("POST", "/p/" + TOKEN + "/done", true);
        doneXhr.onreadystatechange = function() {
          if (doneXhr.readyState === 4) {
            mainSection.style.display = "none";
            successCard.style.display = "block";
          }
        };
        doneXhr.onerror = function() {
          mainSection.style.display = "none";
          successCard.style.display = "block";
        };
        doneXhr.send();
      } else {
        files = remainingFiles;
        renderThumbs();
        sendBtn.disabled = false;
        cameraBtn.disabled = false;
        galleryBtn.disabled = false;
        uploadErr.textContent = networkErrorMsg;
        uploadErr.style.display = "block";
      }
      return;
    }

    statusText.textContent = sent + " of " + total + " sent";
    progressFill.style.width = Math.round((sent / total) * 100) + "%";

    resizePhoto(files[i], function(blob, canSend) {
      if (!canSend || !blob) {
        uploadErr.textContent = cannotSendMsg;
        uploadErr.style.display = "block";
        remainingFiles.push(files[i]);
        processIndex(i + 1);
        return;
      }
      sendWithRetry(blob, function(ok) {
        if (ok) {
          sent++;
          statusText.textContent = sent + " of " + total + " sent";
          progressFill.style.width = Math.round((sent / total) * 100) + "%";
        } else {
          remainingFiles.push(files[i]);
        }
        processIndex(i + 1);
      });
    });
  }

  processIndex(0);
};
</script>
</body>
</html>"""


# Note: Gujarati and Tamil labels have not been checked by a native speaker.
PHRASES = {
    "take": {
        "hi": "फोटो खींचें",
        "mr": "फोटो काढा",
        "en": "Take a photo",
        "gu": "ફોટો લો",
        "ta": "புகைப்படம் எடு",
    },
    "pick": {
        "hi": "फोटो चुनें",
        "mr": "फोटो निवडा",
        "en": "Pick photos",
        "gu": "ફોટો પસંદ કરો",
        "ta": "புகைப்படங்களைத் தேர்ந்தெடு",
    },
    "send": {
        "hi": "भेजें",
        "mr": "पाठवा",
        "en": "Send",
        "gu": "મોકલો",
        "ta": "அனுப்பு",
    },
    "done_msg": {
        "hi": "भेज दिया, आपको कॉल आएगा",
        "mr": "पाठवले, तुम्हाला कॉल येईल",
        "en": "sent, you will get a call",
        "gu": "મોકલાઈ ગયું, તમને કૉલ આવશે",
        "ta": "அனுப்பப்பட்டது, உங்களுக்கு அழைப்பு வரும்",
    },
    "limit_err": {
        "hi": "अधिकतम 6 फोटो भेज सकते हैं",
        "mr": "जास्तीत जास्त 6 फोटो पाठवू शकता",
        "en": "six photos at most",
        "gu": "વધુમાં વધુ 6 ફોટા",
        "ta": "அதிகபட்சம் 6 புகைப்படங்கள்",
    },
    "for_phone": {
        "hi": "फोन नंबर के लिए ...{tail}",
        "mr": "फोन नंबरसाठी ...{tail}",
        "en": "for the phone ending {tail}",
        "gu": "ફોન નંબર માટે ...{tail}",
        "ta": "தொலைபேசி எண்ணிற்கு ...{tail}",
    },
}

NOTICE_PHRASES = {
    "en": "The photos are read by a computer and by a helper.",
    "hi": "फोटो कंप्यूटर और एक सहायक देखेंगे।",
    "mr": "फोटो संगणक आणि एक मदतनीस पाहतील।",
    "gu": "ફોટો કમ્પ્યુટર અને એક સહાયક જોશે.",
    "ta": "புகைப்படங்களை ஒரு கணினியும் ஒரு உதவியாளரும் பார்ப்பார்கள்.",
}

NETWORK_ERR = "no network, press send again / नेटवर्क नहीं है, फिर से भेजें दबाएँ / नेटवर्क नाही, पुन्हा पाठवा दाबा"
CANNOT_SEND_ERR = "this photo can not be sent / यह फोटो नहीं भेजी जा सकती / हा फोटो पाठवता येत नाही"


def _render_photo_page(case: cases.Case) -> str:
    lang = case.lang
    if lang == "gu":
        langs = ["gu", "hi", "en"]
    elif lang == "ta":
        langs = ["ta", "hi", "en"]
    elif lang == "mr":
        langs = ["mr", "hi", "en"]
    elif lang == "en":
        langs = ["en", "hi", "mr"]
    else:
        langs = ["hi", "mr", "en"]

    tail = cases.number_tail(case)
    if tail:
        phone_parts = [PHRASES["for_phone"][l].format(tail=tail) for l in langs]
        phone_header = " / ".join(phone_parts)
    else:
        phone_header = ""

    take_btn = " / ".join(PHRASES["take"][l] for l in langs)
    pick_btn = " / ".join(PHRASES["pick"][l] for l in langs)
    send_btn = " / ".join(PHRASES["send"][l] for l in langs)
    done_msg = " / ".join(PHRASES["done_msg"][l] for l in langs)
    limit_err = " / ".join(PHRASES["limit_err"][l] for l in langs)

    if lang in ("gu", "ta"):
        notice = " / ".join([NOTICE_PHRASES[lang], NOTICE_PHRASES["hi"], NOTICE_PHRASES["en"]])
    else:
        notice = " / ".join([NOTICE_PHRASES[l] for l in langs])

    html_out = PHOTO_HTML_TEMPLATE
    html_out = html_out.replace("__LANG__", html.escape(case.lang))
    html_out = html_out.replace("__PHONE_HEADER__", html.escape(phone_header))
    html_out = html_out.replace("__TAKE_BTN__", html.escape(take_btn))
    html_out = html_out.replace("__PICK_BTN__", html.escape(pick_btn))
    html_out = html_out.replace("__SEND_BTN__", html.escape(send_btn))
    html_out = html_out.replace("__DONE_MSG__", html.escape(done_msg))
    html_out = html_out.replace("__LIMIT_ERR__", html.escape(limit_err))
    html_out = html_out.replace("__NOTICE__", html.escape(notice))
    html_out = html_out.replace("__NETWORK_ERR__", html.escape(NETWORK_ERR))
    html_out = html_out.replace("__CANNOT_SEND_ERR__", html.escape(CANNOT_SEND_ERR))
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
<meta name="viewport" content="width=device-width, initial-scale=1">
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
