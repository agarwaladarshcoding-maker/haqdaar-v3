.PHONY: run sim test demo-fixture pipeline smoke

test:
	python -m pytest

run:
	python -m uvicorn haqdaar.server:app --host 0.0.0.0 --port 8000

sim:
	python -m haqdaar.sim

demo-fixture:
	@echo "demo-fixture target (implemented in Step 6)"

pipeline:
	@echo "pipeline target (implemented in Step 11)"

smoke:
	@echo "smoke target (telephony / pre-demo verification checklist)"
