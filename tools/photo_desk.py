"""tools/photo_desk.py

Starts two FastAPI apps:
- photo app on 0.0.0.0:PHOTO_PORT (default 8002): public photo upload page & endpoints.
- desk app on 127.0.0.1:DESK_PORT (default 8003): laptop-only helper dashboard (Pass 4 keyboard-driven).
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

from haqdaar.contracts import tunables
from haqdaar.keypad_sms.reassembler import SMSReassemblyManager, parse_sms_packet
from haqdaar.photo import cases, reader

PHOTO_PORT = int(os.getenv("PHOTO_PORT", "8002"))
DESK_PORT = int(os.getenv("DESK_PORT", "8003"))

# --- Photo auto mode (Pass 4) ---
_PHOTO_AUTO_RUNTIME: bool = os.getenv("PHOTO_AUTO", "true").lower() in ("true", "1", "yes", "on")


def _is_photo_auto() -> bool:
    env_val = os.getenv("PHOTO_AUTO")
    if env_val is not None:
        return env_val.strip().lower() in ("true", "1", "yes", "on")
    return _PHOTO_AUTO_RUNTIME


# --- Background sweep loop ---
def _start_sweep_loop():
    try:
        cases.sweep()
    except Exception:
        pass

    def _loop():
        while True:
            time.sleep(600)
            try:
                cases.sweep()
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


_start_sweep_loop()

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


SCHEME_HELP_TEMPLATES = {
    "hi": "एक योजना जो मदद कर सकती है वह है {scheme_name}।",
    "mr": "मदत करू शकणारी एक योजना म्हणजे {scheme_name}.",
    "gu": "એક યોજના જે મદદ કરી શકે છે તે છે {scheme_name}.",
    "ta": "உதவக்கூடிய ஒரு திட்டம் {scheme_name}.",
    "en": "A scheme that may help is {scheme_name}.",
}

STAND_IN_SAY = {
    "hi": "फोटो मिल गए हैं। सहायक इन्हें देखेंगे।",
    "mr": "फोटो मिळाले आहेत. मदतनीस ते पाहतील.",
    "gu": "ફોટા મળ્યા છે. સહાયક તેને જોશે.",
    "ta": "புகைப்படங்கள் வந்துள்ளன. உதவியாளர் பார்ப்பார்.",
    "en": "Photos arrived. A helper will look at them.",
}


def _process_done(token: str) -> None:
    try:
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

        lang = case.lang
        finding = reader.read(photo_list, lang=lang)
        search_term = finding.get("search", "")
        scheme_id, scheme_name = pick_scheme(search_term)

        by = str(finding.get("by", ""))
        if by.startswith("stand-in"):
            say = STAND_IN_SAY.get(lang, STAND_IN_SAY["en"])
        else:
            shows = str(finding.get("shows", "")).strip()
            wrong = str(finding.get("wrong", "")).strip()
            parts = []
            if shows:
                s = shows
                if not s.endswith((".", "!", "?", "।")):
                    s += "।" if lang in ("hi", "mr") else "."
                parts.append(s)
            if wrong:
                w = wrong
                if not w.endswith((".", "!", "?", "।")):
                    w += "।" if lang in ("hi", "mr") else "."
                parts.append(w)
            if scheme_name:
                tpl = SCHEME_HELP_TEMPLATES.get(lang, SCHEME_HELP_TEMPLATES["en"])
                parts.append(tpl.format(scheme_name=scheme_name))

            say = " ".join(parts).strip()
            if not say:
                say = STAND_IN_SAY.get(lang, STAND_IN_SAY["en"])

        cases.set_finding(token, finding, scheme_id, say)
        _log_state(token, "read")

        if _is_photo_auto():
            c_approved = cases.approve(token, say)
            call_back(c_approved)
            _log_state(token, "approved")
    except Exception:
        pass


# ==============================================================================
# 1. PHOTO APP (port 8002, 0.0.0.0)
# ==============================================================================
photo_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

STEPS_PHRASES = {
    "step1": {
        "hi": "1. फोटो खींचें या चुनें",
        "mr": "1. फोटो काढा किंवा निवडा",
        "en": "1. Take or pick photos",
        "gu": "1. ફોટો લો અથવા પસંદ કરો",
        "ta": "1. புகைப்படம் எடுக்கவும் அல்லது தேர்ந்தெடுக்கவும்",
    },
    "step2": {
        "hi": "2. फोटो देखें",
        "mr": "2. फोटो पहा",
        "en": "2. Look at them",
        "gu": "2. ફોટો જુઓ",
        "ta": "2. புகைப்படங்களைப் பார்க்கவும்",
    },
    "step3": {
        "hi": "3. भेजें दबाएँ",
        "mr": "3. पाठवा दाबा",
        "en": "3. Press send",
        "gu": "3. મોકલો દબાવો",
        "ta": "3. அனுப்பு அழுத்தவும்",
    },
}

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
    "photos": {
        "hi": "फोटो",
        "mr": "फोटो",
        "en": "Photos",
        "gu": "ફોટા",
        "ta": "புகைப்படங்கள்",
    },
    "send": {
        "hi": "भेजें",
        "mr": "पाठवा",
        "en": "Send",
        "gu": "મોકલો",
        "ta": "அனுப்பு",
    },
    "done_msg": {
        "hi": "भेज दिया, हम आपको कॉल करेंगे",
        "mr": "पाठवले, आम्ही तुम्हाला कॉल करू",
        "en": "sent, we will call you back",
        "gu": "મોકલાઈ ગયું, અમે તમને કૉલ કરીશું",
        "ta": "அனுப்பப்பட்டது, நாங்கள் உங்களுக்கு மீண்டும் அழைப்போம்",
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
    "not_sent": {
        "hi": "नहीं भेजा गया, फिर से दबाएँ",
        "mr": "पाठवले नाही, पुन्हा दाबा",
        "en": "not sent, press again",
        "gu": "મોકલાયું નથી, ફરીથી દબાવો",
        "ta": "அனுப்பப்படவில்லை, மீண்டும் அழுத்தவும்",
    },
    "network_err": {
        "hi": "नेटवर्क नहीं है, फिर से भेजें दबाएँ",
        "mr": "नेटवर्क नाही, पुन्हा पाठवा दाबा",
        "en": "no network, press send again",
        "gu": "નેટવર્ક નથી, ફરીથી મોકલો દબાવો",
        "ta": "நெட்வொர்க் இல்லை, மீண்டும் அனுப்பு அழுத்தவும்",
    },
    "cannot_send": {
        "hi": "यह फोटो नहीं भेजी जा सकती",
        "mr": "हा फोटो पाठवता येत नाही",
        "en": "this photo can not be sent",
        "gu": "આ ફોટો મોકલી શકાતો નથી",
        "ta": "இந்த புகைப்படத்தை அனுப்ப முடியாது",
    },
}

NOTICE_PHRASES = {
    "en": "The photos are read by a computer and by a helper.",
    "hi": "फोटो कंप्यूटर और एक सहायक देखेंगे।",
    "mr": "फोटो संगणक आणि एक मदतनीस पाहतील।",
    "gu": "ફોટો કમ્પ્યુટર અને એક સહાયક જોશે.",
    "ta": "புகைப்படங்களை ஒரு கணினியும் ஒரு உதவியாளரும் பார்ப்பார்கள்.",
}

PHOTO_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta charset="utf-8">
<title>Haqdaar</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
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
header { text-align: center; margin-bottom: 12px; }
.brand { font-size: 26px; font-weight: bold; margin-bottom: 4px; }
.phone-info { font-size: 18px; color: #111; font-weight: 500; min-height: 24px; }
.steps-box {
  background: #f8f9fa;
  border: 2px solid #000000;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}
.btn-grid { display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px; }
.action-btn {
  display: block;
  width: 100%;
  min-height: 56px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 2px solid #000000;
  background-color: #f2f2f2;
  color: #000000;
  cursor: pointer;
  text-align: center;
}
.send-btn {
  background-color: #004488;
  color: #ffffff;
  border: 2px solid #002244;
  margin-top: 12px;
}
.send-btn:disabled { opacity: 0.5; cursor: default; }
.count-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 12px;
}
.photos-container { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
.thumb-box {
  position: relative;
  width: 96px;
  height: 96px;
  min-width: 96px;
  min-height: 96px;
  border: 2px solid #000000;
  border-radius: 6px;
  overflow: hidden;
  background-color: #f9f9f9;
}
.thumb-box img {
  width: 96px;
  height: 96px;
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
.notice-text { font-size: 16px; color: #333333; text-align: center; margin-top: 12px; line-height: 1.4; }
.error-msg { color: #990000; font-size: 16px; font-weight: bold; margin-top: 8px; text-align: center; }
.status-box {
  display: none;
  background-color: #f0f0f0;
  border: 2px solid #000000;
  border-radius: 8px;
  padding: 14px;
  text-align: center;
  margin-bottom: 16px;
}
.status-text { font-size: 18px; font-weight: bold; margin-bottom: 8px; }
.progress-bar-bg {
  width: 100%;
  height: 12px;
  background-color: #cccccc;
  border: 1px solid #000000;
  border-radius: 6px;
  overflow: hidden;
}
.progress-bar-fill { height: 100%; background-color: #004488; width: 0%; }
.success-card {
  display: none;
  background-color: #e8f5e9;
  border: 2px solid #2e7d32;
  border-radius: 8px;
  padding: 24px 16px;
  text-align: center;
}
.success-msg { font-size: 20px; font-weight: bold; color: #1b5e20; line-height: 1.4; }
.lp { font-size: 19px; font-weight: bold; line-height: 1.2; }
.ls { font-size: 15px; opacity: 0.9; line-height: 1.2; margin-top: 2px; }
.stp-row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.stp-ic { font-size: 19px; line-height: 1.2; font-weight: bold; }
.stp-p { font-size: 17px; font-weight: bold; line-height: 1.2; }
.stp-s { font-size: 14px; color: #333; line-height: 1.2; margin-top: 1px; }
</style>
</head>
<body>
<header>
  <div class="brand">Haqdaar</div>
  <div class="phone-info">__PHONE_HEADER__</div>
</header>

<noscript>
  <div class="error-msg" style="padding:14px;border:2px solid #990000;margin-bottom:14px;">
    This page needs JavaScript to send photos. / फोटो भेजने के लिए जावास्क्रिप्ट चालू करें।
  </div>
</noscript>

<main id="main-section">
  __STEPS_HTML__

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
    <div>__PHOTOS_LABEL__</div>
    <div id="photo-counter" style="font-size:20px;">0 / 6</div>
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
var notSentMsg = "__NOT_SENT_ERR__";

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
        try {
          img.src = window.URL.createObjectURL(f);
        } catch(e) {}
      } else if (typeof FileReader !== "undefined") {
        try {
          var fr = new FileReader();
          fr.onload = function(evt) { img.src = evt.target.result; };
          fr.readAsDataURL(f);
        } catch(e) {}
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
  var hasURL = window.URL && window.URL.createObjectURL;
  var hasFR = typeof FileReader !== "undefined";
  if (!hasURL && !hasFR) {
    if (file.size <= 5 * 1024 * 1024) {
      callback(file, true);
    } else {
      callback(null, false);
    }
    return;
  }

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
  if (hasURL) {
    try {
      url = window.URL.createObjectURL(file);
    } catch(e) {
      url = "";
    }
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
    if (!ctx) {
      if (file.size <= 5 * 1024 * 1024) {
        callback(file, true);
      } else {
        callback(null, false);
      }
      return;
    }
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
    try {
      var readerObj = new FileReader();
      readerObj.onload = function(evt) {
        img.src = evt.target.result;
      };
      readerObj.onerror = function() {
        if (file.size <= 5 * 1024 * 1024) {
          callback(file, true);
        } else {
          callback(null, false);
        }
      };
      readerObj.readAsDataURL(file);
    } catch(e) {
      if (file.size <= 5 * 1024 * 1024) {
        callback(file, true);
      } else {
        callback(null, false);
      }
    }
  }
}

function sendOnePhoto(blob, callback) {
  var xhr = new XMLHttpRequest();
  var called = false;
  function handleDone(ok) {
    if (!called) {
      called = true;
      callback(ok);
    }
  }
  xhr.open("POST", "/p/" + TOKEN + "/photo", true);
  xhr.setRequestHeader("Content-Type", "image/jpeg");
  xhr.onreadystatechange = function() {
    if (xhr.readyState === 4) {
      if (xhr.status >= 200 && xhr.status < 300) {
        handleDone(true);
      } else {
        handleDone(false);
      }
    }
  };
  xhr.onerror = function() {
    handleDone(false);
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
            if (doneXhr.status === 200) {
              mainSection.style.display = "none";
              successCard.style.display = "block";
            } else {
              sendBtn.disabled = false;
              cameraBtn.disabled = false;
              galleryBtn.disabled = false;
              uploadErr.innerHTML = notSentMsg;
              uploadErr.style.display = "block";
            }
          }
        };
        doneXhr.onerror = function() {
          sendBtn.disabled = false;
          cameraBtn.disabled = false;
          galleryBtn.disabled = false;
          uploadErr.innerHTML = notSentMsg;
          uploadErr.style.display = "block";
        };
        doneXhr.send();
      } else {
        files = remainingFiles;
        renderThumbs();
        sendBtn.disabled = false;
        cameraBtn.disabled = false;
        galleryBtn.disabled = false;
        uploadErr.innerHTML = networkErrorMsg;
        uploadErr.style.display = "block";
      }
      return;
    }

    statusText.textContent = sent + " of " + total + " sent";
    progressFill.style.width = Math.round((sent / total) * 100) + "%";

    resizePhoto(files[i], function(blob, canSend) {
      if (!canSend || !blob) {
        uploadErr.innerHTML = cannotSendMsg;
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


def _stack_text(phrases_dict: dict[str, str], langs: list[str], p_size: str = "", s_size: str = "") -> str:
    parts = []
    for i, l in enumerate(langs):
        t = html.escape(phrases_dict.get(l, phrases_dict.get("en", "")))
        cls = "lp" if i == 0 else "ls"
        parts.append(f'<div class="{cls}">{t}</div>')
    return "".join(parts)


def _render_steps_box(langs: list[str]) -> str:
    steps = [
        ("[📷]", STEPS_PHRASES["step1"]),
        ("[👁]", STEPS_PHRASES["step2"]),
        ("[✓]", STEPS_PHRASES["step3"]),
    ]
    parts = ['<div class="steps-box">']
    for icon, s_dict in steps:
        parts.append('<div class="stp-row">')
        parts.append(f'<div class="stp-ic">{icon}</div><div>')
        for i, l in enumerate(langs):
            t = html.escape(s_dict.get(l, s_dict.get("en", "")))
            cls = "stp-p" if i == 0 else "stp-s"
            parts.append(f'<div class="{cls}">{t}</div>')
        parts.append('</div></div>')
    parts.append('</div>')
    return "".join(parts)


def _page_langs(case: cases.Case) -> list[str]:
    if hasattr(case, "langs") and case.langs and len(case.langs) > 1:
        return case.langs
    l = case.lang
    if l == "gu":
        return ["gu", "hi", "en"]
    elif l == "ta":
        return ["ta", "hi", "en"]
    elif l == "mr":
        return ["mr", "hi", "en"]
    elif l == "en":
        return ["en", "hi", "mr"]
    else:
        return ["hi", "mr", "en"]


def _render_photo_page(case: cases.Case) -> str:
    langs = _page_langs(case)

    tail = cases.number_tail(case)
    if tail:
        phone_parts = [PHRASES["for_phone"].get(l, PHRASES["for_phone"]["en"]).format(tail=tail) for l in langs]
        phone_header = " / ".join(phone_parts)
    else:
        phone_header = ""

    take_btn = _stack_text(PHRASES["take"], langs)
    pick_btn = _stack_text(PHRASES["pick"], langs)
    send_btn = _stack_text(PHRASES["send"], langs)
    photos_label = _stack_text(PHRASES["photos"], langs)
    limit_err = _stack_text(PHRASES["limit_err"], langs)
    notice = _stack_text(NOTICE_PHRASES, langs)
    done_msg = _stack_text(PHRASES["done_msg"], langs)
    network_err = _stack_text(PHRASES["network_err"], langs)
    cannot_send = _stack_text(PHRASES["cannot_send"], langs)
    not_sent = _stack_text(PHRASES["not_sent"], langs)
    steps_html = _render_steps_box(langs)

    html_out = PHOTO_HTML_TEMPLATE
    html_out = html_out.replace("__LANG__", html.escape(case.lang))
    html_out = html_out.replace("__PHONE_HEADER__", html.escape(phone_header))
    html_out = html_out.replace("__STEPS_HTML__", steps_html)
    html_out = html_out.replace("__TAKE_BTN__", take_btn)
    html_out = html_out.replace("__PICK_BTN__", pick_btn)
    html_out = html_out.replace("__PHOTOS_LABEL__", photos_label)
    html_out = html_out.replace("__SEND_BTN__", send_btn)
    html_out = html_out.replace("__DONE_MSG__", done_msg)
    html_out = html_out.replace("__LIMIT_ERR__", limit_err)
    html_out = html_out.replace("__NOTICE__", notice)
    html_out = html_out.replace("__NETWORK_ERR__", network_err)
    html_out = html_out.replace("__CANNOT_SEND_ERR__", cannot_send)
    html_out = html_out.replace("__NOT_SENT_ERR__", not_sent)
    html_out = html_out.replace("__TOKEN__", html.escape(case.token))
    return html_out


@photo_app.get("/p/{token}")
async def get_photo_page(token: str, request: Request):
    if not token or not cases.TOKEN_RE.match(token):
        time.sleep(1.0)
        err_page = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Not Found</title></head><body style='font-family:sans-serif;padding:2rem;text-align:center;'><h2>this link is no longer good / यह लिंक अब काम नहीं करता / ही लिंक आता चालत नाही</h2></body></html>"
        return HTMLResponse(content=err_page, status_code=404, headers={"Cache-Control": "no-store"})

    case = cases.get(token)
    if case is None:
        time.sleep(1.0)
        err_page = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Not Found</title></head><body style='font-family:sans-serif;padding:2rem;text-align:center;'><h2>this link is no longer good / यह लिंक अब काम नहीं करता / ही लिंक आता चालत नाही</h2></body></html>"
        return HTMLResponse(content=err_page, status_code=404, headers={"Cache-Control": "no-store"})

    if case.state in ("waiting", "photo") and case.photos:
        case = cases.drop_photos(token)

    _log_state(token, case.state)
    page_html = _render_photo_page(case)
    return HTMLResponse(content=page_html, status_code=200, headers={"Cache-Control": "no-store"})


@photo_app.post("/p/{token}/photo")
async def post_photo(token: str, request: Request):
    if not token or not cases.TOKEN_RE.match(token):
        time.sleep(1.0)
        return JSONResponse(status_code=404, content={"ok": False, "why": "case not found"})

    case = cases.get(token)
    if case is None:
        time.sleep(1.0)
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
            time.sleep(1.0)
            return JSONResponse(status_code=404, content={"ok": False, "why": err})
        else:
            return JSONResponse(status_code=400, content={"ok": False, "why": err})


@photo_app.post("/p/{token}/done")
async def post_done(token: str, request: Request):
    if not token or not cases.TOKEN_RE.match(token):
        time.sleep(1.0)
        return JSONResponse(status_code=404, content={"ok": False, "why": "case not found"})

    case = cases.get(token)
    if case is None:
        time.sleep(1.0)
        return JSONResponse(status_code=404, content={"ok": False, "why": "case not found"})

    if case.state in ("reading", "read", "approved", "called") or not case.photos:
        return JSONResponse(status_code=200, content={"ok": True})

    cases.mark_reading(token)
    _log_state(token, "reading")
    threading.Thread(target=_process_done, args=(token,), daemon=True).start()
    return JSONResponse(status_code=200, content={"ok": True})




# --- Door 0 stand-in (Step 3): one SMS text at a time, the same text a real SMS gateway would hand over.
# Everything below the route is real: join the pieces, cases.add_photo, then the same _process_done as Door 1.
_sms = SMSReassemblyManager()
_sms_done: set[tuple[str, int]] = set()       # photos already added (a double after the last piece is not added twice)
_sms_stamp: dict[str, int] = {}               # token -> the newest piece's number; an idle timer only fires for the newest
_sms_timer: dict[str, threading.Timer] = {}
_sms_lock = threading.Lock()
_SMS_CORS = {"Access-Control-Allow-Origin": "*"}   # the keypad app is a page on another port (make keypad-ui, :8080)


def _sms_open_case() -> Optional[cases.Case]:
    """One caller at a time: the newest case that still takes photos."""
    for c in cases.open_cases():
        if c.state in ("waiting", "photo"):
            return c
    return None


def _sms_start_reading(token: str) -> None:
    """The same three lines as /done."""
    case = cases.get(token)
    if case is None or case.state in ("reading", "read", "approved", "called") or not case.photos:
        return
    cases.mark_reading(token)
    _log_state(token, "reading")
    threading.Thread(target=_process_done, args=(token,), daemon=True).start()


def _sms_idle(token: str, stamp: int) -> None:
    with _sms_lock:
        if _sms_stamp.get(token) != stamp:
            return
    _sms_start_reading(token)


def _sms_touch(token: str) -> None:
    with _sms_lock:
        stamp = _sms_stamp[token] = _sms_stamp.get(token, 0) + 1
        old = _sms_timer.pop(token, None)
        if old:
            old.cancel()
        t = _sms_timer[token] = threading.Timer(tunables.SMS_DONE_S, _sms_idle, (token, stamp))
        t.daemon = True
        t.start()


@photo_app.post("/sms")
async def post_sms(request: Request):
    if not tunables.SMS_DOOR:
        return JSONResponse(status_code=404, content={"ok": False, "why": "not found"})
    try:
        body = await request.json()
        text = str(body["text"])
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "why": "need json with text"}, headers=_SMS_CORS)
    case = _sms_open_case()
    if case is None:                                  # no case is open: the piece is dropped
        return JSONResponse(status_code=200, content={"ok": False, "reply": "ERR NO_CASE"}, headers=_SMS_CORS)
    if text.strip().upper() == "H:DONE":              # the app's short last message
        _sms_start_reading(case.token)
        return JSONResponse(status_code=200, content={"ok": True, "reply": "DONE OK"}, headers=_SMS_CORS)
    sender = str(body.get("sender") or case.number or case.token)   # shape (sender, text); never returned or logged
    ok, reply, data = _sms.ingest_sms(sender, text)
    if ok:
        _sms_touch(case.token)
    if ok and data is not None:
        pkt = parse_sms_packet(text)                  # the photo is the message id; a double after the end adds nothing
        key = (case.token, pkt.msg_id if pkt else -1)
        if key not in _sms_done:
            try:
                cases.add_photo(case.token, data)
                _sms_done.add(key)
                _log_state(case.token, "photo")
            except ValueError as e:
                return JSONResponse(status_code=200, content={"ok": False, "reply": f"ERR {e}"}, headers=_SMS_CORS)
    return JSONResponse(status_code=200, content={"ok": ok, "reply": reply}, headers=_SMS_CORS)

# ==============================================================================
# 2. DESK APP (port 8003, 127.0.0.1 only, Pass 4 Keyboard-driven)
# ==============================================================================
desk_app = FastAPI()


@desk_app.middleware("http")
async def desk_host_origin_middleware(request: Request, call_next):
    host_hdr = request.headers.get("host", "").split(":")[0].strip().lower()
    allowed_hosts = {"127.0.0.1", "localhost", "testserver"}
    if host_hdr and host_hdr not in allowed_hosts:
        return Response(content="Forbidden host", status_code=403, media_type="text/plain")

    if request.method == "POST":
        origin = request.headers.get("origin", "").strip()
        if origin:
            m = re.match(r"^https?://([^/:]+)(?::(\d+))?", origin.lower())
            if not m:
                return Response(content="Forbidden origin", status_code=403, media_type="text/plain")
            orig_host = m.group(1)
            orig_port = m.group(2)
            if orig_host not in allowed_hosts:
                return Response(content="Forbidden origin host", status_code=403, media_type="text/plain")
            if orig_host in ("127.0.0.1", "localhost") and orig_port and int(orig_port) != DESK_PORT:
                return Response(content="Forbidden origin port", status_code=403, media_type="text/plain")

    return await call_next(request)


def _format_age(made_ts: float) -> str:
    diff = max(0.0, time.time() - made_ts)
    if diff < 60:
        return f"{int(diff)}s ago"
    mins = int(diff // 60)
    if mins < 60:
        return f"{mins}m ago"
    hours = int(mins // 60)
    return f"{hours}h ago"


def _case_step(state: str) -> str:
    if state == "waiting":
        return "link sent"
    elif state == "photo":
        return "photo came"
    elif state == "reading":
        return "being read"
    elif state in ("read", "approved"):
        return "answer ready"
    elif state == "called":
        return "called back"
    return "link sent"


def _case_to_dict(c: cases.Case) -> dict[str, Any]:
    raw_tail = cases.number_tail(c)
    last2 = raw_tail[-2:] if len(raw_tail) >= 2 else raw_tail
    by = str(c.finding.get("by", ""))
    is_stand_in = by.startswith("stand-in")

    return {
        "token": c.token,
        "tail": last2,
        "step": _case_step(c.state),
        "state": c.state,
        "time": time.strftime("%H:%M", time.localtime(c.made)),
        "age": _format_age(c.made),
        "langs": c.langs or [c.lang],
        "shows": str(c.finding.get("shows", "")),
        "wrong": str(c.finding.get("wrong", "")),
        "scheme": c.scheme,
        "say": c.say,
        "photos": [f"/photo/{c.token}/{i}" for i in range(len(c.photos))],
        "is_stand_in": is_stand_in,
    }


DESK_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Haqdaar Helper Desk</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background-color: #f8fafc;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.4;
  padding: 16px;
  max-width: 700px;
  margin: 0 auto;
}
.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 20px;
  font-weight: bold;
  padding: 12px 16px;
  background: #ffffff;
  border: 2px solid #0f172a;
  border-radius: 8px;
  margin-bottom: 16px;
}
.case-card {
  background: #ffffff;
  border: 2px solid #0f172a;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.steps-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 14px;
}
.step-item {
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
}
.step-item.active {
  background-color: #004488;
  color: #ffffff;
  font-weight: bold;
  border-color: #002244;
}
.step-arrow { color: #64748b; font-weight: bold; }
.photos-row {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.desk-thumb {
  width: 96px;
  height: 96px;
  min-width: 96px;
  min-height: 96px;
  object-fit: cover;
  border-radius: 6px;
  border: 2px solid #0f172a;
  cursor: pointer;
}
.field-line {
  font-size: 18px;
  margin-bottom: 8px;
  line-height: 1.3;
}
.stand-in-line {
  font-size: 16px;
  color: #b91c1c;
  font-weight: bold;
  margin-bottom: 8px;
}
.textarea-label {
  font-size: 18px;
  font-weight: bold;
  display: block;
  margin-top: 10px;
  margin-bottom: 4px;
}
textarea {
  width: 100%;
  font-family: inherit;
  font-size: 18px;
  line-height: 1.4;
  padding: 10px;
  border: 2px solid #0f172a;
  border-radius: 6px;
  margin-bottom: 14px;
  resize: vertical;
}
textarea:focus {
  outline: 3px solid #004488;
  outline-offset: 1px;
}
.actions-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
button {
  font-family: inherit;
  font-size: 18px;
  font-weight: bold;
  padding: 10px 14px;
  min-height: 48px;
  border: 2px solid #0f172a;
  border-radius: 6px;
  background: #f1f5f9;
  color: #0f172a;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
button:hover { background: #e2e8f0; }
button:focus { outline: 3px solid #004488; outline-offset: 2px; }
.btn-primary { background: #004488; color: #ffffff; border-color: #002244; }
.btn-primary:hover { background: #003366; }
.btn-warn { background: #fef08a; color: #854d0e; }
.btn-warn:hover { background: #fde047; }
.other-section {
  background: #ffffff;
  border: 2px solid #0f172a;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 16px;
}
.other-title { font-weight: bold; font-size: 18px; margin-bottom: 10px; }
.other-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  margin-bottom: 6px;
  cursor: pointer;
  font-size: 18px;
}
.other-item:hover { background: #f1f5f9; }
.other-item.selected {
  background: #e0f2fe;
  border-color: #0284c7;
  font-weight: bold;
}
.status-msg-bar {
  min-height: 28px;
  font-size: 18px;
  font-weight: bold;
  color: #004488;
  margin-bottom: 12px;
  padding: 0 4px;
}
.key-bar {
  background: #0f172a;
  color: #ffffff;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 16px;
  line-height: 1.4;
  margin-top: 8px;
}
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 9999;
  align-items: center;
  justify-content: center;
  padding: 16px;
  cursor: pointer;
}
.modal-overlay img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border: 3px solid #ffffff;
  border-radius: 8px;
}
</style>
</head>
<body>

<div class="header-bar">
  <div id="top-auto-line">Auto: __AUTO_STATE__</div>
  <div id="top-waiting-line">__WAITING_COUNT__ cases waiting</div>
</div>

<main id="active-case-container">
  <div class="case-card" id="active-card">
    <div class="steps-row" id="steps-bar">
      <span class="step-item" id="stp-0">link sent</span> <span class="step-arrow">&gt;</span>
      <span class="step-item" id="stp-1">photo came</span> <span class="step-arrow">&gt;</span>
      <span class="step-item" id="stp-2">being read</span> <span class="step-arrow">&gt;</span>
      <span class="step-item" id="stp-3">answer ready</span> <span class="step-arrow">&gt;</span>
      <span class="step-item" id="stp-4">called back</span>
    </div>

    <div class="photos-row" id="active-photos"></div>

    <div class="stand-in-line" id="stand-in-line" style="display:none;">
      read by a stand-in, not by Muse
    </div>

    <div class="field-line" id="shows-line"><strong>Saw:</strong> <span id="shows-text">-</span></div>
    <div class="field-line" id="scheme-line"><strong>Scheme:</strong> <span id="scheme-text">-</span></div>

    <label for="say-box" class="textarea-label">Text to say:</label>
    <textarea id="say-box" rows="3"></textarea>

    <div class="actions-row">
      <button type="button" id="btn-call" class="btn-primary" onclick="actionCallback()">Call back (Enter)</button>
      <button type="button" id="btn-edit" onclick="actionEdit()">Edit text (E)</button>
      <button type="button" id="btn-bad" class="btn-warn" onclick="actionNotClear()">Not clear (B)</button>
      <button type="button" id="btn-new" onclick="actionNew()">New test case (N)</button>
      <button type="button" id="btn-auto" onclick="actionToggleAuto()">Auto on / off (A)</button>
    </div>
  </div>
</main>

<div class="other-section">
  <div class="other-title">Other cases</div>
  <div id="other-cases-list">
    <div style="color:#64748b; font-size:18px;">No other cases</div>
  </div>
</div>

<div class="status-msg-bar" id="status-line"></div>

<div class="key-bar" id="key-bar">
  Keys: [↑/↓ or K/J: Move] [Enter: Call back] [E: Edit text] [Esc: Leave & save] [B: Not clear] [1-6: Big photo] [N: New case] [A: Auto on/off] [?: Help]
</div>

<div class="modal-overlay" id="photo-modal" onclick="closeModal()">
  <img id="modal-img" src="" alt="Big Photo">
</div>

<script>
var casesList = [];
var selectedToken = null;
var isEditing = false;
var autoMode = __INITIAL_AUTO__;
var statusTimer = null;
var isModalOpen = false;

var sayBox = document.getElementById("say-box");
var statusLine = document.getElementById("status-line");
var keyBar = document.getElementById("key-bar");
var photoModal = document.getElementById("photo-modal");
var modalImg = document.getElementById("modal-img");

sayBox.addEventListener("focus", function() { isEditing = true; });
sayBox.addEventListener("blur", function() { isEditing = false; });

function setStatusMsg(msg) {
  statusLine.textContent = msg;
  if (statusTimer) clearTimeout(statusTimer);
  statusTimer = setTimeout(function() {
    statusLine.textContent = "";
  }, 4000);
}

function showBigPhoto(url) {
  modalImg.src = url;
  photoModal.style.display = "flex";
  isModalOpen = true;
}

function closeModal() {
  photoModal.style.display = "none";
  modalImg.src = "";
  isModalOpen = false;
}

function markStep(stepName) {
  var names = ["link sent", "photo came", "being read", "answer ready", "called back"];
  for (var i = 0; i < 5; i++) {
    var el = document.getElementById("stp-" + i);
    if (el) {
      if (names[i] === stepName) {
        el.className = "step-item active";
      } else {
        el.className = "step-item";
      }
    }
  }
}

function renderUI() {
  document.getElementById("top-auto-line").textContent = "Auto: " + (autoMode ? "on" : "off");
  var waitingCount = 0;
  for (var i = 0; i < casesList.length; i++) {
    if (casesList[i].state !== "called") waitingCount++;
  }
  document.getElementById("top-waiting-line").textContent = waitingCount + " cases wait";

  if (casesList.length === 0) {
    document.getElementById("active-card").style.display = "none";
    document.getElementById("other-cases-list").innerHTML = "<div style='color:#64748b;'>No open cases</div>";
    return;
  }
  document.getElementById("active-card").style.display = "block";

  var activeCase = null;
  for (var i = 0; i < casesList.length; i++) {
    if (casesList[i].token === selectedToken) {
      activeCase = casesList[i];
      break;
    }
  }
  if (!activeCase && casesList.length > 0) {
    activeCase = casesList[0];
    selectedToken = activeCase.token;
  }

  // Active case fields
  markStep(activeCase.step);

  var standInEl = document.getElementById("stand-in-line");
  if (activeCase.is_stand_in) {
    standInEl.style.display = "block";
  } else {
    standInEl.style.display = "none";
  }

  document.getElementById("shows-text").textContent = activeCase.shows || "-";
  document.getElementById("scheme-text").textContent = activeCase.scheme || "-";

  // Text box: do not overwrite if user is typing in it
  if (!isEditing && document.activeElement !== sayBox) {
    if (sayBox.dataset.token !== activeCase.token || sayBox.value !== activeCase.say) {
      sayBox.value = activeCase.say || "";
      sayBox.dataset.token = activeCase.token;
    }
  }

  // Photos
  var photosRow = document.getElementById("active-photos");
  photosRow.innerHTML = "";
  if (activeCase.photos && activeCase.photos.length > 0) {
    for (var p = 0; p < activeCase.photos.length; p++) {
      (function(idx) {
        var imgUrl = activeCase.photos[idx];
        var img = document.createElement("img");
        img.src = imgUrl;
        img.className = "desk-thumb";
        img.alt = "Photo " + (idx + 1);
        img.onclick = function() { showBigPhoto(imgUrl); };
        photosRow.appendChild(img);
      })(p);
    }
  } else {
    photosRow.innerHTML = "<div style='color:#64748b; font-size:18px;'>No photos yet</div>";
  }

  // Other cases list (at most 10)
  var otherContainer = document.getElementById("other-cases-list");
  otherContainer.innerHTML = "";
  var count = 0;
  for (var i = 0; i < casesList.length; i++) {
    var c = casesList[i];
    if (c.token === activeCase.token) continue;
    if (count >= 10) break;
    count++;

    (function(item) {
      var row = document.createElement("div");
      row.className = "other-item";
      var tailStr = item.tail ? ".." + item.tail : "no num";
      var langsStr = (item.langs || []).join(", ");
      row.innerHTML = "<span>" + item.time + " (" + item.age + ") | " + tailStr + "</span><span>" + item.step + " | " + langsStr + "</span>";
      row.onclick = function() {
        selectedToken = item.token;
        renderUI();
      };
      otherContainer.appendChild(row);
    })(c);
  }
  if (count === 0) {
    otherContainer.innerHTML = "<div style='color:#64748b; font-size:18px;'>No other cases</div>";
  }
}

async function fetchCases() {
  try {
    var res = await fetch("/cases");
    if (res.ok) {
      var autoHdr = res.headers.get("X-Photo-Auto");
      if (autoHdr) autoMode = (autoHdr === "on");
      var data = await res.json();
      casesList = data || [];
      if (!selectedToken && casesList.length > 0) {
        selectedToken = casesList[0].token;
      }
      renderUI();
    }
  } catch(e) {}
}

async function actionCallback() {
  if (!selectedToken) {
    setStatusMsg("no case selected");
    return;
  }
  var txt = sayBox.value;
  try {
    var res = await fetch("/approve/" + selectedToken, {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: txt
    });
    if (res.ok) {
      setStatusMsg("call back is set");
      fetchCases();
    } else {
      var d = await res.json().catch(function() { return {}; });
      setStatusMsg("could not: " + (d.detail || res.statusText));
    }
  } catch(err) {
    setStatusMsg("could not: " + err.message);
  }
}

async function actionSave() {
  if (!selectedToken) return;
  var txt = sayBox.value;
  try {
    var res = await fetch("/save/" + selectedToken, {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: txt
    });
    if (res.ok) {
      setStatusMsg("saved");
      fetchCases();
    } else {
      var d = await res.json().catch(function() { return {}; });
      setStatusMsg("could not: " + (d.detail || res.statusText));
    }
  } catch(err) {
    setStatusMsg("could not: " + err.message);
  }
}

async function actionNotClear() {
  if (!selectedToken) {
    setStatusMsg("no case selected");
    return;
  }
  try {
    var res = await fetch("/not-clear/" + selectedToken, { method: "POST" });
    if (res.ok) {
      setStatusMsg("call back is set (not clear)");
      fetchCases();
    } else {
      var d = await res.json().catch(function() { return {}; });
      setStatusMsg("could not: " + (d.detail || res.statusText));
    }
  } catch(err) {
    setStatusMsg("could not: " + err.message);
  }
}

async function actionNew() {
  try {
    var res = await fetch("/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ langs: ["hi"] })
    });
    if (res.ok) {
      var d = await res.json();
      selectedToken = d.token;
      setStatusMsg("new case created");
      fetchCases();
    } else {
      setStatusMsg("could not create case");
    }
  } catch(err) {
    setStatusMsg("could not: " + err.message);
  }
}

async function actionToggleAuto() {
  try {
    var res = await fetch("/toggle-auto", { method: "POST" });
    if (res.ok) {
      var d = await res.json();
      autoMode = d.auto;
      setStatusMsg("Auto: " + (autoMode ? "on" : "off"));
      renderUI();
    }
  } catch(err) {
    setStatusMsg("could not toggle auto");
  }
}

function actionEdit() {
  sayBox.focus();
}

function moveCase(delta) {
  if (casesList.length <= 1) return;
  var idx = -1;
  for (var i = 0; i < casesList.length; i++) {
    if (casesList[i].token === selectedToken) {
      idx = i;
      break;
    }
  }
  if (idx === -1) idx = 0;
  var nextIdx = idx + delta;
  if (nextIdx < 0) nextIdx = casesList.length - 1;
  if (nextIdx >= casesList.length) nextIdx = 0;
  selectedToken = casesList[nextIdx].token;
  renderUI();
}

window.addEventListener("keydown", function(e) {
  if (isModalOpen) {
    closeModal();
    e.preventDefault();
    return;
  }

  // Inside text box: Esc leaves and saves
  if (document.activeElement === sayBox) {
    if (e.key === "Escape") {
      sayBox.blur();
      actionSave();
      e.preventDefault();
    }
    return;
  }

  var code = e.code || "";
  var key = e.key || "";

  if (key === "ArrowUp" || key === "k" || key === "K") {
    e.preventDefault();
    moveCase(-1);
    return;
  }
  if (key === "ArrowDown" || key === "j" || key === "J") {
    e.preventDefault();
    moveCase(1);
    return;
  }
  if (key === "Enter") {
    e.preventDefault();
    actionCallback();
    return;
  }
  if (key === "e" || key === "E") {
    e.preventDefault();
    actionEdit();
    return;
  }
  if (key === "b" || key === "B") {
    e.preventDefault();
    actionNotClear();
    return;
  }
  if (key === "n" || key === "N") {
    e.preventDefault();
    actionNew();
    return;
  }
  if (key === "a" || key === "A") {
    e.preventDefault();
    actionToggleAuto();
    return;
  }
  if (key === "?") {
    e.preventDefault();
    keyBar.style.display = keyBar.style.display === "none" ? "block" : "none";
    return;
  }

  // 1 to 6 (including numpad)
  var numMatch = key.match(/^[1-6]$/);
  if (!numMatch && code.startsWith("Numpad") && code.length === 7) {
    var numChar = code.charAt(6);
    if (numChar >= "1" && numChar <= "6") {
      numMatch = [numChar];
    }
  }
  if (numMatch) {
    e.preventDefault();
    var pIdx = parseInt(numMatch[0], 10) - 1;
    var activeCase = null;
    for (var i = 0; i < casesList.length; i++) {
      if (casesList[i].token === selectedToken) {
        activeCase = casesList[i];
        break;
      }
    }
    if (activeCase && activeCase.photos && activeCase.photos[pIdx]) {
      showBigPhoto(activeCase.photos[pIdx]);
    } else {
      setStatusMsg("no photo " + (pIdx + 1));
    }
    return;
  }
});

fetchCases();
setInterval(fetchCases, 3000);
</script>
</body>
</html>"""


@desk_app.get("/", response_class=HTMLResponse)
async def get_desk_home():
    open_list = cases.open_cases()
    waiting_count = sum(1 for c in open_list if c.state != "called")
    auto_str = "on" if _is_photo_auto() else "off"

    html_content = DESK_HTML_TEMPLATE
    html_content = html_content.replace("__AUTO_STATE__", auto_str)
    html_content = html_content.replace("__WAITING_COUNT__", str(waiting_count))
    html_content = html_content.replace("__INITIAL_AUTO__", "true" if _is_photo_auto() else "false")
    return HTMLResponse(content=html_content, status_code=200)


@desk_app.get("/cases")
async def get_desk_cases():
    open_list = cases.open_cases()
    result = [_case_to_dict(c) for c in open_list]
    headers = {
        "Cache-Control": "no-store",
        "X-Photo-Auto": "on" if _is_photo_auto() else "off",
    }
    return JSONResponse(status_code=200, content=result, headers=headers)


@desk_app.get("/status")
async def get_desk_status():
    return JSONResponse(status_code=200, content={"auto": _is_photo_auto()})


@desk_app.post("/toggle-auto")
async def post_toggle_auto():
    global _PHOTO_AUTO_RUNTIME
    _PHOTO_AUTO_RUNTIME = not _is_photo_auto()
    os.environ["PHOTO_AUTO"] = "true" if _PHOTO_AUTO_RUNTIME else "false"
    return JSONResponse(status_code=200, content={"ok": True, "auto": _PHOTO_AUTO_RUNTIME})


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


@desk_app.post("/not-clear/{token}")
async def post_desk_not_clear(token: str):
    if not token or not cases.TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        case = cases.mark_not_clear(token)
        call_back(case)
        _log_state(token, case.state)
        return JSONResponse(status_code=200, content={"ok": True, "state": case.state, "wrong": case.finding.get("wrong")})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@desk_app.post("/new")
async def post_desk_new(request: Request):
    langs = ["hi"]
    try:
        raw_body = await request.body()
        if raw_body:
            parsed = json.loads(raw_body.decode("utf-8"))
            if isinstance(parsed, dict) and "langs" in parsed:
                langs = parsed["langs"]
            elif isinstance(parsed, list):
                langs = parsed
    except Exception:
        pass

    case = cases.new_case(langs=langs)
    _log_state(case.token, case.state)
    return JSONResponse(
        status_code=200,
        content={"ok": True, "token": case.token, "link": cases.link(case), "langs": case.langs},
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
