# bangicode-infra

Infrastructure and architecture records for the Bangicode ERPNext apps (Linear project MaroneERP).

| Path | Content |
| -- | -- |
| `docs/adr/` | Architecture decision records. Start with `0001-app-split.md`. |
| `dev/` | Local development stack (CHW-86). |

## Local development

The workspace layout is:

```
MaroneERP/
  apps/             morocco_localization, trade_import, bangicode_brand, marone_custom (one git repo each)
  bangicode-infra/  this repo
  erpnext/          upstream ERPNext version-16, read-only reference
```

Requirements: Docker Desktop and Git Bash.

1. Clone the four app repos into `MaroneERP/apps/`.
2. Run `bangicode-infra/dev/up.sh`. The first run takes 15 to 20 minutes.
3. Start the server: `docker compose -f bangicode-infra/dev/compose.yml exec frappe bash -lc "cd frappe-bench && bench start"`.
4. Open `http://marone.localhost:8000` (all apps) or `http://generic.localhost:8000` (generic apps only). Log in as `Administrator` / `admin`.

`up.sh` is safe to run again. It skips each step that is already done.

The bench lives in the Docker volume `bangicode-dev_bench`. The apps stay on the host in `MaroneERP/apps/` and are soft-linked into the bench, so you edit them with your normal tools.

## New app

```bash
docker compose -f dev/compose.yml exec -T frappe bash /workspace/scripts/new-app.sh <app_name> "<App Title>" "<description>"
python dev/scripts/apply_app_standards.py   # add the app to APPS in this script first
```

`apply_app_standards.py` writes `required_apps`, `[tool.bench.frappe-dependencies]`, the CI workflow, Dependabot, an install smoke test and `CLAUDE.md` for each app.

## CI secret

`marone_custom` CI checks out the three private generic apps. It needs a repository secret `APPS_READ_TOKEN`: a fine-grained GitHub token with read access to the contents of `morocco_localization`, `trade_import` and `bangicode_brand`.
