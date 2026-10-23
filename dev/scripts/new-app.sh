#!/usr/bin/env bash
# Runs inside the frappe container. Creates a Frappe app with `bench new-app`,
# moves it to /workspace/apps (host: MaroneERP/apps) and soft-links it back.
#
# Usage: new-app.sh <app_name> "<App Title>" "<description>"
set -euo pipefail

APP=$1
TITLE=$2
DESCRIPTION=$3
PUBLISHER="Bangicode SARL"
EMAIL="ahmedchioua@gmail.com"
LICENSE="gpl-3.0"   # provisional, see CHW-82
BENCH=/home/frappe/benches/frappe-bench
APPS_SRC=/workspace/apps

cd "$BENCH"

if [ -e "$APPS_SRC/$APP" ]; then
	echo "$APPS_SRC/$APP exists, skipping"
	exit 0
fi

# Answers, in prompt order: title, description, publisher, email, license,
# create GitHub workflow, branch name.
printf '%s\n' "$TITLE" "$DESCRIPTION" "$PUBLISHER" "$EMAIL" "$LICENSE" "y" "main" |
	bench new-app "$APP"

# The editable install points at apps/$APP, so the symlink keeps it valid.
mv "apps/$APP" "$APPS_SRC/$APP"
ln -s "$APPS_SRC/$APP" "apps/$APP"

cat >"$APPS_SRC/$APP/.gitattributes" <<'EOF'
* text=auto eol=lf
EOF
