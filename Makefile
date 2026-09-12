PYTHON ?= $(shell if [ -f .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)

.PHONY: run sim test demo-fixture pipeline smoke pipeline-scrape

test:
	$(PYTHON) -m pytest

run:
	$(PYTHON) -m uvicorn haqdaar.server:app --host 0.0.0.0 --port 8000

sim:
	$(PYTHON) -m haqdaar.sim

demo-fixture:
	@echo "demo-fixture target (implemented in Step 6)"

pipeline-scrape:
	$(PYTHON) -m haqdaar.data.pipeline.p1_scrape

pipeline:
	@echo "pipeline target (implemented in Step 11)"

smoke:
	@echo "smoke target (telephony / pre-demo verification checklist)"
