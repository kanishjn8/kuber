#!/usr/bin/env bash
set -euo pipefail

kind delete cluster --name kuber
echo "Deleted kind-kuber."

