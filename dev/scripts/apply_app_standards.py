"""Apply the Bangicode app standards (CHW-84, ADR 0001) to the apps in MaroneERP/apps.

Run on the host after `new-app.sh`:  python dev/scripts/apply_app_standards.py
Safe to run again: every file is rewritten from the same template.
"""

import json
import re
import sys
from pathlib import Path

GITHUB_OWNER = "r0b0t007"
FRAPPE_BRANCH = "version-16"
FRAPPE_RANGE = ">=16.50.0,<17.0.0"
ERPNEXT_RANGE = ">=16.52.0,<17.0.0"

# required_apps per ADR 0001. Generic apps never list each other or the tenant app.
APPS = {
    "morocco_localization": {"requires": ["erpnext"], "kind": "generic"},
    "trade_import": {"requires": ["erpnext"], "kind": "generic"},
    "bangicode_brand": {"requires": [], "kind": "generic"},
    "marone_custom": {
        "requires": [
            "erpnext",
            "morocco_localization",
            "trade_import",
            "bangicode_brand",
        ],
        "kind": "tenant",
    },
}

APPS_DIR = Path(__file__).resolve().parents[3] / "apps"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def set_required_apps(app: str, requires: list[str]) -> None:
    hooks = APPS_DIR / app / app / "hooks.py"
    text = hooks.read_text(encoding="utf-8")
    line = f"required_apps = {json.dumps(requires)}"
    text = re.sub(r"^#? ?required_apps = .*$", line, text, count=1, flags=re.M)
    write(hooks, text)


def set_frappe_dependencies(app: str, requires: list[str]) -> None:
    pyproject = APPS_DIR / app / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = re.sub(
        r"\n\[tool\.bench\.frappe-dependencies\]\n(?:[^\[\n].*\n)*", "\n", text
    )
    block = f'\n[tool.bench.frappe-dependencies]\nfrappe = "{FRAPPE_RANGE}"\n'
    if "erpnext" in requires:
        block += f'erpnext = "{ERPNEXT_RANGE}"\n'
    text = text.replace("\n[build-system]", block + "\n[build-system]", 1)
    write(pyproject, text)


def ci_workflow(app: str, requires: list[str]) -> str:
    private_deps = [a for a in requires if a in APPS]
    checkout_deps = "".join(
        f"""
      - name: Checkout {dep}
        uses: actions/checkout@v6
        with:
          repository: {GITHUB_OWNER}/{dep}
          path: apps/{dep}
          token: ${{{{ secrets.APPS_READ_TOKEN }}}}
"""
        for dep in private_deps
    )
    get_erpnext = (
        f"          bench get-app --branch {FRAPPE_BRANCH} erpnext\n"
        if "erpnext" in requires
        else ""
    )
    get_deps = "".join(
        f"          bench get-app {dep} $GITHUB_WORKSPACE/apps/{dep}\n"
        for dep in private_deps
    )
    return f"""name: CI

on:
  push:
    branches:
      - main
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-{app}-${{{{ github.event.number || github.ref }}}}
  cancel-in-progress: true

jobs:
  tests:
    runs-on: ubuntu-latest
    name: Server tests ({FRAPPE_BRANCH})

    services:
      redis-cache:
        image: redis:8-alpine
        ports:
          - 13000:6379
      redis-queue:
        image: redis:8-alpine
        ports:
          - 11000:6379
      mariadb:
        image: mariadb:11.8
        env:
          MYSQL_ROOT_PASSWORD: root
        ports:
          - 3306:3306
        options: --health-cmd="healthcheck.sh --connect --innodb_initialized" --health-interval=5s --health-timeout=2s --health-retries=10

    steps:
      - name: Checkout {app}
        uses: actions/checkout@v6
        with:
          path: apps/{app}
{checkout_deps}
      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.14'

      - name: Setup Node
        uses: actions/setup-node@v6
        with:
          node-version: 24

      - name: Install MariaDB client
        run: |
          sudo apt-get update
          sudo apt-get install -y mariadb-client

      - name: Setup bench
        run: |
          pip install frappe-bench
          bench init --skip-redis-config-generation --skip-assets --frappe-branch {FRAPPE_BRANCH} --python "$(which python)" ~/frappe-bench

      - name: Install apps
        working-directory: /home/runner/frappe-bench
        run: |
{get_erpnext}{get_deps}          bench get-app {app} $GITHUB_WORKSPACE/apps/{app}
          bench setup requirements --dev
          bench new-site --db-root-password root --admin-password admin --mariadb-user-host-login-scope='%' test_site
          bench --site test_site install-app {app}
        env:
          CI: 'Yes'

      - name: Run tests
        working-directory: /home/runner/frappe-bench
        run: |
          bench --site test_site set-config allow_tests true
          bench --site test_site run-tests --app {app}
        env:
          TYPE: server
"""


DEPENDABOT = """version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
"""


def smoke_test(app: str, requires: list[str]) -> str:
    return f'''import frappe
from frappe.tests import IntegrationTestCase


class TestInstall(IntegrationTestCase):
	def test_app_is_installed(self):
		self.assertIn("{app}", frappe.get_installed_apps())

	def test_required_apps_are_installed(self):
		installed = frappe.get_installed_apps()
		for app in {json.dumps(requires)}:
			self.assertIn(app, installed)
'''


GENERIC_RULES = """- This is a **generic** app (ADR 0001). Never import, name or depend on a tenant app (`marone_custom`) or on another generic app. Where two generic apps meet, check `"<app>" in frappe.get_installed_apps()` first.
- No client name, identifier (ICE, IF, RC), price, address or logo anywhere: code, fixtures, tests, comments. Client values come from this app's settings DocType."""

TENANT_RULES = """- This is the **tenant** app for one client (ADR 0001). It holds fixtures and settings values only: no business logic. Logic goes in a generic app.
- No real client data in tests. Use the fictional demo dataset."""


def claude_md(app: str, cfg: dict) -> str:
    title = app.replace("_", " ").title()
    requires = ", ".join(f"`{a}`" for a in cfg["requires"]) or "`frappe` only"
    rules = GENERIC_RULES if cfg["kind"] == "generic" else TENANT_RULES
    return f"""# {app}

{title}: a Frappe app for ERPNext {FRAPPE_BRANCH[-2:]} by Bangicode SARL. Part of the MaroneERP white-label build (Linear project MaroneERP, team CHW).

- Requires: {requires} (`required_apps` in `hooks.py`).
- Architecture: `bangicode-infra/docs/adr/0001-app-split.md`.
- Reference the Linear issue (`CHW-123`) in branch names, commits and PRs.

## Commands (inside the dev container, `bangicode-infra/dev/`)

```bash
bench --site marone.localhost run-tests --app {app}
bench --site marone.localhost migrate
bench --site marone.localhost export-fixtures --app {app}
pre-commit run --all-files
```

## Rules

{rules}
- No edits to Frappe or ERPNext. Use `hooks.py` (`doc_events`, `extend_doctype_class`, overrides), Custom Fields and Property Setters.
- Every Desk customization is exported to this app's fixtures.
- User-facing labels in French, wrapped in `_()` / `__()`.
- Money: `flt(value, precision)` with the field precision. Submitted documents are cancelled and amended, never deleted.
- Never list `frappe` or `erpnext` in `[project] dependencies`. Use `[tool.bench.frappe-dependencies]`.

## Done

Tests pass on a `*.localhost` site, fixtures exported, `frappe-reviewer` run on the diff (plus `accounting-checker` for GL, TVA, landed cost, valuation or currency changes).
"""


def main() -> None:
    for app, cfg in APPS.items():
        root = APPS_DIR / app
        if not (root / "pyproject.toml").exists():
            sys.exit(f"missing app: {root}")
        set_required_apps(app, cfg["requires"])
        set_frappe_dependencies(app, cfg["requires"])
        write(
            root / ".github" / "workflows" / "ci.yml", ci_workflow(app, cfg["requires"])
        )
        write(root / ".github" / "dependabot.yml", DEPENDABOT)
        write(root / app / "tests" / "__init__.py", "")
        write(
            root / app / "tests" / "test_install.py", smoke_test(app, cfg["requires"])
        )
        write(root / "CLAUDE.md", claude_md(app, cfg))
        print(f"applied: {app}")


if __name__ == "__main__":
    main()
