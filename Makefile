.PHONY: test evaluate demo-check demo-up demo demo-reset demo-down

PYTHON ?= uv run python

test:
	$(PYTHON) -m pytest

evaluate:
	$(PYTHON) -m judge_layer.evaluation.runner

demo-check:
	./demo_layer/scripts/check-prerequisites.sh

demo-up: demo-check
	./demo_layer/scripts/setup.sh

demo:
	$(PYTHON) -m kuber.cli demo

demo-reset:
	./demo_layer/scripts/reset.sh

demo-down:
	./demo_layer/scripts/cleanup.sh
