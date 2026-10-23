"""Phase 0 test site (CHW-77/78): plain ERPNext v16, one fictional China shipment.

Shows the accountant how ERPNext books an import before any custom app exists:
CGNC-numbered accounts, TVA templates, an ICE field, then
PO (USD) -> receipt -> supplier invoice -> landed cost (freight, insurance, duties,
transit, local transport) -> customs TVA bill -> payments with an exchange difference
-> sales order -> delivery note -> sales invoice (TVA 20 %, amount in words) -> receipt.

All names and figures are fictional. Run inside the frappe container:
    cd /home/frappe/benches/frappe-bench/sites && PHASE0_SITE=<site> ../env/bin/python /workspace/scripts/phase0_seed.py
Each stage skips what already exists, so the script can run again after a fix.
"""

import os

import frappe
from frappe.utils import flt

SITE = os.environ.get("PHASE0_SITE", "phase0-demo.localhost")
COMPANY = "Démo Import SARL"
ABBR = "DI"
YEAR = "2026"

# Fictional exchange rates (MAD per USD).
RATE_ORDER = 10.00
RATE_PAYMENT = 10.12

DUTY_RATE = 0.10  # fictional customs duty rate on the CIF value
TPI_RATE = 0.0025  # taxe parafiscale à l'importation, part of the cost and of the TVA base
IMPORT_TVA_RATE = 0.20

SUPPLIER_CN = "Guangzhou Sweet Tools Co. (démo)"
SUPPLIER_TRANSIT = "Transit Nord SARL (démo)"
SUPPLIER_TRANSPORT = "Transports Rif SARL (démo)"
SUPPLIER_CUSTOMS = "ADII - Douane (démo)"
CUSTOMER = "Pâtisserie Les Délices (démo)"

WAREHOUSE_NAME = "Dépôt Tétouan"

# code, name, uom, weight kg per unit, purchase price USD, qty bought, selling price MAD HT, qty sold
ITEMS = [
	("DOU-1M", "Douille étoile ouverte 1M inox", "Nos", 0.008, 0.35, 2000, 9.00, 300),
	(
		"POCHE-100",
		"Poches à douille jetables (rouleau de 100)",
		"Nos",
		0.9,
		1.20,
		500,
		35.00,
		50,
	),
	("COL-ROUGE-25", "Colorant gel rouge 25 g", "Nos", 0.03, 0.80, 1000, 25.00, 120),
	("PERLES-ARG", "Perles de sucre argentées", "Kg", 1.0, 3.00, 250.5, 85.00, 12.5),
]

# Landed-cost charges in MAD. Freight and insurance are re-invoiced by the forwarder without TVA.
FREIGHT = 3200.00
INSURANCE = 400.00
TRANSIT_FEES = 1500.00  # TVA 20 %
LOCAL_TRANSPORT = 600.00  # TVA 14 %


def a(number, name):
	"""ERPNext account name for a CGNC account of the demo company."""
	return f"{number} - {name} - {ABBR}"


ACC = {
	"capital": a("1111", "Capital social"),
	"stock": a("3111", "Marchandises"),
	"customers": a("3421", "Clients"),
	"tva_recup": a("34552", "État - TVA récupérable sur charges"),
	"suppliers_mad": a("44111", "Fournisseurs - MAD"),
	"suppliers_usd": a("44112", "Fournisseurs étrangers - USD"),
	"srbnb": a("4417", "Fournisseurs - factures non parvenues"),
	"tva_facturee": a("4455", "État - TVA facturée"),
	"bank": a("5141", "Banques"),
	"cash": a("5161", "Caisses"),
	"frais_transport": a("61113", "Frais d'approche - transport et assurance"),
	"frais_douane": a("61114", "Frais d'approche - droits de douane et TPI"),
	"frais_transit": a("61115", "Frais d'approche - transit et transport local"),
	"cogs": a("61141", "Variation des stocks - coût des ventes"),
	"stock_adjustment": a("61142", "Variation des stocks - écarts d'inventaire"),
	"exchange": a("6331", "Pertes de change"),
	"round_off": a("6588", "Autres charges non courantes - arrondis"),
	"sales": a("7111", "Ventes de marchandises au Maroc"),
}

# CGNC chart, limited to the accounts this test uses: class (1 digit), rubrique (2),
# poste (3), compte (4), sous-compte (5). Leaf choices (44112, 4417, 61113-61115,
# 61141 as cost of sales) are proposals for the accountant to confirm.
CGNC_CHART = {
	"Comptes de financement permanent": {
		"account_number": "1",
		"root_type": "Equity",
		"Capitaux propres": {
			"account_number": "11",
			"Capital social ou personnel": {
				"account_number": "111",
				"Capital social": {"account_number": "1111"},
			},
		},
	},
	"Comptes d'actif circulant (hors trésorerie)": {
		"account_number": "3",
		"root_type": "Asset",
		"Stocks": {
			"account_number": "31",
			"Marchandises (groupe)": {
				"account_number": "311",
				"Marchandises": {"account_number": "3111", "account_type": "Stock"},
			},
		},
		"Créances de l'actif circulant": {
			"account_number": "34",
			"Clients et comptes rattachés": {
				"account_number": "342",
				"Clients": {"account_number": "3421", "account_type": "Receivable"},
			},
			"État - débiteur": {
				"account_number": "345",
				"État - TVA récupérable": {
					"account_number": "3455",
					"État - TVA récupérable sur charges": {"account_number": "34552", "account_type": "Tax"},
				},
			},
		},
	},
	"Comptes de passif circulant (hors trésorerie)": {
		"account_number": "4",
		"root_type": "Liability",
		"Dettes du passif circulant": {
			"account_number": "44",
			"Fournisseurs et comptes rattachés": {
				"account_number": "441",
				"Fournisseurs": {
					"account_number": "4411",
					"Fournisseurs - MAD": {"account_number": "44111", "account_type": "Payable"},
					"Fournisseurs étrangers - USD": {
						"account_number": "44112",
						"account_type": "Payable",
						"account_currency": "USD",
					},
				},
				"Fournisseurs - factures non parvenues": {
					"account_number": "4417",
					"account_type": "Stock Received But Not Billed",
				},
			},
			"État - créditeur": {
				"account_number": "445",
				"État - TVA facturée": {"account_number": "4455", "account_type": "Tax"},
			},
		},
	},
	"Comptes de trésorerie": {
		"account_number": "5",
		"root_type": "Asset",
		"Trésorerie - actif": {
			"account_number": "51",
			"Banques, TG et CP": {
				"account_number": "514",
				"Banques": {"account_number": "5141", "account_type": "Bank"},
			},
			"Caisses (groupe)": {
				"account_number": "516",
				"Caisses": {"account_number": "5161", "account_type": "Cash"},
			},
		},
	},
	"Comptes de charges": {
		"account_number": "6",
		"root_type": "Expense",
		"Charges d'exploitation": {
			"account_number": "61",
			"Achats revendus de marchandises": {
				"account_number": "611",
				"Achats de marchandises": {
					"account_number": "6111",
					"Frais d'approche - transport et assurance": {
						"account_number": "61113",
						"account_type": "Expenses Included In Valuation",
					},
					"Frais d'approche - droits de douane et TPI": {
						"account_number": "61114",
						"account_type": "Expenses Included In Valuation",
					},
					"Frais d'approche - transit et transport local": {
						"account_number": "61115",
						"account_type": "Expenses Included In Valuation",
					},
				},
				"Variation des stocks de marchandises": {
					"account_number": "6114",
					"Variation des stocks - coût des ventes": {
						"account_number": "61141",
						"account_type": "Cost of Goods Sold",
					},
					"Variation des stocks - écarts d'inventaire": {
						"account_number": "61142",
						"account_type": "Stock Adjustment",
					},
				},
			},
		},
		"Charges financières": {
			"account_number": "63",
			"Pertes de change (groupe)": {
				"account_number": "633",
				"Pertes de change": {"account_number": "6331"},
			},
		},
		"Charges non courantes": {
			"account_number": "65",
			"Autres charges non courantes": {
				"account_number": "658",
				"Autres charges non courantes - arrondis": {
					"account_number": "6588",
					"account_type": "Round Off",
				},
			},
		},
	},
	"Comptes de produits": {
		"account_number": "7",
		"root_type": "Income",
		"Produits d'exploitation": {
			"account_number": "71",
			"Ventes de marchandises": {
				"account_number": "711",
				"Ventes de marchandises au Maroc": {
					"account_number": "7111",
					"account_type": "Income Account",
				},
			},
		},
		"Produits financiers": {
			"account_number": "73",
			"Gains de change (groupe)": {
				"account_number": "733",
				"Gains de change": {"account_number": "7331"},
			},
		},
	},
}


def log(msg):
	print(f">> {msg}", flush=True)


def checkpoint(msg):
	frappe.db.commit()
	log(msg)


# --- Stage 1: setup wizard -------------------------------------------------------------


def run_setup_wizard():
	if frappe.is_setup_complete():
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	setup_complete(
		{
			"language": "English",
			"country": "Morocco",
			"timezone": "Africa/Casablanca",
			"currency": "MAD",
			"full_name": "Administrateur Démo",
			"email": "demo@demo-import.test",
			"password": "admin",
			"company_name": COMPANY,
			"company_abbr": ABBR,
			"chart_of_accounts": "Standard",
			"fy_start_date": f"{YEAR}-01-01",
			"fy_end_date": f"{YEAR}-12-31",
		}
	)
	checkpoint("setup wizard done")


def set_french():
	"""The wizard runs in English so fixture names are predictable; the users work in French."""
	settings = frappe.get_single("System Settings")
	if settings.language != "fr":
		settings.language = "fr"
		settings.save()
	for user in ("Administrator", "demo@demo-import.test"):
		if frappe.db.exists("User", user):
			frappe.db.set_value("User", user, "language", "fr")
	checkpoint("interface language set to French")


# --- Stage 2: CGNC chart and company defaults -----------------------------------------


def replace_chart():
	if frappe.db.exists("Account", ACC["stock"]):
		return
	if frappe.db.count("GL Entry", {"company": COMPANY}):
		frappe.throw("Company already has GL entries, cannot replace the chart")

	from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import (
		create_charts,
	)
	from erpnext.accounts.doctype.chart_of_accounts_importer.chart_of_accounts_importer import (
		unset_existing_data,
	)

	# Item Tax Templates from the wizard point at accounts that are about to go.
	for name in frappe.get_all("Item Tax Template", {"company": COMPANY}, pluck="name"):
		frappe.delete_doc("Item Tax Template", name, force=True, ignore_permissions=True)
	unset_existing_data(COMPANY)
	create_charts(COMPANY, custom_chart=CGNC_CHART)

	company = frappe.get_doc("Company", COMPANY)
	company.update(
		{
			"default_receivable_account": ACC["customers"],
			"default_payable_account": ACC["suppliers_mad"],
			"default_bank_account": ACC["bank"],
			"default_cash_account": ACC["cash"],
			"default_inventory_account": ACC["stock"],
			"stock_received_but_not_billed": ACC["srbnb"],
			"stock_adjustment_account": ACC["stock_adjustment"],
			"expenses_included_in_valuation": ACC["frais_transport"],
			"default_expense_account": ACC["cogs"],
			"default_income_account": ACC["sales"],
			"round_off_account": ACC["round_off"],
			"exchange_gain_loss_account": ACC["exchange"],
			"unrealized_exchange_gain_loss_account": ACC["exchange"],
			"enable_perpetual_inventory": 1,
		}
	)
	company.save()

	for mop, account in (("Cash", ACC["cash"]), ("Wire Transfer", ACC["bank"])):
		if frappe.db.exists("Mode of Payment", mop):
			doc = frappe.get_doc("Mode of Payment", mop)
			doc.set("accounts", [{"company": COMPANY, "default_account": account}])
			doc.save()
	checkpoint("CGNC chart loaded, company defaults set")


# --- Stage 3: settings, ICE, taxes, masters --------------------------------------------


def configure():
	if frappe.db.exists("Item", ITEMS[0][0]):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	frappe.db.set_single_value("Stock Settings", "valuation_method", "Moving Average")
	# Moroccan invoices are not rounded to the whole dirham.
	# Saved as a document: on_update applies the setting to the transaction defaults.
	global_defaults = frappe.get_single("Global Defaults")
	global_defaults.disable_rounded_total = 1
	global_defaults.save()
	frappe.db.set_value("Currency", "USD", "enabled", 1)
	frappe.get_doc(
		{
			"doctype": "Currency Exchange",
			"date": f"{YEAR}-09-01",
			"from_currency": "USD",
			"to_currency": "MAD",
			"exchange_rate": RATE_ORDER,
		}
	).insert()

	ice = {
		"fieldname": "ice",
		"label": "ICE",
		"fieldtype": "Data",
		"length": 15,
		"insert_after": "tax_id",
	}
	create_custom_fields(
		{
			"Company": [ice],
			"Customer": [ice],
			"Supplier": [ice],
			"Sales Invoice": [
				{
					"fieldname": "company_ice",
					"label": "ICE société",
					"fieldtype": "Data",
					"fetch_from": "company.ice",
					"read_only": 1,
					"insert_after": "company",
				},
				{
					"fieldname": "customer_ice",
					"label": "ICE client",
					"fieldtype": "Data",
					"fetch_from": "customer.ice",
					"read_only": 1,
					"insert_after": "customer_name",
				},
			],
		}
	)
	frappe.db.set_value("Company", COMPANY, "ice", "001234567000012")

	for rate in (20, 14, 10, 7):
		frappe.get_doc(
			{
				"doctype": "Sales Taxes and Charges Template",
				"title": f"TVA {rate} % - Ventes",
				"company": COMPANY,
				"is_default": int(rate == 20),
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": ACC["tva_facturee"],
						"rate": rate,
						"description": f"TVA {rate} %",
					}
				],
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Purchase Taxes and Charges Template",
				"title": f"TVA {rate} % - Achats",
				"company": COMPANY,
				"taxes": [
					{
						"category": "Total",
						"add_deduct_tax": "Add",
						"charge_type": "On Net Total",
						"account_head": ACC["tva_recup"],
						"rate": rate,
						"description": f"TVA récupérable {rate} %",
					}
				],
			}
		).insert()

	root_warehouse = frappe.db.get_value(
		"Warehouse", {"company": COMPANY, "is_group": 1, "parent_warehouse": ""}
	)
	frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": WAREHOUSE_NAME,
			"company": COMPANY,
			"parent_warehouse": root_warehouse,
		}
	).insert()
	warehouse = f"{WAREHOUSE_NAME} - {ABBR}"

	item_group_root = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ""})
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": "Articles de pâtisserie",
			"parent_item_group": item_group_root,
		}
	).insert()
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": "Frais d'importation",
			"parent_item_group": item_group_root,
		}
	).insert()

	for code, name, uom, weight, _usd, _qty_in, price, _qty_out in ITEMS:
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": "Articles de pâtisserie",
				"stock_uom": uom,
				"is_stock_item": 1,
				"weight_per_unit": weight,
				"weight_uom": "Kg",
				"item_defaults": [{"company": COMPANY, "default_warehouse": warehouse}],
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": code,
				"price_list": "Standard Selling",
				"price_list_rate": price,
			}
		).insert()

	services = [
		("FRET-MER", "Fret maritime", ACC["frais_transport"]),
		("ASSUR-TRANS", "Assurance transport", ACC["frais_transport"]),
		("DROITS-DOUANE", "Droits de douane", ACC["frais_douane"]),
		("TRANSIT", "Frais de transit et dédouanement", ACC["frais_transit"]),
		("TRANSP-LOC", "Transport local Tanger Med - Tétouan", ACC["frais_transit"]),
		("TPI", "Taxe parafiscale à l'importation (0,25 %)", ACC["frais_douane"]),
	]
	for code, name, account in services:
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": "Frais d'importation",
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"item_defaults": [{"company": COMPANY, "expense_account": account}],
			}
		).insert()

	supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0})
	for name, currency, account, ice_number in (
		(SUPPLIER_CN, "USD", ACC["suppliers_usd"], None),
		(SUPPLIER_TRANSIT, "MAD", ACC["suppliers_mad"], "002345678000034"),
		(SUPPLIER_TRANSPORT, "MAD", ACC["suppliers_mad"], "003456789000045"),
		(SUPPLIER_CUSTOMS, "MAD", ACC["suppliers_mad"], None),
	):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": supplier_group,
				"country": "China" if currency == "USD" else "Morocco",
				"default_currency": currency,
				"ice": ice_number,
				"accounts": [{"company": COMPANY, "account": account}],
			}
		).insert()

	frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": CUSTOMER,
			"customer_type": "Company",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
			"default_currency": "MAD",
			"ice": "009876543000021",
			"tax_id": "IF 12345678",
		}
	).insert()

	# Opening capital in the bank so the payments have a source of funds.
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": COMPANY,
			"posting_date": f"{YEAR}-09-01",
			"user_remark": "Apport en capital (démo)",
			"accounts": [
				{"account": ACC["bank"], "debit_in_account_currency": 100000},
				{"account": ACC["capital"], "credit_in_account_currency": 100000},
			],
		}
	)
	je.insert()
	je.submit()
	checkpoint("settings, ICE fields, TVA templates, items, parties, opening capital")


# --- Stage 4: the import ----------------------------------------------------------------


def submitted(doctype, filters):
	return frappe.db.get_value(doctype, {**filters, "docstatus": 1, "company": COMPANY})


def apply_tax_template(doc, template_doctype, title):
	"""Copy the template rows into the document (set_taxes() does not do it from a script)."""
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	name = f"{title} - {ABBR}"
	doc.taxes_and_charges = name
	doc.set("taxes", get_taxes_and_charges(template_doctype, name))


def submit(doc):
	doc.insert()
	doc.submit()
	return doc


def import_shipment():
	warehouse = f"{WAREHOUSE_NAME} - {ABBR}"
	from erpnext.buying.doctype.purchase_order.purchase_order import (
		make_purchase_receipt,
	)
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
		make_purchase_invoice,
	)

	po_name = submitted("Purchase Order", {"supplier": SUPPLIER_CN})
	if not po_name:
		po = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"company": COMPANY,
				"supplier": SUPPLIER_CN,
				"transaction_date": f"{YEAR}-09-01",
				"schedule_date": f"{YEAR}-10-01",
				"currency": "USD",
				"conversion_rate": RATE_ORDER,
				"set_warehouse": warehouse,
				"items": [
					{"item_code": code, "qty": qty, "rate": usd, "uom": uom}
					for code, _n, uom, _w, usd, qty, _p, _q in ITEMS
				],
			}
		)
		po_name = submit(po).name
		checkpoint(f"purchase order {po_name}")

	pr_name = submitted("Purchase Receipt", {"supplier": SUPPLIER_CN})
	if not pr_name:
		pr = make_purchase_receipt(po_name)
		pr.posting_date = f"{YEAR}-10-05"
		pr.set_posting_time = 1
		pr.conversion_rate = RATE_ORDER
		pr_name = submit(pr).name
		checkpoint(f"purchase receipt {pr_name}")

	pi_name = submitted("Purchase Invoice", {"supplier": SUPPLIER_CN})
	if not pi_name:
		pi = make_purchase_invoice(pr_name)
		pi.posting_date = f"{YEAR}-10-05"
		pi.set_posting_time = 1
		pi.bill_no = "GST-2026-0917"
		pi.bill_date = f"{YEAR}-09-17"
		pi.conversion_rate = RATE_ORDER
		pi_name = submit(pi).name
		checkpoint(f"supplier invoice {pi_name}")

	# Goods value in MAD, then CIF, duties and customs TVA.
	goods_mad = flt(frappe.db.get_value("Purchase Receipt", pr_name, "base_net_total"), 2)
	cif = flt(goods_mad + FREIGHT + INSURANCE, 2)
	duties = flt(cif * DUTY_RATE, 2)
	tpi = flt(cif * TPI_RATE, 2)
	import_tva = flt((cif + duties + tpi) * IMPORT_TVA_RATE, 2)

	service_bills = [
		(
			SUPPLIER_TRANSIT,
			"TN-2026-311",
			[("FRET-MER", FREIGHT), ("ASSUR-TRANS", INSURANCE)],
			None,
		),
		(
			SUPPLIER_TRANSIT,
			"TN-2026-312",
			[("TRANSIT", TRANSIT_FEES)],
			"TVA 20 % - Achats",
		),
		(
			SUPPLIER_TRANSPORT,
			"TR-2026-088",
			[("TRANSP-LOC", LOCAL_TRANSPORT)],
			"TVA 14 % - Achats",
		),
		(
			SUPPLIER_CUSTOMS,
			"DUM-2026-55120",
			[("DROITS-DOUANE", duties), ("TPI", tpi)],
			None,
		),
	]
	for supplier, bill_no, lines, tax_template in service_bills:
		if submitted("Purchase Invoice", {"supplier": supplier, "bill_no": bill_no}):
			continue
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"supplier": supplier,
				"posting_date": f"{YEAR}-10-06",
				"set_posting_time": 1,
				"bill_no": bill_no,
				"bill_date": f"{YEAR}-10-06",
				"currency": "MAD",
				"items": [{"item_code": code, "qty": 1, "rate": amount} for code, amount in lines],
			}
		)
		if supplier == SUPPLIER_CUSTOMS:
			# Import TVA is a tax row, not an item line, so TVA reports see it.
			pi.append(
				"taxes",
				{
					"category": "Total",
					"add_deduct_tax": "Add",
					"charge_type": "Actual",
					"account_head": ACC["tva_recup"],
					"tax_amount": import_tva,
					"description": "TVA à l'importation 20 %",
				},
			)
		if tax_template:
			apply_tax_template(pi, "Purchase Taxes and Charges Template", tax_template)
		submit(pi)
		checkpoint(f"service bill {bill_no} ({supplier})")

	if not submitted("Landed Cost Voucher", {}):
		lcv = frappe.get_doc(
			{
				"doctype": "Landed Cost Voucher",
				"company": COMPANY,
				"posting_date": f"{YEAR}-10-06",
				"distribute_charges_based_on": "Amount",
				"purchase_receipts": [
					{
						"receipt_document_type": "Purchase Receipt",
						"receipt_document": pr_name,
						"supplier": SUPPLIER_CN,
						"posting_date": f"{YEAR}-10-05",
						"grand_total": goods_mad,
					}
				],
				"taxes": [
					{
						"description": "Fret maritime et assurance",
						"expense_account": ACC["frais_transport"],
						"amount": FREIGHT + INSURANCE,
					},
					{
						"description": "Droits de douane et TPI",
						"expense_account": ACC["frais_douane"],
						"amount": duties + tpi,
					},
					{
						"description": "Transit, dédouanement et transport local",
						"expense_account": ACC["frais_transit"],
						"amount": TRANSIT_FEES + LOCAL_TRANSPORT,
					},
				],
			}
		)
		lcv.get_items_from_purchase_receipts()
		submit(lcv)
		frappe.db.commit()
		from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import (
			repost_entries,
		)

		repost_entries()
		checkpoint(f"landed cost voucher {lcv.name}, valuation reposted")

	log(f"goods {goods_mad} MAD, CIF {cif}, duties {duties}, TPI {tpi}, customs TVA {import_tva}")


# --- Stage 5: payments ------------------------------------------------------------------


def pay_suppliers():
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	for pi_name in frappe.get_all(
		"Purchase Invoice",
		{"company": COMPANY, "docstatus": 1, "outstanding_amount": (">", 0)},
		pluck="name",
		order_by="posting_date, name",
	):
		pe = get_payment_entry("Purchase Invoice", pi_name, bank_account=ACC["bank"])
		pe.posting_date = f"{YEAR}-10-10"
		pe.reference_no = f"VIR-{pi_name}"
		pe.reference_date = f"{YEAR}-10-10"
		if pe.paid_to_account_currency == "USD":
			pe.target_exchange_rate = RATE_PAYMENT
			pe.paid_amount = flt(pe.received_amount * RATE_PAYMENT, 2)
			pe.base_paid_amount = pe.paid_amount
			pe.set_amounts()
		submit(pe)
		checkpoint(f"payment {pe.name} for {pi_name}")


# --- Stage 6: the sale ------------------------------------------------------------------


def sell():
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	frappe.local.lang = "fr"
	warehouse = f"{WAREHOUSE_NAME} - {ABBR}"

	so_name = submitted("Sales Order", {"customer": CUSTOMER})
	if not so_name:
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"company": COMPANY,
				"customer": CUSTOMER,
				"transaction_date": f"{YEAR}-10-15",
				"delivery_date": f"{YEAR}-10-16",
				"set_warehouse": warehouse,
				"selling_price_list": "Standard Selling",
				"items": [
					{"item_code": code, "qty": qty_out, "uom": uom, "rate": price}
					for code, _n, uom, _w, _u, _qi, price, qty_out in ITEMS
				],
			}
		)
		# A scripted insert does not fetch prices or template rows, so both are set here.
		apply_tax_template(so, "Sales Taxes and Charges Template", "TVA 20 % - Ventes")
		so_name = submit(so).name
		checkpoint(f"sales order {so_name}")

	dn_name = submitted("Delivery Note", {"customer": CUSTOMER})
	if not dn_name:
		dn = make_delivery_note(so_name)
		dn.posting_date = f"{YEAR}-10-16"
		dn.set_posting_time = 1
		dn_name = submit(dn).name
		checkpoint(f"delivery note {dn_name}")

	si_name = submitted("Sales Invoice", {"customer": CUSTOMER})
	if not si_name:
		si = make_sales_invoice(dn_name)
		si.posting_date = f"{YEAR}-10-16"
		si.set_posting_time = 1
		si.due_date = f"{YEAR}-11-15"
		si_name = submit(si).name
		checkpoint(f"sales invoice {si_name}")

	if frappe.db.get_value("Sales Invoice", si_name, "outstanding_amount") > 0:
		pe = get_payment_entry("Sales Invoice", si_name, bank_account=ACC["bank"])
		pe.posting_date = f"{YEAR}-10-20"
		pe.reference_no = "CHQ-0004521"
		pe.reference_date = f"{YEAR}-10-20"
		submit(pe)
		checkpoint(f"customer payment {pe.name}")


# --- Report -----------------------------------------------------------------------------


def report():
	print("\n## GL entries by voucher\n")
	rows = frappe.get_all(
		"GL Entry",
		{"company": COMPANY, "is_cancelled": 0},
		["voucher_type", "voucher_no", "posting_date", "account", "debit", "credit"],
		order_by="posting_date, creation, voucher_no, debit desc",
	)
	current = None
	for r in rows:
		key = (r.voucher_type, r.voucher_no)
		if key != current:
			current = key
			print(f"\n### {r.voucher_type} {r.voucher_no} ({r.posting_date})")
		print(f"  {r.account:<60} D {r.debit:>12,.2f}  C {r.credit:>12,.2f}")

	print("\n## Balances\n")
	balances = frappe.db.sql(
		"""select account, sum(debit) - sum(credit) as balance from `tabGL Entry`
		where company = %s and is_cancelled = 0 group by account order by account""",
		COMPANY,
		as_dict=True,
	)
	for b in balances:
		print(f"  {b.account:<60} {b.balance:>14,.2f}")
	print(f"  {'TOTAL (doit être 0)':<60} {sum(b.balance for b in balances):>14,.2f}")

	print("\n## Stock\n")
	for code, *_ in ITEMS:
		qty, value = frappe.db.get_value("Bin", {"item_code": code}, ["actual_qty", "stock_value"]) or (0, 0)
		rate = flt(value / qty, 4) if qty else 0
		print(f"  {code:<14} qty {qty:>9,.3f}  value {value:>12,.2f}  unit cost {rate:>10,.4f}")

	si = frappe.get_doc("Sales Invoice", {"customer": CUSTOMER, "docstatus": 1})
	print("\n## Sales invoice\n")
	print(
		f"  {si.name}: HT {si.net_total:,.2f}  TVA {si.total_taxes_and_charges:,.2f}  TTC {si.grand_total:,.2f}"
	)
	print(f"  ICE société {si.company_ice}  ICE client {si.customer_ice}")
	print(f"  En lettres: {si.in_words}")


def main():
	frappe.init(site=SITE, sites_path=".")
	frappe.connect()
	frappe.set_user("Administrator")
	try:
		run_setup_wizard()
		set_french()
		replace_chart()
		configure()
		import_shipment()
		pay_suppliers()
		sell()
		report()
		# The web workers cache setup state and boot info; this script runs in its own process.
		frappe.clear_cache()
	except Exception:
		frappe.db.rollback()
		raise
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
