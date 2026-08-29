#!/usr/bin/env bash
set -euo pipefail

missing=0
for tool in docker kind kubectl curl rg; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required command: $tool" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  echo "Install the missing tools, then rerun make demo-check." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but its daemon is not reachable." >&2
  exit 1
fi
echo "Demo prerequisites are available."
