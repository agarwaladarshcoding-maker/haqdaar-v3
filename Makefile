PYTHON ?= $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: run call calls sim test stress demo-fixture pipeline smoke pipeline-discover pipeline-scrape pipeline-extract pipeline-cards pipeline-translate pipeline-gates lines-sheet pipeline-texts pipeline-cost render listen snapshot backup call-me

test:
	$(PYTHON) -m pytest

# Copy of all pipeline data (raw HTML included; HTML is not in git) to ~/haqdaar-backup/.
backup:
	@mkdir -p $(HOME)/haqdaar-backup
	tar czf $(HOME)/haqdaar-backup/data_cache-$$(date +%Y%m%d-%H%M%S).tgz data_cache
	@ls -lh $(HOME)/haqdaar-backup | tail -1

# Everything the server prints also goes to logs/server.log (Claude reads it).
# Starts the cloudflared tunnel and points the number at it. Backup: TUNNEL=ngrok make run
run:
	@mkdir -p logs
	@$(PYTHON) -m tools.tunnel | tee -a logs/server.log
	NGROK_DOMAIN=$$($(PYTHON) -m tools.tunnel --host) PYTHONUNBUFFERED=1 $(PYTHON) -m uvicorn haqdaar.server:app --host 0.0.0.0 --port 8000 2>&1 | tee -a logs/server.log

# Last calls on the phone line, with any warnings the provider logged.
calls:
	$(PYTHON) -m tools.calls

# Backup: ring your phone (CALL_ME_NUMBER in .env, or TO=+91...). Needs make run.
# Uses the live tunnel; HOST=<address> to aim at another server.
call:
	NGROK_DOMAIN=$${HOST:-$$($(PYTHON) -m tools.tunnel --host)} $(PYTHON) -m tools.call_me $(TO)

# One command: tunnel + haqdaar.server + rings your phone (CALL_ME_NUMBER). NOCALL=1 skips the ring.
call-me:
	caffeinate -dimsu $(PYTHON) -m tools.run_demo

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

pipeline-scrape:
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

smoke:
	@echo "smoke target (telephony / pre-demo verification checklist)"

# Plan 2.1: real voice for every text. Without YES=1 it only counts what is missing.
render:
	$(PYTHON) -m haqdaar.audio.render $(if $(YES),--yes,)

# make listen L=mr N=5   (N=lines plays every fixed line)
listen:
	$(PYTHON) -m tools.listen $(L) $(N)

# Plan 2.3: build the real snapshot from the 12 schemes and flip snapshots/CURRENT to it.
snapshot:
	$(PYTHON) -m haqdaar.data.pipeline.p6_snapshot

# Plan 3.6: random keypad callers on the real snapshot; 0 crashes and 0 truth failures.
stress:
	$(PYTHON) -m tools.stress -n $(or $(N),1000) --seed $(or $(SEED),1)
