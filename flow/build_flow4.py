"""Builds Chart 4: HAQDAAR Call Flow with Photo Architecture (Online & Offline).

Extends Chart 3 (talk + cut-in + keys) with the complete photo architecture:
- In-call photo triggering (spoken keywords & Key 9)
- Case creation & context snapshot (token, phone privacy, languages, call_id)
- SMS dispatch & Call 1 clean hangup (PHOTO_HANGUP)
- Door 1: Online Mobile Web flow (<20KB standalone HTML, camera/picker, canvas shrink, port 8002)
- Door 0: Offline Feature Phone Keypad SMS flow (10 SMS pieces, reassembler) & Rural Social Proxy bridges (Kiosk QR, 3-digit token)
- Unified storage, async Vision AI reader (Muse/local), Budget Guard (Rs 30/day), Dose Guard, Scheme RAG
- Photo Operator Desk (port 8003, localhost only, keyboard controls, PHOTO_AUTO)
- Automated Call-Back Daemon (photo_back.py, idle line check, Twilio place_call)
- Call 2: Context-aware spoken diagnosis (_call_back), photo quality check & seamless return to main dialog.

Ensures zero changes to charts 1, 2, or 3.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flowlib
from flowlib import Chart, check_file
import build_flows

HERE = os.path.dirname(os.path.abspath(__file__))

# Extend flowlib layers
flowlib.STYLE["photo"] = ("#7048e8", "#f3f0ff")    # purple: core photo architecture
flowlib.STYLE["online"] = ("#0c8599", "#e3fafc")   # cyan: door 1 online web
flowlib.STYLE["offline"] = ("#c2255c", "#fff0f6")  # magenta: door 0 offline keypad & proxy

NAME_4 = "4-talk-flow-with-photo"
TITLE_4 = "HAQDAAR call flow, chart 4 of 4: talk + cut-in + keys + photo (online & offline)"


def build_chart_4():
    # Build chart 3 as base (level 3)
    c = build_flows.build(3)
    c.title = TITLE_4

    n, a = c.node, c.arrow
    P = "photo"
    ON = "online"
    OFF = "offline"

    # Reference existing nodes
    listen = c.nodes["listen"]
    start = c.nodes["start"]

    # Update legend in top right
    c.note("purple = photo architecture (online & offline)", 1250, start.top + 250, layer="photo", fs=18, w=700)
    c.note("cyan = Door 1 (online web) / magenta = Door 0 (offline keypad)", 1250, start.top + 280, layer="online", fs=16, w=700)

    # Empty corridor between XR (right=1747) and people (left=2070):
    G_P_RET = 1980        # return lane for Call 2 (outer)
    G_P_NO = 1920         # lane for confirm 'no' (inner)
    Y_TOP_CORRIDOR = 865  # corridor above listen.top (928) and below end_q.bottom (826.5)

    # Column X coordinates for photo architecture
    CX_MID = 3450
    CX_D1 = 3050     # Door 1 column
    CX_D0 = 3850     # Door 0 column
    CX_RULES = 4500  # Rules note column

    # ---------------- STAGE 1: In-Call Trigger, SMS & Hangup ----------------
    ev_photo = n("ev_photo", "ANY TIME in talk: caller speaks photo words (\"फोटो भेजना है\", \"I want to send photo\"), "
                 "names visual damage (crop pest, animal disease, housing crack), or presses key 9",
                 CX_MID, top=420, w=500, kind="event", layer=P)

    p_offer = n("p_offer", "AGENT ASKS TO CONFIRM\n\"Do you want to send a photo? I will send a link by SMS and call you back.\"\n"
                "Triggered by word spotter or key 9 in code, not model.",
                CX_MID, top=ev_photo.bottom + 50, w=500, layer=P)

    p_confirm = n("p_confirm", "Caller says yes or presses 9?", CX_MID, top=p_offer.bottom + 50, kind="diamond", w=240, layer=P)

    p_case = n("p_case", "CASE CREATED & CONTEXT SAVED\n- 10-char secure token (PHOTO_DIR/<token>/)\n"
               "- Caller phone number kept in case only (never in links/logs/pages, wiped after call-back or 24h)\n"
               "- Records languages spoken so far (up to 4 codes)\n"
               "- Saves Call 1 ID and answered qualification facts",
               CX_MID, top=p_confirm.bottom + 50, w=500, layer=P)

    p_sms = n("p_sms", "SMS SENT VIA TWILIO\nSMS sent to caller's phone:\n"
              "\"Haqdaar: Photo link: https://<domain>/p/<token> . No internet: open Haqdaar app.\"\n"
              "Agent speaks fixed line: \"I have sent a link by SMS. Send the photo. I will call you back.\"",
              CX_MID, top=p_case.bottom + 50, w=500, layer=P)

    p_hang = n("p_hang", "CALL 1 HANGS UP (PHOTO_HANGUP=true)\nLine disconnects cleanly. Saves all state in case.json. "
               "Phone line is freed for other callers while photos are captured.",
               CX_MID, top=p_sms.bottom + 50, w=500, layer=P)

    p_door_split = n("p_door_split", "Which door does caller use?", CX_MID, top=p_hang.bottom + 50, kind="diamond", w=250, layer=P)

    a("ev_photo", "b", "p_offer", "t", layer=P)
    a("p_offer", "b", "p_confirm", "t", layer=P)
    a("p_confirm", "b", "p_case", "t", layer=P, label="yes")
    # p_confirm 'no' returns to listen via top corridor, avoiding remind
    a("p_confirm", "l", "listen", ("t", 0.7),
      via=[("x", G_P_NO), ("y", Y_TOP_CORRIDOR - 5), ("x", listen.fx(0.7))],
      layer=P, label="no: talk goes on", lab=(0, 0.5, 0, 0), lw=140)
    a("p_case", "b", "p_sms", "t", layer=P)
    a("p_sms", "b", "p_hang", "t", layer=P)
    a("p_hang", "b", "p_door_split", "t", layer=P)

    # ---------------- STAGE 2: The Two Ingestion Doors (Online vs Offline) ----------------
    # Door 1 (Online) - Left
    p_web = n("p_web", "DOOR 1: ONLINE MOBILE WEB PAGE\nCaller taps link in SMS -> opens https://<domain>/p/<token>\n"
              "- Served by photo web server on port 8002 (via tunnel)\n"
              "- Standalone HTML page < 20 KB (no CDN/external JS)\n"
              "- Multi-language UI in caller's spoken languages (hi/mr/en/gu/ta)\n"
              "- Responsive viewport, high-contrast, large touch targets",
              CX_D1, top=p_door_split.bottom + 110, w=450, layer=ON)

    p_buttons = n("p_buttons", "MOBILE CAMERA & SELECTION\n- Big accessible buttons (>= 56px height):\n"
                  "  1. \"Take Photo\" (direct camera capture)\n"
                  "  2. \"Pick Photos\" (multi-select from gallery, up to 6)\n"
                  "- Visual thumbnails with delete 'x' button (>= 44px)\n"
                  "- Clear pictograms: [📷] Take, [👁] Preview, [✓] Sent",
                  CX_D1, top=p_web.bottom + 50, w=450, layer=ON)

    p_shrink = n("p_shrink", "CLIENT-SIDE IMAGE SHRINK\n- HTML5 Canvas automatically resizes photos (~1000px, < 5 MB) for fast upload on 2G/3G\n"
                 "- Canvas toBlob with toDataURL fallback\n"
                 "- Memory-safe client compression prevents phone browser crash",
                 CX_D1, top=p_buttons.bottom + 50, w=450, layer=ON)

    p_upload = n("p_upload", "PHOTO UPLOAD & STATE LOCK\n- Uploads photo files via POST /p/<token>/photo\n"
                 "- Caller taps \"Send\" -> POST /p/<token>/done\n"
                 "- Server validates: max 6 photos, max 5 MB, image format only\n"
                 "- State locks to \"reading\" (blocks duplicate spends)",
                 CX_D1, top=p_shrink.bottom + 50, w=450, layer=ON)

    # Door 0 (Offline) - Right
    p_door0 = n("p_door0", "DOOR 0: OFFLINE (KEYPAD PHONE / NO DATA)\nCaller has an Rs 800 phone, no mobile data, cannot open links.\n"
                "Uses pre-installed Keypad SMS App OR Rural Social Proxy infrastructure.",
                CX_D0, top=p_door_split.bottom + 110, w=450, layer=OFF)

    p_keypad_app = n("p_keypad_app", "KEYPAD SMS APP (keypad_app/)\n- Put on phone beforehand by Govt Krishi Mitra / CSC VLE\n"
                     "- Ultra-compact UI (< 20 KB) for 240x320 keypad screen\n"
                     "- Camera capture + aggressive downscale (<= 1-5 KB total)\n"
                     "- Slices JPEG into at most 10 SMS pieces (~136 chars base64 each)\n"
                     "- Emits via sms:<number>?body=<piece>",
                     CX_D0, top=p_door0.bottom + 50, w=450, layer=OFF)

    p_proxy = n("p_proxy", "RURAL SOCIAL PROXY BRIDGES (alternative)\n1. Spoken 3-digit Case Token: Voice/SMS gives code \"412\"; family member/neighbor uploads on smartphone\n"
                "2. Fertilizer Shop (Khad-Beej Dukandaar) Kiosk: Standee QR; shopkeeper snaps photo; Haqdaar calls farmer directly\n"
                "3. Krishi Mitra Push-Task: Village field worker visits and captures photo for farmer",
                CX_D0, top=p_keypad_app.bottom + 50, w=450, layer=OFF)

    p_reasm = n("p_reasm", "SMS REASSEMBLY MANAGER (reassembler.py)\n- Route POST /sms/inbound on port 8002 (SMS_DOOR=true)\n"
                "- Ingests pieces (sender, text), tracks indices, drops duplicates\n"
                "- Returns ACK with missing piece list\n"
                "- When all pieces arrive (or \"done\" message / 2 min timeout), reconstructs binary JPEG byte-stream",
                CX_D0, top=p_proxy.bottom + 50, w=450, layer=OFF)

    # Four distinct diamond exits for p_door_split:
    # 'l' -> Door 1
    a("p_door_split", "l", "p_web", "t", via=[("x", CX_D1)], layer=ON,
      label="Door 1: has internet / data", lab=(1, 0.75, -95, 0), lw=180)
    a("p_web", "b", "p_buttons", "t", layer=ON)
    a("p_buttons", "b", "p_shrink", "t", layer=ON)
    a("p_shrink", "b", "p_upload", "t", layer=ON)

    # 'b' -> Door 0
    a("p_door_split", "b", "p_door0", "t", via=[("y", p_door_split.bottom + 50), ("x", CX_D0)], layer=OFF,
      label="Door 0: no internet / Rs 800 phone", lab=(1, 0.5, 0, 24), lw=200)
    a("p_door0", "b", "p_keypad_app", "t", layer=OFF)
    a("p_keypad_app", "b", "p_proxy", "t", layer=OFF)
    a("p_proxy", "b", "p_reasm", "t", layer=OFF)

    # ---------------- STAGE 3: Unified Storage, Vision AI & Scheme RAG ----------------
    y_s3_start = max(p_upload.bottom, p_reasm.bottom) + 70

    p_store = n("p_store", "UNIFIED CASE STORAGE\nBoth Door 1 and Door 0 add binary JPEG photos via cases.add_photo(token, jpeg_bytes).\n"
                "- Stored in PHOTO_DIR/<token>/ on disk\n"
                "- Status updates: \"waiting\" -> \"photo\" -> \"reading\"\n"
                "- Automatic 10-minute sweep cleans cases past 24 hours",
                CX_MID, top=y_s3_start, w=500, layer=P)

    p_reader = n("p_reader", "VISION AI READER (reader.py)\nRuns in background thread pool (port 8002 stays unblocked).\n"
                 "- Reader plug: PHOTO_READER = auto | muse | http | stand-in\n"
                 "- Budget Guard: checks daily limit (Rs 30/day cap on Muse API; skips if limit reached)\n"
                 "- Inspects up to 4 photos: returns shows (crop description), wrong (pest/disease), sure (confidence 0-1), search (keywords)",
                 CX_MID, top=p_store.bottom + 50, w=500, layer=P)

    p_dose = n("p_dose", "DOSE GUARD & SAFETY SANITIZATION\n- Strips chemical brand names, medicines, and drug dosages (mg, gm, tablet, गोली, spray dosage)\n"
               "- Prevents AI hallucinations or dangerous medical advice\n"
               "- Truncates finding text to safe 400-char boundary",
               CX_MID, top=p_reader.bottom + 50, w=500, layer=P)

    p_rag = n("p_rag", "SCHEME RAG MATCHING\n- Searches Chunk Index (chunk_index.py) using search keywords\n"
              "- Matches government compensation & support schemes (e.g. PM Fasal Bima Yojana - PMFBY, disaster relief)\n"
              "- Case status advances to \"read\"",
              CX_MID, top=p_dose.bottom + 50, w=500, layer=P)

    a("p_upload", "b", "p_store", ("t", 0.3), via=[("y", y_s3_start - 35), ("x", CX_MID - 100)], layer=ON,
      label="Door 1 photos", lab=(0, 0.45, 0, 0), lw=140)
    a("p_reasm", "b", "p_store", ("t", 0.7), via=[("y", y_s3_start - 35), ("x", CX_MID + 100)], layer=OFF,
      label="Door 0 photos", lab=(0, 0.45, 0, 0), lw=140)

    a("p_store", "b", "p_reader", "t", layer=P)
    a("p_reader", "b", "p_dose", "t", layer=P)
    a("p_dose", "b", "p_rag", "t", layer=P)

    # ---------------- STAGE 4: Operator Desk & Callback Daemon ----------------
    p_desk = n("p_desk", "OPERATOR DESK (tools/photo_desk.py)\nRunning on private port 8003 (localhost only 127.0.0.1, isolated from public tunnel).\n"
               "- Operator sees case cards, photo thumbnails, modal zoom\n"
               "- Shows AI finding, matched scheme, and draft say text in caller's primary language\n"
               "- Keyboard controls: Enter approve, B not clear, Esc save, 1-6 zoom, A auto toggle",
               CX_MID, top=p_rag.bottom + 60, w=500, layer=P)

    p_auto_choice = n("p_auto_choice", "PHOTO_AUTO=true and confidence sure >= 0.4?",
                      CX_MID, top=p_desk.bottom + 50, kind="diamond", w=250, layer=P)

    p_auto_app = n("p_auto_app", "AUTO-APPROVAL (zero human delay)\nSystem automatically approves valid findings. Composes concise 3-sentence say text in caller's language. "
                   "Writes PHOTO_DIR/next_call.json with {token, lang, say, made}.",
                   CX_D1, top=p_auto_choice.bottom + 50, w=450, layer=P)

    p_manual_app = n("p_manual_app", "MANUAL OPERATOR APPROVAL\nOperator reviews finding, edits say text if needed, and presses Enter (or clicks \"Call Back\"). "
                     "If photo is blurry/unreadable, presses B (\"not clear\"). Writes next_call.json.",
                     CX_D0, top=p_auto_choice.bottom + 50, w=450, layer=P)

    y_s4_app_bottom = max(p_auto_app.bottom, p_manual_app.bottom)

    p_daemon = n("p_daemon", "AUTOMATED CALL-BACK DAEMON (photo_back.py)\n- Background worker (make photo-back) monitors next_call.json\n"
                 "- Checks line: waits until NO call is currently active\n"
                 "- Takes caller's phone number from case.json and wipes it immediately from disk (mark_called)\n"
                 "- Initiates outbound call via Twilio place_call",
                 CX_MID, top=y_s4_app_bottom + 50, w=500, layer=P)

    a("p_rag", "b", "p_desk", "t", layer=P)
    a("p_desk", "b", "p_auto_choice", "t", layer=P)
    a("p_auto_choice", "l", "p_auto_app", "t", via=[("x", CX_D1)], layer=P, label="yes (auto on)", lab=(1, 0.4, 0, 0))
    a("p_auto_choice", "r", "p_manual_app", "t", via=[("x", CX_D0)], layer=P, label="no: helper reviews", lab=(1, 0.4, 0, 0))
    a("p_auto_app", "b", "p_daemon", ("t", 0.3), via=[("y", y_s4_app_bottom + 25), ("x", CX_MID - 100)], layer=P)
    a("p_manual_app", "b", "p_daemon", ("t", 0.7), via=[("y", y_s4_app_bottom + 25), ("x", CX_MID + 100)], layer=P)

    # ---------------- STAGE 5: Call 2, Diagnosis, Context & Return ----------------
    p_call2 = n("p_call2", "CALL 2 CONNECTS TO CALLER\nTwilio rings caller's phone and connects to /stream.\n"
                "- Bypasses greeting! Opens directly with _call_back diagnosis in caller's spoken language\n"
                "- Line speaks findings and scheme details smoothly",
                CX_MID, top=p_daemon.bottom + 60, w=500, layer=P)

    p_quality = n("p_quality", "Photo was clear and identified?", CX_MID, top=p_call2.bottom + 50, kind="diamond", w=250, layer=P)

    p_bad_photo = n("p_bad_photo", "UNCLEAR PHOTO GRACEFUL RETRY\nAgent says: \"The photo was not clear enough to identify the crop/issue. "
                    "Please send a clearer, closer photo using the same link or app.\"\n"
                    "Drops bad photos, resets case to \"waiting\", link stays active.",
                    CX_D1, top=p_quality.bottom + 50, w=450, layer=P)

    p_good_photo = n("p_good_photo", "EXPLAINS DIAGNOSIS & SCHEME\nAgent speaks diagnosis (e.g. \"Leaves show signs of cotton bollworm\") "
                     "and explains benefits & application steps of matching scheme (e.g. PM Fasal Bima claims).",
                     CX_D0, top=p_quality.bottom + 50, w=450, layer=P)

    y_s5_diag_bottom = max(p_bad_photo.bottom, p_good_photo.bottom)

    p_context = n("p_context", "CONTEXT CONTINUITY (NO RE-ASKING)\nLoads Call 1 context by call_id and preserved box_vector (farmer, state, age, category).\n"
                  "Model prompt includes separate <photo_finding> block.\n"
                  "Caller is NOT re-asked facts from Call 1!",
                  CX_MID, top=y_s5_diag_bottom + 50, w=500, layer=P)

    p_loop_return = n("p_loop_return", "SEAMLESS RETURN TO DIALOG\nCall flows directly into LISTEN in the main talk loop.\n"
                      "Caller can ask follow-up questions (\"how do I apply?\", \"what papers are needed?\"), and system answers with full combined context.",
                      CX_MID, top=p_context.bottom + 50, w=500, layer=P)

    a("p_daemon", "b", "p_call2", "t", layer=P)
    a("p_call2", "b", "p_quality", "t", layer=P)
    a("p_quality", "l", "p_bad_photo", "t", via=[("x", CX_D1)], layer=P, label="no: sure < 0.4 / blurry", lab=(1, 0.75, -95, 0))
    a("p_quality", "r", "p_good_photo", "t", via=[("x", CX_D0)], layer=P, label="yes: clear", lab=(1, 0.4, 0, 0))
    a("p_bad_photo", "b", "p_context", ("t", 0.3), via=[("y", y_s5_diag_bottom + 25), ("x", CX_MID - 100)], layer=P)
    a("p_good_photo", "b", "p_context", ("t", 0.7), via=[("y", y_s5_diag_bottom + 25), ("x", CX_MID + 100)], layer=P)
    a("p_context", "b", "p_loop_return", "t", layer=P)

    # Return loop to listen via top corridor, avoiding remind
    a("p_loop_return", "l", "listen", ("t", 0.85),
      via=[("x", G_P_RET), ("y", Y_TOP_CORRIDOR + 20), ("x", listen.fx(0.85))],
      layer=P, label="Call 2 continues: caller asks follow-ups, line answers with full context",
      lab=(0, 0.5, 0, 0), lw=360)

    # Timeout End box - right exit of p_door_split
    p_expire_end = n("p_expire_end", "No photo sent in 24h: link expires, case wiped. Log saved.",
                     CX_RULES, cy=p_door_split.cy, w=380, kind="end")
    a("p_door_split", "r", "p_expire_end", "l", layer="end", label="24h timeout", lab=(0, 0.45, 0, 0), lw=140)

    # ---------------- COLUMN 7: Rules Note ----------------
    n("p_rules", "PHOTO ARCHITECTURE RULES & CONSTRAINTS\n"
      "- Privacy First: Phone number stored in case.json only; wiped immediately upon call-back or after 24h sweep; NEVER in SMS links, logs, or public web pages\n"
      "- Two-Server Architecture: Public port 8002 (photo upload & SMS ingest via tunnel), Private port 8003 (operator desk, localhost 127.0.0.1 only)\n"
      "- Async Execution: Photo reading runs in background worker thread; port 8002 web handlers never freeze\n"
      "- Rate Limits & Guards: Max 6 photos per case, max 5 MB per photo; link expires in 24 hours; repeated invalid tokens rate-limited\n"
      "- Budget Cap: Muse API capped at Rs 30/day; money guard checks ledger before API calls\n"
      "- Dose Guard: No medicinal brand names or chemical dosages generated by AI; only verified govt schemes\n"
      "- Door 0 Keypad Limit: Photos aggressively shrunk to <= 1-5 KB and sliced into at most 10 SMS pieces\n"
      "- One Caller at a Time: Automated call-back daemon waits until telephony line is idle before placing call\n"
      "- Context Preservation: Second call retains Call 1 history, log context, and answered qualification vector",
      CX_RULES, top=p_expire_end.bottom + 80, w=480, kind="note", layer=P, align="left")

    return c


def main():
    c = build_chart_4()
    errs, warns, crossings = c.check()

    path = os.path.join(HERE, NAME_4 + ".excalidraw")
    with open(path, "w") as f:
        json.dump(c.excalidraw(), f, indent=1)

    ferrs, counts = check_file(path)
    kinds = {}
    for node in c.nodes.values():
        kinds[node.kind] = kinds.get(node.kind, 0) + 1
    print(f"{NAME_4}: {len(c.nodes)} boxes {kinds}, {len(c.edges)} arrows, "
          f"{len(c.labels)} labels, {crossings} line crossings; file parts {counts}")

    for e in errs + ferrs:
        print("   ERROR", e)
    for w in warns:
        print("   warn ", w)

    svg_path = os.path.join(HERE, NAME_4 + ".svg")
    with open(svg_path, "w") as f:
        f.write(c.svg())

    png_path = os.path.join(HERE, NAME_4 + ".png")
    os.system(f"rsvg-convert -w 2600 '{svg_path}' -o '{png_path}'")
    print("PNG generated:", png_path if os.path.exists(png_path) else "Failed")

    if not errs and not ferrs:
        print("ALL CHECKS PASS")
        return 0
    else:
        print(f"{len(errs) + len(ferrs)} ERRORS")
        return 1


if __name__ == "__main__":
    sys.exit(main())
