PYTHON ?= $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: run call calls sim test demo-fixture pipeline smoke pipeline-scrape pipeline-extract pipeline-cards pipeline-translate backup call-me

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
	$(PYTHON) -m haqdaar.sim

# T17 §4: a whole call against the four fakes, printing the LOG. One run per
# keypad-only persona, so an interface break shows up on day one, not day nine.
# Log.open appends, and these call ids are fixed, so clear the demo logs first.
demo-fixture:
	@rm -rf logs/demo
	@for p in p1 p2 p3 widened; do \
		$(PYTHON) -m haqdaar.sim --persona $$p --canned --call-id demo_$$p --logs-dir logs/demo || exit 1; \
	done

pipeline-scrape:
	$(PYTHON) -m haqdaar.data.pipeline.p1_scrape

pipeline-extract:
	$(PYTHON) -m haqdaar.data.pipeline.p2_derive

pipeline-cards:
	$(PYTHON) -m haqdaar.data.pipeline.p3_cards

# Hindi and Marathi via Sarvam Translate (D4). Cached: a second run costs nothing.
pipeline-translate:
	$(PYTHON) -m haqdaar.data.pipeline.p4_translate


pipeline:
	@echo "pipeline target (implemented in Step 11)"

smoke:
	@echo "smoke target (telephony / pre-demo verification checklist)"
