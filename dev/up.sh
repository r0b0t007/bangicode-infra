#!/usr/bin/env bash
# One command to get both dev sites from scratch (CHW-86).
# Run from anywhere: bangicode-infra/dev/up.sh
set -euo pipefail

# Git Bash on Windows rewrites /workspace/... into C:/Program Files/Git/workspace/...
export MSYS_NO_PATHCONV=1

cd "$(dirname "$0")"
mkdir -p ../../apps

docker compose -f compose.yml up -d --wait mariadb redis-cache redis-queue
docker compose -f compose.yml up -d frappe
docker compose -f compose.yml exec -T frappe bash /workspace/scripts/setup-bench.sh

echo
echo "Start the server:  docker compose -f $(pwd)/compose.yml exec frappe bench start"
echo "Then open:         http://marone.localhost:8000  and  http://generic.localhost:8000  (Administrator / admin)"
