"""tools/call_viewer.py

`make calls-ui` — a page that shows each call as a back and forth: what the AI said, what the
caller pressed or said, what the engine understood, and how long each part took.

It reads the call traces (haqdaar/data/trace.py) from <logs_dir>/trace/. It is its own small
server on 127.0.0.1 only, apart from the call server: the call server is open to the world
through the tunnel, and what callers say must not be. It only reads files, so it cannot slow
or break a call.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from haqdaar.contracts import tunables
from haqdaar.data.trace import TRACE_DIR

SAY = re.compile(r"^-> say (?P<name>.+?)(?: \((?P<dur>[\d.]+) s\))?$")
KEY = re.compile(r"^<- key (?P<key>\S+?)(?:: language (?P<lang>\w+))?(?: \((?P<why>.*)\))?$")
NO_KEY = re.compile(r"^<- no key: language (?P<lang>\w+)")
SPEECH = re.compile(r'^<- speech "(?P<text>.*)"(?: \((?P<lang>[\w-]+), stt (?P<stt>[\d.]+)s\))?$')
SILENCE = re.compile(r"^<- silence (?P<n>\d+)(?: \((?P<why>.*)\))?$")
NOISE = re.compile(r"^<- noise ?(?P<why>.*)$")

EAR_KEY_NOTES = ("pre-queued", "interrupted", "won over")  # how the ear words a key it saw first
LIVE_S = 20.0  # a trace with no end line, written this recently, is a call still going on
Lookup = Callable[[str, str], str]


# --- token -> the words the caller heard ---------------------------------------------

class Texts:
    """What each spoken token says, per snapshot. Loaded once per snapshot, on first use."""

    def __init__(self, snapshots_dir: Path | str | None = None) -> None:
        self._dir = Path(snapshots_dir or tunables.SNAPSHOTS_DIR)
        self._by_snapshot: dict[str, dict[tuple[str, str], str]] = {}

    def lookup(self, snapshot_id: str) -> Lookup:
        table = self._table(snapshot_id)

        def find(token: str, lang: str) -> str:
            if token.startswith("scheme:"):
                token = "/".join(token.split(":", 2)[1:])
            return table.get((token, lang)) or table.get((token, "all")) or ""

        return find

    def _table(self, snapshot_id: str) -> dict[tuple[str, str], str]:
        if snapshot_id not in self._by_snapshot:
            from haqdaar.data.pipeline.texts import all_texts

            schemes: list[dict[str, Any]] = []
            bands: dict[str, Any] = {}
            try:  # a sim on the test fixture has no snapshot on disk: fixed lines still resolve
                folder = self._dir / snapshot_id
                schemes = [json.loads(x) for x in (folder / "schemes.jsonl").read_text("utf-8").splitlines() if x.strip()]
                boxes = json.loads((folder / "vocab.json").read_text("utf-8")).get("boxes", {})
                bands = {box: meta["bands"] for box, meta in boxes.items() if "bands" in meta}
            except Exception:
                pass
            try:
                table = {(t.ref, t.lang): t.text for t in all_texts(schemes, bands)}
            except Exception:
                table = {}
            self._by_snapshot[snapshot_id] = table
        return self._by_snapshot[snapshot_id]


# --- trace file -> calls -------------------------------------------------------------

def read_calls(path: Path) -> list[list[dict[str, Any]]]:
    """The calls in one trace file. A call id used twice stacks two calls in one file."""
    calls: list[list[dict[str, Any]]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(raw)
        except Exception:
            continue  # a half-written last line while the call is live
        if not isinstance(row, dict):
            continue
        if "start" in row:
            calls.append([row])
        elif calls:
            calls[-1].append(row)
    return calls


def _turn_words(rec: dict[str, Any]) -> str:
    words = [str(rec.get("class", "?"))]
    if rec.get("box"):
        words.append(f"{rec['box']} = {rec.get('value')}")
    if rec.get("unknown_source"):
        words.append(str(rec["unknown_source"]))
    if rec.get("silence_n"):
        words.append(f"silence {rec['silence_n']}")
    if rec.get("candidate_count") is not None:
        words.append(f"{rec['candidate_count']} scheme name match")
    if rec.get("discarded_transcript"):
        words.append(f"dropped: {rec['discarded_transcript']}")
    if rec.get("invalid"):
        words.append("invalid")
    return " · ".join(words)


def build_call(rows: list[dict[str, Any]], lookup: Lookup = lambda token, lang: "") -> dict[str, Any]:
    """One call's trace rows -> the list of bubbles and the numbers for the top of the page."""
    start = rows[0] if rows else {}
    lang = "hi"
    items: list[dict[str, Any]] = []
    ai_end: Optional[float] = None    # when the AI's queued words finish playing
    heard_at: Optional[float] = None  # the caller's last input, until the AI answers it
    info: dict[str, Any] = {
        "call_id": start.get("start", ""), "at": start.get("at", ""),
        "snapshot": start.get("snapshot", ""), "lang": lang, "duration_s": 0.0, "turns": 0,
        "unclear": 0, "silences": 0, "problems": 0, "stop": "", "mode": "", "ended": "",
        "finished": False, "schemes": [], "ai_talk_s": 0.0, "slowest_reply_s": None,
    }

    def note(t: float, text: str, level: str = "note") -> None:
        items.append({"who": level, "t": t, "text": text})

    for row in rows[1:]:
        t = float(row.get("t") or 0.0)
        info["duration_s"] = max(info["duration_s"], t)

        rec = row.get("log")
        if isinstance(rec, dict):
            if "class" in rec:
                info["turns"] = max(info["turns"], int(rec.get("turn_n") or 0))
                if rec["class"] in ("UNCLEAR", "NOISE"):
                    info["unclear"] += 1
                if rec["class"] == "SILENCE":
                    info["silences"] += 1
                last = items[-1] if items else None
                if last and last["who"] == "caller" and "understood" not in last:
                    last["understood"], last["cls"], last["turn_n"] = _turn_words(rec), rec["class"], rec.get("turn_n")
                else:
                    note(t, f"turn {rec.get('turn_n')}: {_turn_words(rec)}")
            elif "slug" in rec:
                name = lookup(f"scheme:{rec['slug']}:name", rec.get("lang") or lang) or rec["slug"]
                info["schemes"].append(name)
                note(t, f"read out: {name} · {rec.get('ending')} · {', '.join(rec.get('sections') or [])}")
            elif "stop" in rec:
                info["stop"], info["mode"] = rec.get("stop") or "", rec.get("mode") or ""
                note(t, f"stopped asking: {rec.get('stop')} · ladder rung {rec.get('ladder_rung')} · mode {rec.get('mode')}")
            elif rec.get("mode") == "keypad_only":
                note(t, "voice gave up: keypad only from here", "problem")
                info["problems"] += 1
            elif "lang" in rec:
                lang = info["lang"] = rec["lang"]
                last = items[-1] if items else None
                if not (last and last["who"] == "caller" and last.get("lang") == lang):
                    note(t, f"language: {lang} ({rec.get('lang_source')})")
            else:
                note(t, json.dumps(rec, ensure_ascii=False))
            continue

        line = str(row.get("line") or "")
        if m := SAY.match(line):
            token, dur = m["name"], float(m["dur"] or 0.0)
            if token.startswith(("name:", "end:")):
                continue  # engine bookkeeping marks, not speech (the sim notes them)
            part = {"token": token, "text": lookup(token, lang), "dur": dur}
            if items and items[-1]["who"] == "ai":
                items[-1]["parts"].append(part)
                items[-1]["dur"] = round(items[-1]["dur"] + dur, 2)
            else:
                item = {"who": "ai", "t": t, "parts": [part], "dur": dur}
                if heard_at is not None:
                    item["reply_s"] = round(t - heard_at, 2)
                    info["slowest_reply_s"] = max(info["slowest_reply_s"] or 0.0, item["reply_s"])
                    heard_at = None
                items.append(item)
            ai_end = max(ai_end or t, t) + dur
            info["ai_talk_s"] = round(info["ai_talk_s"] + dur, 2)
            continue

        caller: Optional[dict[str, Any]] = None
        if m := KEY.match(line):
            last = items[-1] if items else None
            if (last and last["who"] == "caller" and last.get("key") == m["key"] and t - last["t"] < 0.3
                    and last.get("detail", "").startswith(EAR_KEY_NOTES)):
                last["detail"] = f"{m['why'] or ''}, {last['detail']}".strip(", ")
                continue  # the ear and the phone both note the same key press
            caller = {"kind": "key", "key": m["key"], "text": f"pressed {m['key']}", "detail": m["why"] or ""}
            if m["lang"]:
                lang = info["lang"] = caller["lang"] = m["lang"]
        elif m := NO_KEY.match(line):
            lang = info["lang"] = m["lang"]
            caller = {"kind": "silence", "text": "pressed nothing", "lang": lang, "detail": "default language"}
        elif m := SPEECH.match(line):
            caller = {"kind": "speech", "text": m["text"], "detail": f"heard as {m['lang']}" if m["lang"] else ""}
            if m["stt"]:
                caller["stt_s"] = float(m["stt"])
        elif m := SILENCE.match(line):
            caller = {"kind": "silence", "text": f"said nothing (silence {m['n']})", "detail": m["why"] or ""}
        elif m := NOISE.match(line):
            caller = {"kind": "noise", "text": "noise, no words", "detail": m["why"].strip("() ")}
        if caller is not None:
            caller.update(who="caller", t=t)
            if ai_end is not None:
                caller["wait_s"] = round(t - ai_end, 2)  # below 0: the caller cut in
            ai_end, heard_at = None, t
            items.append(caller)
        elif line.startswith("!!"):
            info["problems"] += 1
            note(t, line[2:].strip(), "problem")
        elif line.startswith("stop "):
            info["ended"] = "caller hung up"
            note(t, "caller hung up")
        elif line.startswith("call ") and line.endswith("finished"):
            info["finished"] = True
            info["ended"] = info["ended"] or "we ended the call"
        elif line.strip().startswith("skip "):
            note(t, f"not said, a key was waiting: {line.strip()[5:].replace(' (a key is waiting)', '')}")
        elif line.strip():
            note(t, line.strip())

    info["duration_s"] = round(info["duration_s"], 1)
    info["timed"] = info["ai_talk_s"] > 0
    if not info["timed"]:  # a sim plays no sound, so its gaps mean nothing
        info["slowest_reply_s"] = None
        for item in items:
            item.pop("wait_s", None)
            item.pop("reply_s", None)
    return {"info": info, "items": items}


def _verdict(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The 5.2 judge's word on a finished call. None if it cannot be judged (no snapshot)."""
    try:
        from tools.judge import judge_call_log

        start = rows[0]
        opened = {"call_id": start.get("start", ""), "snapshot_id": start.get("snapshot", ""),
                  "caller_hash": "", "lang": "hi", "lang_source": "default", "t0": 0.0}
        result = judge_call_log([opened] + [r["log"] for r in rows if isinstance(r.get("log"), dict)])
        return {"passed": bool(result.passed), "reason": str(result.reason)}
    except Exception:
        return None


class Calls:
    """Every call found under the trace folders, newest first. Parsed again only on change."""

    def __init__(self, dirs: list[Path | str], texts: Optional[Texts] = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._dirs = [Path(d) for d in dirs]
        self._texts = texts or Texts()
        self._clock = clock
        self._cache: dict[Path, tuple[tuple[float, int], list[dict[str, Any]]]] = {}

    def all(self) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for folder in self._dirs:
            for path in sorted((folder / TRACE_DIR).glob("*.jsonl")):
                for n, call in enumerate(self._file(path)):
                    found[path.stem if n == 0 else f"{path.stem}~{n + 1}"] = call
        return dict(sorted(found.items(), key=lambda kv: kv[1]["info"]["at"], reverse=True))

    def _file(self, path: Path) -> list[dict[str, Any]]:
        try:
            stat = path.stat()
            stamp = (stat.st_mtime, stat.st_size)
            fresh = self._clock() - stat.st_mtime < LIVE_S
            if not fresh and path in self._cache and self._cache[path][0] == stamp:
                return self._cache[path][1]
            calls = []
            for rows in read_calls(path):
                call = build_call(rows, self._texts.lookup(rows[0].get("snapshot", "")))
                info = call["info"]
                info["live"] = fresh and not info["finished"]
                if not info["finished"] and not info["live"]:
                    info["ended"] = (info["ended"] + ", no end line").lstrip(", ")
                info["source"] = "sim" if info["call_id"].startswith(("sim", "demo", "real_sim", "test")) else "phone"
                info["verdict"] = None if info["live"] else _verdict(rows)
                info["rev"] = stat.st_size
                calls.append(call)
            self._cache[path] = (stamp, calls)
            return calls
        except Exception:
            return []


def make_app(dirs: list[Path | str], texts: Optional[Texts] = None) -> FastAPI:
    app = FastAPI(title="haqdaar calls")
    calls = Calls(dirs, texts)

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE

    @app.get("/api/calls")
    def list_calls() -> list[dict[str, Any]]:
        return [{"key": key, **call["info"]} for key, call in calls.all().items()]

    @app.get("/api/calls/{key}")
    def one_call(key: str) -> dict[str, Any]:
        call = calls.all().get(key)
        if call is None:
            raise HTTPException(status_code=404, detail="no such call")
        return {"key": key, **call}

    return app


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Haqdaar calls</title>
<style>
:root {
  --bg: #f6f5f1; --panel: #ffffff; --ink: #1d1c1a; --soft: #6b6862; --line: #e3e0d8;
  --ai: #ffffff; --caller: #1f4f46; --caller-ink: #ffffff; --accent: #1f4f46;
  --warn: #9a6200; --warn-bg: #fdf1d6; --bad: #a52a1c; --bad-bg: #fbe3df; --good: #1f6b3a; --good-bg: #dff3e4;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161614; --panel: #1f1f1c; --ink: #ecebe6; --soft: #9c9a92; --line: #33322e;
    --ai: #262622; --caller: #2f7a6c; --caller-ink: #ffffff; --accent: #6fc7b4;
    --warn: #f0c060; --warn-bg: #3d3112; --bad: #ff9c8e; --bad-bg: #45201b; --good: #84d79c; --good-bg: #1b3a25;
  }
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", "Noto Sans Devanagari", sans-serif; }
.app { display: grid; grid-template-columns: 330px minmax(0, 1fr); height: 100vh; }
aside { border-right: 1px solid var(--line); background: var(--panel); display: flex; flex-direction: column; min-height: 0; }
aside header { padding: 16px 16px 10px; border-bottom: 1px solid var(--line); }
h1 { font-size: 17px; margin: 0 0 2px; }
.sub { color: var(--soft); font-size: 13px; }
label.pick { display: flex; gap: 6px; align-items: center; margin-top: 8px; font-size: 13px; color: var(--soft); cursor: pointer; }
#list { overflow-y: auto; flex: 1; }
.row { display: block; width: 100%; text-align: left; background: none; border: 0; border-bottom: 1px solid var(--line);
  padding: 10px 16px; color: inherit; font: inherit; cursor: pointer; }
.row:hover { background: var(--bg); }
.row.on { background: var(--bg); box-shadow: inset 3px 0 0 var(--accent); }
.row .top { display: flex; justify-content: space-between; gap: 8px; font-variant-numeric: tabular-nums; }
.row .id { color: var(--soft); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.tag { font-size: 11.5px; padding: 1px 7px; border-radius: 99px; border: 1px solid var(--line); color: var(--soft); white-space: nowrap; }
.tag.good { color: var(--good); background: var(--good-bg); border-color: transparent; }
.tag.bad { color: var(--bad); background: var(--bad-bg); border-color: transparent; }
.tag.warn { color: var(--warn); background: var(--warn-bg); border-color: transparent; }
.tag.live { color: #fff; background: var(--bad); border-color: transparent; }
main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
#head { padding: 14px 22px; border-bottom: 1px solid var(--line); background: var(--panel); }
#head h2 { margin: 0; font-size: 16px; overflow-wrap: anywhere; }
.stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); gap: 8px; margin-top: 10px; }
.stat { border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px; }
.stat b { display: block; font-size: 16px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.stat span { color: var(--soft); font-size: 12px; }
.stat.wide { grid-column: span 2; }
.stat.warn b { color: var(--warn); } .stat.bad b { color: var(--bad); } .stat.good b { color: var(--good); }
.why { margin-top: 8px; font-size: 13px; color: var(--soft); }
#chat { flex: 1; overflow-y: auto; padding: 18px 22px 40px; }
.msg { max-width: min(640px, 82%); margin: 10px 0; }
.msg .who { font-size: 12px; color: var(--soft); margin-bottom: 2px; font-variant-numeric: tabular-nums; }
.bubble { padding: 9px 13px; border-radius: 14px; border: 1px solid var(--line); background: var(--ai); overflow-wrap: anywhere; }
.msg.ai .bubble { border-top-left-radius: 4px; }
.msg.caller { margin-left: auto; }
.msg.caller .who { text-align: right; }
.msg.caller .bubble { background: var(--caller); color: var(--caller-ink); border-color: transparent; border-top-right-radius: 4px; font-size: 16px; }
.msg.caller .tags { justify-content: flex-end; }
.part + .part { margin-top: 4px; }
.token { font: 11.5px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--soft); }
.note { text-align: center; color: var(--soft); font-size: 12.5px; margin: 8px auto; max-width: 720px; overflow-wrap: anywhere; }
.note.problem { color: var(--bad); background: var(--bad-bg); border-radius: 8px; padding: 5px 10px; }
.empty { color: var(--soft); padding: 40px 22px; }
code { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--bg); padding: 1px 5px; border-radius: 4px; }
@media (max-width: 760px) {
  .app { grid-template-columns: minmax(0, 1fr); grid-template-rows: 30vh minmax(0, 1fr); }
  main { overflow-y: auto; }
  #chat { overflow-y: visible; flex: none; }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  aside { border-right: 0; border-bottom: 1px solid var(--line); }
  #chat, #head { padding-left: 16px; padding-right: 16px; }
}
</style>
</head>
<body>
<div class="app">
  <aside>
    <header>
      <h1>Haqdaar calls</h1>
      <div class="sub" id="count">loading…</div>
      <label class="pick"><input type="checkbox" id="phoneOnly"> real phone calls only</label>
    </header>
    <div id="list"></div>
  </aside>
  <main>
    <div id="head"><h2>Pick a call on the left</h2></div>
    <div id="chat"><div class="empty">Each call shows as a back and forth: the AI on the left, the caller on the right,
      and what the engine made of it in between. A call that is going on right now updates by itself.</div></div>
  </main>
</div>
<script>
const $ = (id) => document.getElementById(id);
const LANG = {hi: "Hindi", mr: "Marathi", en: "English"};
const STOP = {survivors_le_4: "4 or fewer schemes left", max_turns: "turn limit reached",
  max_questions: "question limit reached", no_split: "no question could narrow it more",
  zero_survivors: "no scheme matched"};
const SLOW_S = 1.2, VERY_SLOW_S = 3;   // 1.2 s is the reply budget
let calls = [], picked = location.hash.slice(1) || null, shownRev = null;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function clock(t) {
  const m = Math.floor(t / 60), s = t - m * 60;
  return m + ":" + (s < 10 ? "0" : "") + s.toFixed(1);
}
function secs(s) { return (Math.round(s * 10) / 10) + " s"; }
function long(s) { return s >= 60 ? Math.floor(s / 60) + " min " + Math.round(s % 60) + " s" : secs(s); }
function when(at) { return at ? at.replace("T", "  ").slice(5, 20) : "no time"; }
function tag(text, cls) { return el("span", "tag" + (cls ? " " + cls : ""), text); }

function drawList() {
  const phoneOnly = $("phoneOnly").checked;
  const shown = calls.filter((c) => !phoneOnly || c.source === "phone");
  $("count").textContent = shown.length + (shown.length === 1 ? " call" : " calls") +
    (calls.length ? "" : ". Make a call, or run make sim, and it shows up here.");
  const list = $("list");
  list.replaceChildren();
  for (const c of shown) {
    const row = el("button", "row" + (c.key === picked ? " on" : ""));
    const top = el("div", "top");
    top.append(el("span", "", when(c.at)), el("span", "", c.timed ? long(c.duration_s) : ""));
    row.append(top, el("div", "id", c.call_id));
    const tags = el("div", "tags");
    if (c.live) tags.append(tag("LIVE", "live"));
    tags.append(tag(c.source), tag(LANG[c.lang] || c.lang), tag(c.turns + " turns"));
    if (c.verdict) tags.append(tag(c.verdict.passed ? "PASS" : "FAIL", c.verdict.passed ? "good" : "bad"));
    if (c.problems) tags.append(tag(c.problems + " problem" + (c.problems > 1 ? "s" : ""), "bad"));
    if (c.unclear) tags.append(tag(c.unclear + " not understood", "warn"));
    row.append(tags);
    row.onclick = () => { picked = c.key; location.hash = c.key; shownRev = null; drawList(); loadCall(); };
    list.append(row);
  }
}

function stat(label, value, cls) {
  const s = el("div", "stat" + (cls ? " " + cls : ""));
  s.append(el("b", "", value), el("span", "", label));
  return s;
}

function drawCall(call) {
  const i = call.info, head = $("head"), chat = $("chat");
  const atBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 60;
  head.replaceChildren();
  head.append(el("h2", "", when(i.at) + "   " + i.call_id + (i.live ? "   (live)" : "")));
  const stats = el("div", "stats");
  const slow = i.slowest_reply_s;
  stats.append(
    stat("call length", i.timed ? long(i.duration_s) : "not timed (sim)"),
    stat("language", LANG[i.lang] || i.lang),
    stat("turns", String(i.turns)),
    stat("AI talking", i.ai_talk_s ? long(i.ai_talk_s) : "not timed"),
    stat("slowest AI reply", slow == null ? (i.timed ? "none" : "not timed") : secs(slow), slow > VERY_SLOW_S ? "bad" : slow > SLOW_S ? "warn" : ""),
    stat("not understood", String(i.unclear), i.unclear ? "warn" : ""),
    stat("silences", String(i.silences), i.silences ? "warn" : ""),
    stat("problems", String(i.problems), i.problems ? "bad" : ""),
    stat("why it stopped asking", STOP[i.stop] || i.stop || "did not get there", (i.stop ? "" : "warn") + " wide"),
    stat("how it ended", i.live ? "still going" : (i.ended || "unknown"), (/no end line/.test(i.ended) ? "bad" : "") + " wide"),
    stat("judge", i.verdict ? (i.verdict.passed ? "PASS" : "FAIL") : "not judged", i.verdict ? (i.verdict.passed ? "good" : "bad") : ""),
  );
  head.append(stats);
  const why = [];
  if (i.verdict && i.verdict.reason) why.push("Judge: " + i.verdict.reason);
  if (i.schemes.length) why.push("Schemes read out: " + i.schemes.join(", "));
  if (i.mode) why.push("Mode: " + i.mode);
  if (i.snapshot) why.push("Snapshot: " + i.snapshot);
  if (why.length) head.append(el("div", "why", why.join("  ·  ")));

  chat.replaceChildren();
  for (const it of call.items) {
    if (it.who === "note" || it.who === "problem") {
      chat.append(el("div", "note" + (it.who === "problem" ? " problem" : ""), clock(it.t) + "   " + it.text));
      continue;
    }
    const msg = el("div", "msg " + it.who), bubble = el("div", "bubble"), tags = el("div", "tags");
    msg.append(el("div", "who", (it.who === "ai" ? "AI" : "Caller") + "  ·  " + clock(it.t)));
    if (it.who === "ai") {
      for (const p of it.parts) {
        const part = el("div", "part");
        if (p.text) part.append(el("div", "", p.text));
        part.append(el("div", "token", p.token + (p.dur ? "  " + secs(p.dur) : "")));
        bubble.append(part);
      }
      if (it.dur) tags.append(tag("spoke for " + secs(it.dur)));
      if (it.reply_s != null) tags.append(tag("replied in " + secs(it.reply_s),
        it.reply_s > VERY_SLOW_S ? "bad" : it.reply_s > SLOW_S ? "warn" : ""));
    } else {
      bubble.textContent = it.kind === "speech" ? "“" + it.text + "”" : it.text;
      if (it.understood) tags.append(tag("turn " + it.turn_n + ": " + it.understood,
        it.cls === "UNCLEAR" || it.cls === "NOISE" ? "warn" : it.cls === "SILENCE" ? "" : "good"));
      if (it.lang) tags.append(tag("language " + (LANG[it.lang] || it.lang)));
      if (it.wait_s != null) tags.append(it.wait_s < 0
        ? tag("cut in " + secs(-it.wait_s) + " before the AI finished")
        : tag("after " + secs(it.wait_s) + " of quiet"));
      if (it.stt_s != null) tags.append(tag("speech to text " + secs(it.stt_s), it.stt_s > SLOW_S ? "warn" : ""));
      if (it.detail) tags.append(tag(it.detail));
    }
    msg.append(bubble, tags);
    chat.append(msg);
  }
  if (!call.items.length) chat.append(el("div", "empty", "Nothing has happened on this call yet."));
  if (shownRev === null) chat.scrollTop = i.live ? chat.scrollHeight : 0;
  else if (atBottom) chat.scrollTop = chat.scrollHeight;
  shownRev = i.rev;
}

async function loadCall() {
  if (!picked) return;
  try {
    const r = await fetch("/api/calls/" + encodeURIComponent(picked));
    if (r.ok) drawCall(await r.json());
  } catch (e) { /* the viewer was stopped: keep what is on screen */ }
}

async function tick() {
  try {
    const r = await fetch("/api/calls");
    calls = await r.json();
    if (!picked && calls.length) { picked = calls[0].key; }
    drawList();
    const mine = calls.find((c) => c.key === picked);
    if (mine && mine.rev !== shownRev) await loadCall();
  } catch (e) { $("count").textContent = "the viewer is not running (make calls-ui)"; }
}
$("phoneOnly").onchange = drawList;
tick();
setInterval(tick, 2000);
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Show calls as a back and forth, with timings.")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--dirs", nargs="*", default=[tunables.CALL_LOGS_DIR, "logs"],
                        help="log folders to look in; each holds a trace/ folder")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    import uvicorn

    url = f"http://127.0.0.1:{args.port}"
    print(f"call page: {url}   (this computer only; Ctrl+C to stop)")
    if not args.no_open:
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(make_app(args.dirs), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
