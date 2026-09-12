PYTHON ?= $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: run sim test demo-fixture pipeline smoke pipeline-scrape

test:
	$(PYTHON) -m pytest

run:
	$(PYTHON) -m uvicorn haqdaar.server:app --host 0.0.0.0 --port 8000

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

pipeline:
	@echo "pipeline target (implemented in Step 11)"

smoke:
	@echo "smoke target (telephony / pre-demo verification checklist)"
