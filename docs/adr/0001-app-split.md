# ADR 0001: Split code into generic apps and one tenant app

- Status: Accepted (2026-10-23)
- Date: 2026-10-23
- Linear: CHW-83 (milestone M1)
- Decider: Ahmed Chioua (Bangicode SARL)

## Context

Bangicode builds ERPNext v16 for MarOne Professional. Bangicode also wants to sell the same work to other Moroccan importers and distributors. The Moroccan localization and the import features are the parts with resale value.

If MarOne values (company name, ICE, prices, logo, roles) get into this code, Bangicode cannot sell it again without a cleanup. The cleanup gets more expensive with each month of work. The split must be fixed before the first line of app code.

ERPNext v16 gives these extension points, so a custom app does not need to change core code:

- `hooks.py`: `doc_events`, `extend_doctype_class`, `override_whitelisted_methods`, `fixtures`, `required_apps`.
- Custom Fields and Property Setters, exported as fixtures.
- New DocTypes, reports, print formats and workspaces inside the app.

ERPNext uses `extend_doctype_class` itself in v16 (`erpnext/hooks.py`, line 82).

## Decision

Bangicode uses four Frappe apps. Each app has its own git repository.

| App | Contents | Requires | Owner |
| -- | -- | -- | -- |
| `morocco_localization` | CGNC chart with account numbers, TVA templates, ICE/IF/RC/TP/CNSS fields, art. 145 print formats, amount in words, SIMPL-TVA export, payment delays (law 69-21), cash rules, cheque and LCN portfolio | `erpnext` | Bangicode, resold |
| `trade_import` | Dossier Importation, landed-cost split by weight, volume and percentage, import reports, supplier credit limit, cash count | `erpnext` | Bangicode, resold |
| `bangicode_brand` | Theme, logos, app name, login page, email and letter head templates. All values come from a settings DocType. | `frappe` | Bangicode, resold |
| `marone_custom` | Fixtures and settings values only: item groups, price lists, warehouses, roles, letter head, values for the settings DocTypes of the three generic apps | all three generic apps | MarOne |

The rest of this ADR calls the first three apps the "generic apps" and `marone_custom` the "tenant app".

### Dependency rules

1. A generic app never imports from, depends on, or names the tenant app.
2. A generic app never depends on another generic app. Each one installs alone on a plain ERPNext site.
3. If two generic apps must work together, the code checks `"<app>" in frappe.get_installed_apps()` first. Example: `morocco_localization` adds customs TVA handling to a Dossier Importation only when `trade_import` is installed.
4. The tenant app lists all the apps it configures in `required_apps`.
5. No app changes files in Frappe or ERPNext.

### Content rules

1. Generic apps contain no client name, client identifier, client price, client address or client logo. This applies to code, fixtures, tests and comments.
2. A value that changes between clients goes in a settings DocType of the generic app. The tenant app sets the value as a fixture.
3. A feature that some clients do not want gets a check field in the settings DocType. The default is the safe choice for a new client.
4. Generic apps ship with French labels wrapped in `_()` or `__()`. Arabic and English come from translation files.
5. Test data in generic apps is fictional.

CHW-87 defines the settings DocTypes, the feature flags and the fixture format in detail.

### Where a new item goes

Ask these questions in order. Stop at the first "yes".

1. Is it a MarOne value or a MarOne-only choice? Put it in `marone_custom`.
2. Is it required by Moroccan law or Moroccan accounting practice? Put it in `morocco_localization`.
3. Is it about importing goods or about trade between suppliers and customers? Put it in `trade_import`.
4. Is it about how the product looks or what it is called? Put it in `bangicode_brand`.
5. Else, write a follow-up ADR before you add a fifth app.

## How we check the rules

1. CI installs each generic app alone on a fresh v16 site and runs its tests (CHW-84).
2. The dev environment has a site `generic.localhost` with the generic apps only (CHW-86). If a generic app needs the tenant app, this site fails to install.
3. A pre-commit check in each generic app fails if the code contains a word from a deny list (for example `marone`, the client ICE, the client domain). The deny list lives in `bangicode-infra`, not in the generic apps.
4. The `frappe-reviewer` subagent checks the dependency and content rules on each PR.

## Options we did not choose

- **One app for everything, with feature flags.** It is less work at the start. But MarOne values and generic code share one repository, and a resale needs a fork. Rejected.
- **A fork of ERPNext.** Each ERPNext update then needs a merge. ERPNext v16 publishes several releases each month (16.52.1 on 2026-10-22). Rejected.
- **One app per client that contains all the code.** The Moroccan work then gets copied for each client, and bug fixes do not reach the other clients. Rejected.
- **Customization in the database only (Custom Fields, Server Scripts in the Desk).** It cannot be reviewed, tested or installed on a second site. Rejected. A Desk change is allowed only if it is exported as a fixture in the right app.

## Consequences

Good:

- Bangicode can install the generic apps for a second client without a cleanup.
- An ERPNext update needs no merge. Only the extension points can break, and CI finds the break.
- Each app has a clear owner. The contract can name the apps that MarOne owns and the apps that Bangicode keeps.

Bad:

- Four repositories, four CI pipelines and four release cycles. CHW-126 handles versions and changelogs.
- Each value that changes between clients needs a settings field. This costs time at the start.
- The rule against dependencies between generic apps adds `get_installed_apps()` checks in the places where two generic apps meet.

## Open points

1. **License.** ERPNext and Frappe use GPL-3. An app that imports `frappe` or `erpnext` is probably a derived work. Thus the generic apps may need a GPL-compatible license, and clients may get the right to share the code. This affects the resale model: Bangicode sells setup, support and updates, not closed code. CHW-82 must confirm this before the first sale to a second client.
2. **Trademark.** `bangicode_brand` replaces the Frappe and ERPNext names in the UI. CHW-82 must check the Frappe trademark policy for this.
3. **App names.** The four names are final for now. A rename after the first release needs a migration patch on each site.
