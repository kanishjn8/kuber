.PHONY: test test-llm coverage lint typecheck quality build evaluate evaluate-summary experiment-context experiment-workers sandbox-check sandbox-build sandbox-up sandbox-run sandbox-status sandbox-reset sandbox-down

test:
	uv run --extra kubernetes pytest tests examples/reference_workload/tests

test-llm:
	uv run python -m kuber_cli.llm_diagnostic

coverage:
	uv run --extra kubernetes pytest tests examples/reference_workload/tests --cov=rules_engine --cov=agent_layer --cov=event_layer --cov=context_layer --cov=judge_layer --cov=kuber_cli --cov=kubernetes_runtime --cov=reference_workload --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .
	bash -n deploy/kind/scripts/*.sh

typecheck:
	uv run --extra kubernetes mypy rules_engine agent_layer event_layer context_layer judge_layer kubernetes_runtime kuber_cli examples/reference_workload/src/reference_workload

quality: lint typecheck coverage

build:
	uv build
	uv build --project examples/reference_workload

evaluate:
	uv run kuber evaluate

evaluate-summary:
	uv run kuber evaluate --summary-only

experiment-context:
	uv run kuber experiment-context

experiment-workers:
	uv run --extra kubernetes kuber experiment-workers

sandbox-check:
	./deploy/kind/scripts/check-prerequisites.sh

sandbox-build:
	docker build -t kuber-reference-workload:dev examples/reference_workload

sandbox-up: sandbox-check
	./deploy/kind/scripts/setup.sh

sandbox-run:
	uv run --extra kubernetes kuber optimize

sandbox-status:
	./deploy/kind/scripts/status.sh

sandbox-reset:
	./deploy/kind/scripts/reset.sh

sandbox-down:
	./deploy/kind/scripts/cleanup.sh
