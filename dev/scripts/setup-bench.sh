#!/usr/bin/env bash
# Runs inside the frappe container. Safe to run again: each step skips what exists.
#
# 1. Create the bench (Frappe version-16) and get ERPNext version-16.
# 2. Soft-link every app found in /workspace/apps into the bench.
# 3. Create generic.localhost (generic apps only) and marone.localhost (all apps).
set -euo pipefail

BRANCH=version-16
ROOT=/home/frappe/benches
BENCH=$ROOT/frappe-bench
APPS_SRC=/workspace/apps
GENERIC_APPS=(morocco_localization trade_import bangicode_brand)
TENANT_APP=marone_custom

# Docker Desktop DNS needs a few seconds after the container starts.
for _ in $(seq 1 30); do
	getent hosts github.com >/dev/null && break
	sleep 2
done
getent hosts github.com >/dev/null || { echo "DNS: cannot resolve github.com" >&2; exit 1; }

# The bench volume is created empty and owned by root on first start.
sudo chown frappe:frappe "$ROOT"
cd "$ROOT"

# A failed init can leave a Procfile behind, so test that frappe really imports.
if ! "$BENCH/env/bin/python" -c "import frappe" 2>/dev/null; then
	echo ">> bench init ($BRANCH)"
	# The virtualenv stores absolute paths, so the bench is created in place, never moved.
	rm -rf "$BENCH"
	bench init --skip-redis-config-generation --frappe-branch "$BRANCH" --python python3.14 frappe-bench
fi

cd "$BENCH"

bench set-config -g db_host mariadb
bench set-config -g redis_cache redis://redis-cache:6379
bench set-config -g redis_queue redis://redis-queue:6379
bench set-config -g redis_socketio redis://redis-queue:6379
bench set-config -g developer_mode 1

if [ ! -d apps/erpnext ]; then
	echo ">> get-app erpnext ($BRANCH)"
	bench get-app --branch "$BRANCH" erpnext
fi

# Soft-link each custom app that exists on the host.
for app in "${GENERIC_APPS[@]}" "$TENANT_APP"; do
	if [ -f "$APPS_SRC/$app/pyproject.toml" ] && [ ! -e "apps/$app" ]; then
		echo ">> soft-link $app"
		bench get-app --soft-link "$APPS_SRC/$app"
	fi
done

installed() { [ -d "apps/$1" ]; }

new_site() {
	local site=$1
	shift
	if [ ! -d "sites/$site" ]; then
		echo ">> new-site $site"
		bench new-site "$site" \
			--db-root-username root \
			--db-root-password "$DB_ROOT_PASSWORD" \
			--admin-password "$ADMIN_PASSWORD" \
			--mariadb-user-host-login-scope='%'
		bench --site "$site" set-config developer_mode 1
	fi
	for app in "$@"; do
		if installed "$app" && ! bench --site "$site" list-apps | grep -qx "$app.*"; then
			echo ">> install $app on $site"
			bench --site "$site" install-app "$app"
		fi
	done
}

# generic.localhost proves the generic apps install without the tenant app (ADR 0001).
new_site generic.localhost erpnext "${GENERIC_APPS[@]}"
new_site marone.localhost erpnext "${GENERIC_APPS[@]}" "$TENANT_APP"

bench use marone.localhost
echo ">> done. Start the server with: bench start"
bench --site generic.localhost list-apps
bench --site marone.localhost list-apps
