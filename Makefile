PYTHON ?= $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: sms-door sms-try run call calls calls-ui keypad-ui photo-desk photo-back full full-stop sim test stress demo-fixture pipeline smoke pipeline-discover pipeline-scrape pipeline-extract pipeline-cards pipeline-translate pipeline-gates lines-sheet cards-sheet pipeline-texts pipeline-cost render listen listen-cards pace-samples snapshot backup call-me mac-call ear-check model-bakeoff muse-status muse-block muse-unblock barge-eval log-text stage-check door-a-check qa-check qa-router-check talk-eval talk-questions

test:
	$(PYTHON) -m pytest

# Copy of all pipeline data (raw HTML included; HTML is not in git) to ~/haqdaar-backup/.
backup:
	@mkdir -p $(HOME)/haqdaar-backup
	tar czf $(HOME)/haqdaar-backup/data_cache-$$(date +%Y%m%d-%H%M%S).tgz data_cache
	@ls -lh $(HOME)/haqdaar-backup | tail -1

# Everything the server prints also goes to logs/server.log (Claude reads it).
# Starts the cloudflared tunnel and points the number at it. Backup: TUNNEL=ngrok make run
# Plan 5.3: tools.keep_running starts the server again if it dies. Ctrl-C stops it for good.
run:
	@mkdir -p logs
	@$(PYTHON) -m tools.tunnel | tee -a logs/server.log
	NGROK_DOMAIN=$$($(PYTHON) -m tools.tunnel --host) PYTHONUNBUFFERED=1 $(PYTHON) -m tools.keep_running $(PYTHON) -m uvicorn haqdaar.server:app --host 127.0.0.1 --port 8000 2>&1 | tee -a logs/server.log

# Last calls on the phone line, with any warnings the provider logged.
calls:
	$(PYTHON) -m tools.calls

# 5 Oct: the line's own sound record of a call placed with CALL_RECORD=true (newest, or ID=CA...).
# Saves it under logs/recordings/ and says where the sound has holes on our side and the caller's.
recording:
	$(PYTHON) -m tools.recording $(ID)

# The call page: each call as a back and forth with timings. This computer only (port 8001).
calls-ui:
	$(PYTHON) -m tools.call_viewer $(ARGS)

# Keypad web client: 240x320 QVGA offline feature phone simulator (port 8080).
keypad-ui:
	$(PYTHON) -m http.server 8080 --directory keypad_app

photo-desk:
	$(PYTHON) -m tools.photo_desk

# The SMS photo door, to try on this laptop (ports 8012 / 8013, so a desk already on 8002 / 8003 is left alone).
# Terminal 1: make sms-door     Terminal 2: make sms-try PHOTOS="a.jpg b.jpg"   then open http://127.0.0.1:8013
# Muse is the reader when MUSE_API_KEY is set (a few paise a case): run make muse-status first. PHOTO_READER=stand-in costs nothing.
sms-door:
	SMS_DOOR=true PHOTO_PORT=8012 DESK_PORT=8013 $(PYTHON) -m tools.photo_desk

sms-try:
	PHOTO_PORT=8012 DESK_PORT=8013 $(PYTHON) -m tools.sms_try $(PHOTOS)

# Phase 4: rings the caller back when a photo answer is ready (needs PHOTO_BACK_URL).
photo-back:
	$(PYTHON) -m tools.photo_back $(ARGS)

# Backup: ring your phone (CALL_ME_NUMBER in .env, or TO=+91...). Needs make run.
# Uses the live tunnel; HOST=<address> to aim at another server.
call:
	NGROK_DOMAIN=$${HOST:-$$($(PYTHON) -m tools.tunnel --host)} $(PYTHON) -m tools.call_me $(TO)

# One command: tunnel + haqdaar.server + rings your phone (CALL_ME_NUMBER). NOCALL=1 skips the ring.
# Asks before it moves the phone number off another work folder (MOVE_NUMBER=1 says yes).
# Times tiny requests to the tunnel, Sarvam and Groq first; a weak net means no ring (WEAK_OK=1 rings anyway).
call-me:
	caffeinate -dimsu $(PYTHON) -m tools.run_demo

# 5 Oct: talk to the system on this Mac (mic and speakers), no phone, no Twilio. Use headphones. PORT=8001 by default.
mac-call:
	$(PYTHON) -m tools.mac_call --serve --port $(or $(PORT),8001)

# Everything at once for a Mac call: the photo desk (8002 / 8003, SMS door on) and the phone page (8080) are
# started if they are not up, then the call. They stay up after the call, so the photo can come in and the
# call-back comes by itself: after a call that sent a photo link the command stays, waits for the photo's answer
# (no clock: photo sent -> read -> answer ready; BACK_WAIT=seconds puts a limit) and at once starts the call-back on this Mac. A real phone number is rung by the watcher (photo-back), which is
# Cut-in is on (6 Oct) when the sound goes to headphones; on open speakers it stays off by itself. CUT=0 turns it off.
# started too when PHOTO_BACK_URL is set. `make full-stop` stops them. Logs: logs/photo-desk.log, logs/keypad-ui.log.
full:
	@mkdir -p logs; \
	lsof -ti tcp:8002 >/dev/null || { SMS_DOOR=true nohup $(PYTHON) -m tools.photo_desk > logs/photo-desk.log 2>&1 & echo "started the photo desk  (page 8002, desk http://127.0.0.1:8003)"; }; \
	lsof -ti tcp:8080 >/dev/null || { nohup $(PYTHON) -m http.server 8080 --directory keypad_app > logs/keypad-ui.log 2>&1 & echo "started the phone page  (8080)"; }; \
	[ -z "$$(grep -E '^PHOTO_BACK_URL=.+' .env 2>/dev/null)" ] || pgrep -f "tools.photo_back" >/dev/null || { nohup $(PYTHON) -m tools.photo_back > logs/photo-back.log 2>&1 & echo "started the call-back watcher  (logs/photo-back.log)"; }; \
	sleep 2; \
	lsof -ti tcp:8002 >/dev/null || echo "!! the photo desk did not start: see logs/photo-desk.log"; \
	lsof -ti tcp:8080 >/dev/null || echo "!! the phone page did not start: see logs/keypad-ui.log"; \
	$(PYTHON) -m tools.mac_call --serve $(if $(filter 0,$(CUT)),,--cut-in) --back --back-wait $(or $(BACK_WAIT),0) --port $(or $(PORT),8001)

full-stop:
	@pkill -f "tools.photo_desk" && echo "photo desk stopped" || echo "photo desk was not running"; \
	pkill -f "http.server 8080 --directory keypad_app" && echo "phone page stopped" || echo "phone page was not running"; \
	pkill -f "tools.photo_back" && echo "call-back watcher stopped" || echo "call-back watcher was not running"

# 5 Oct: run a few minutes before a demo call. Says what is ready and what is not. Places no call.
stage-check:
	$(PYTHON) -m tools.stage_check

sim:
	$(PYTHON) -m haqdaar.sim $(if $(SNAP),--snapshot $(SNAP),) $(if $(KEYS),--keys "$(KEYS)",)

# T17 §4: a whole call against the four fakes, printing the LOG. One run per
# keypad-only persona, so an interface break shows up on day one, not day nine.
# Log.open appends, and these call ids are fixed, so clear the demo logs first.
demo-fixture:
	@rm -rf logs/demo
	@for p in p1 p2 p3 widened; do \
		$(PYTHON) -m haqdaar.sim --persona $$p --canned --call-id demo_$$p --logs-dir logs/demo || exit 1; \
	done

# Plan 3.1: every central scheme on myscheme -> data_cache/derived/candidates.csv (free).
pipeline-discover:
	$(PYTHON) -m haqdaar.data.pipeline.p0_discover

# A failed fetch deletes a scheme's saved pages, so copy data_cache first.
pipeline-scrape: backup
	$(PYTHON) -m haqdaar.data.pipeline.p1_scrape

pipeline-extract:
	$(PYTHON) -m haqdaar.data.pipeline.p2_derive

pipeline-cards:
	$(PYTHON) -m haqdaar.data.pipeline.p3_cards

# Hindi and Marathi via Sarvam Translate (D4). Cached: a second run costs nothing.
pipeline-translate:
	$(PYTHON) -m haqdaar.data.pipeline.p4_translate

# The five gates (D5). Free and offline: it only reads what p2/p3/p4 already wrote.
pipeline-gates:
	$(PYTHON) -m haqdaar.data.pipeline.p5_gates

# The fixed lines as a sheet to correct by hand. Free and offline.
lines-sheet:
	$(PYTHON) -m tools.lines_sheet

# Step 3.7: 20 sampled cards review sheet. Free and offline.
cards-sheet:
	$(PYTHON) -m tools.cards_sheet

# What the call can say, and what is still missing. Free and offline.
pipeline-texts:
	$(PYTHON) -m haqdaar.data.pipeline.texts


# The whole pipeline: p1 (only with RESCRAPE=1) -> p2 -> p3 -> p4 -> p5 -> p6.
# Paid steps do not run without YES=1; without it they are skipped and say so.
#   make pipeline              # free steps only
#   make pipeline YES=1        # allow Groq and Sarvam
#   make pipeline YES=1 RESCRAPE=1
pipeline:
	$(PYTHON) -m haqdaar.data.pipeline.run_all $(if $(YES),--yes,) $(if $(RESCRAPE),--rescrape,)

# What has been spent so far, from the two usage ledgers. Runs nothing.
pipeline-cost:
	$(PYTHON) -m haqdaar.data.pipeline.run_all --cost

# Plan 5.3: the checklist before a real call. Checks what it can offline, prints the rest.
smoke:
	@$(PYTHON) -m tools.smoke

# Muse money guard: ₹30 a day. Free; calls nothing. `make muse-block` shuts Muse for today.
muse-status:
	@$(PYTHON) -m tools.muse_guard
muse-block:
	@$(PYTHON) -m tools.muse_guard block
muse-unblock:
	@$(PYTHON) -m tools.muse_guard unblock

# Plan 2.1: real voice for every text. Without YES=1 it only counts what is missing.
# Note: without YES checks snapshots/CURRENT only, but YES=1 without SNAP renders all schemes (scope mismatch: 'missing: 0' applies to CURRENT snapshot, not full corpus).
render:
	$(PYTHON) -m haqdaar.audio.render $(if $(YES),--yes,) $(if $(SNAP),--snapshot $(SNAP),$(if $(YES),,--snapshot snapshots/CURRENT))

# make listen L=mr N=5   (N=lines plays every fixed line)
listen:
	$(PYTHON) -m tools.listen $(L) $(N)

# Step 3.7: listen to N card-chunk clips in language L from audio-ready snapshot schemes
# make listen-cards L=hi N=2
listen-cards:
	$(PYTHON) -m tools.listen cards $(L) $(N)

# Step 7.7a: same lines at three speeds in scratch/pace-samples/ (no API); make pace-samples
pace-samples:
	$(PYTHON) -m tools.pace_samples

# Plan 2.3: build the real snapshot from the audio-ready schemes and flip snapshots/CURRENT to it.
snapshot:
	$(PYTHON) -m haqdaar.data.pipeline.p6_snapshot

# One call's log as short English text: make log-text ID=<call id>
log-text:
	$(PYTHON) -m tools.log_text $(ID)

# Plan 3.6: random keypad callers on the real snapshot; 0 crashes and 0 truth failures.
stress:
	$(PYTHON) -m tools.stress -n $(or $(N),1000) --seed $(or $(SEED),1)

# Step 4.1: transcribe 3 sentences x en/hi/mr against fixtures (or custom audio)
# NOTE: offline by default (zero API spend); ARGS=--live spends Sarvam/Groq budget.
ear-check:
	$(PYTHON) -m tools.ear_check $(ARGS)

# Step 4.2: 30-utterance model client + span guard bake-off
# NOTE: defaults to offline faked HTTP (zero API spend); use ARGS=--live for owner live run.
model-bakeoff:
	$(PYTHON) -m tools.model_bakeoff $(ARGS)

# Step 4.3: Door A offline top-1 accuracy check across 90 utterances (3 forms × 30 schemes)
door-a-check:
	$(PYTHON) -m tools.door_a_check $(ARGS)


# Step 7.1: live check of the answer step, 15 questions (Groq; with ENGLISH_PIPE=true also a little Sarvam)
# QA_ENABLED=true make qa-check ; QA_ENABLED=true ENGLISH_PIPE=true make qa-check
qa-check:
	$(PYTHON) -m tools.qa_check $(ARGS)

# Step 7.1: live check of the router's sorting rules, 50 cases, right/wrong per model (Groq)
qa-router-check:
	$(PYTHON) -m tools.model_bakeoff --router-check $(ARGS)

# Step 7.9: cut-in scorecard on a virtual clock. ARGS=--quick for a small sample;
# ARGS="--show keys:voice_qa --at 14:600 --kind cough_long" prints one call.
barge-eval:
	$(PYTHON) -m tools.barge_eval $(ARGS)

# Step 7.14 (B6): scripted TALK calls on the same rig (no network, no money): side talk, cut-in, "hmm",
# noise, a key, a hang-up at every place the agent speaks, with the cut-in gate off and on.
talk-eval:
	$(PYTHON) -m tools.talk_eval $(ARGS)

# Step 7.14 (B6): 40 real questions through the real model, per model in TALK_MODELS (Groq only; ~25 min).
talk-questions:
	@if [ "$(YES)" != "1" ]; then echo "talk-questions spends about 120,000 Groq tokens a model (the day limit is 200,000). Run: make talk-questions YES=1"; exit 1; fi
	$(PYTHON) -m tools.talk_questions --questions $(ARGS)
