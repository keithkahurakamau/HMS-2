"""Accounting reference-data seed: base currency, settings, default CoA,
and the default ledger mappings.

Why this exists (TENANT-DRIFT-003): the alembic accounting migrations seed
all of this, but legacy-bootstrapped tenants were built with
``Base.metadata.create_all`` and *stamped* at head — the data seeds never
ran. Such tenants have empty ``acc_accounts`` / ``acc_ledger_mappings``, so
``post_from_event`` skips every payment ("no mapping configured") and the
transaction log stays empty forever. Tenant provisioning had the same gap.

This module repeats those seeds idempotently (WHERE NOT EXISTS, keyed on
account code / source_key / currency code) so migrate_all_tenants can
converge every tenant on each deploy. Hospitals that renamed accounts or
re-pointed mappings are never disturbed.

The data below is a faithful copy of the seeds in:
  * d2f4a91c5e83_accounting_phase1.py   (currency, settings, DEFAULT_COA)
  * e3a91c2d7f48_accounting_phase3_config.py (DEFAULT_MAPPINGS)
  * f4b8e2c91a36_accounting_phase5_debtors.py (billing.deposit.applied)
  * a3f9c1d8b240_accounting_budgets_notes_allocation.py (…bulk_allocated)
Alembic history is frozen; future additions belong HERE plus a new
migration for already-converged tenants.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

LOG = logging.getLogger(__name__)

# (code, name, type, parent_code, is_postable)
DEFAULT_COA: list[tuple[str, str, str, str | None, bool]] = [
    ("1000", "Assets",                        "Asset",     None,   False),
    ("1100", "Current Assets",                "Asset",     "1000", False),
    ("1110", "Cash on Hand",                  "Asset",     "1100", True),
    ("1120", "Bank Accounts",                 "Asset",     "1100", True),
    ("1130", "Mobile Money (M-Pesa)",         "Asset",     "1100", True),
    ("1140", "Accounts Receivable",           "Asset",     "1100", True),
    ("1150", "Insurance Receivable",          "Asset",     "1100", True),
    ("1160", "Inventory — Pharmacy",          "Asset",     "1100", True),
    ("1170", "Inventory — Consumables",       "Asset",     "1100", True),
    ("1180", "Prepayments",                   "Asset",     "1100", True),
    ("1200", "Non-Current Assets",            "Asset",     "1000", False),
    ("1210", "Property, Plant & Equipment",   "Asset",     "1200", True),
    ("1220", "Accumulated Depreciation",      "Asset",     "1200", True),
    ("2000", "Liabilities",                   "Liability", None,   False),
    ("2100", "Current Liabilities",           "Liability", "2000", False),
    ("2110", "Accounts Payable",              "Liability", "2100", True),
    ("2120", "Accrued Expenses",              "Liability", "2100", True),
    ("2130", "PAYE Payable",                  "Liability", "2100", True),
    ("2140", "NHIF Payable",                  "Liability", "2100", True),
    ("2150", "NSSF Payable",                  "Liability", "2100", True),
    ("2160", "VAT Payable",                   "Liability", "2100", True),
    ("2170", "Patient Deposits",              "Liability", "2100", True),
    ("2200", "Non-Current Liabilities",       "Liability", "2000", False),
    ("2210", "Long-term Loans",               "Liability", "2200", True),
    ("3000", "Equity",                        "Equity",    None,   False),
    ("3100", "Owner's Capital",               "Equity",    "3000", True),
    ("3200", "Retained Earnings",             "Equity",    "3000", True),
    ("3300", "Current Year Earnings",         "Equity",    "3000", True),
    ("4000", "Revenue",                       "Revenue",   None,   False),
    ("4100", "Out-Patient Consultation",      "Revenue",   "4000", True),
    ("4200", "In-Patient Ward Charges",       "Revenue",   "4000", True),
    ("4300", "Laboratory Revenue",            "Revenue",   "4000", True),
    ("4400", "Radiology Revenue",             "Revenue",   "4000", True),
    ("4500", "Pharmacy Revenue",              "Revenue",   "4000", True),
    ("4600", "Theatre / Surgery Revenue",     "Revenue",   "4000", True),
    ("4700", "Maternity Revenue",             "Revenue",   "4000", True),
    ("4800", "Other Operating Revenue",       "Revenue",   "4000", True),
    ("5000", "Cost of Services",              "Expense",   None,   False),
    ("5100", "Pharmacy — Cost of Drugs Sold", "Expense",   "5000", True),
    ("5200", "Lab — Reagents & Consumables",  "Expense",   "5000", True),
    ("5300", "Radiology — Films & Contrast",  "Expense",   "5000", True),
    ("5400", "Theatre — Disposables",         "Expense",   "5000", True),
    ("6000", "Operating Expenses",            "Expense",   None,   False),
    ("6100", "Salaries & Wages",              "Expense",   "6000", True),
    ("6200", "Rent",                          "Expense",   "6000", True),
    ("6300", "Utilities",                     "Expense",   "6000", True),
    ("6400", "Repairs & Maintenance",         "Expense",   "6000", True),
    ("6500", "Office & Admin",                "Expense",   "6000", True),
    ("6600", "Marketing & PR",                "Expense",   "6000", True),
    ("6700", "Insurance Premiums",            "Expense",   "6000", True),
    ("6800", "Depreciation",                  "Expense",   "6000", True),
    ("6900", "Bank Charges",                  "Expense",   "6000", True),
    ("6950", "Other Operating Expenses",      "Expense",   "6000", True),
]

# (source_key, debit_code, credit_code, description)
DEFAULT_MAPPINGS: list[tuple[str, str, str, str]] = [
    ("billing.invoice.created", "1140", "4100",
     "Invoice raised: Dr Accounts Receivable, Cr OP Consultation Revenue (override per service via price list)"),
    ("billing.payment.cash", "1110", "1140",
     "Patient pays cash against invoice: Dr Cash on Hand, Cr Accounts Receivable"),
    ("billing.payment.bank", "1120", "1140",
     "Patient pays via bank transfer/card: Dr Bank Accounts, Cr Accounts Receivable"),
    ("billing.payment.mpesa", "1130", "1140",
     "Patient pays via M-Pesa: Dr Mobile Money, Cr Accounts Receivable"),
    ("billing.deposit.received", "1110", "2170",
     "Patient pre-payment / deposit: Dr Cash, Cr Patient Deposits (liability)"),
    ("billing.deposit.applied", "2170", "1140",
     "Deposit applied to invoice: clear Patient Deposits liability against Accounts Receivable"),
    ("billing.deposit.bulk_allocated", "2170", "1140",
     "Deposit allocated to claim items in bulk: clear Patient Deposits liability against Accounts Receivable"),
    ("pharmacy.dispense.revenue", "1140", "4500",
     "Pharmacy dispensation: Dr Accounts Receivable, Cr Pharmacy Revenue"),
    ("pharmacy.dispense.cogs", "5100", "1160",
     "Pharmacy cost of goods sold: Dr Cost of Drugs Sold, Cr Inventory — Pharmacy"),
    ("cheques.deposit.cleared", "1120", "1140",
     "Cheque cleared into bank: Dr Bank Accounts, Cr Accounts Receivable"),
    ("mpesa.receipt.direct", "1130", "4800",
     "Direct M-Pesa receipt with no prior invoice: Dr Mobile Money, Cr Other Operating Revenue"),
    ("insurance.claim.submitted", "1150", "1140",
     "Claim submitted to insurer: move from patient AR to insurance receivable"),
    ("insurance.claim.settled", "1120", "1150",
     "Insurer pays: Dr Bank, Cr Insurance Receivable"),
]


def seed_accounting_defaults(conn) -> dict:
    """Idempotently seed currency, settings, CoA, and ledger mappings.

    Returns ``{"accounts": n, "mappings": n}`` counts of rows created.
    Works on a SQLAlchemy Session or Connection.
    """
    conn.execute(text(
        "INSERT INTO acc_currencies (code, name, symbol, decimals, is_base, is_active) "
        "SELECT 'KES', 'Kenyan Shilling', 'KSh', 2, true, true "
        "WHERE NOT EXISTS (SELECT 1 FROM acc_currencies WHERE code = 'KES')"
    ))
    conn.execute(text(
        "INSERT INTO acc_settings (base_currency_code, fiscal_year_start_month) "
        "SELECT 'KES', 1 WHERE NOT EXISTS (SELECT 1 FROM acc_settings)"
    ))

    accounts = 0
    # Two-pass: parents first, then children resolving parent_id by code.
    for code, name, acc_type, parent_code, is_postable in DEFAULT_COA:
        if parent_code is None:
            r = conn.execute(text(
                "INSERT INTO acc_accounts (code, name, account_type, parent_id, is_postable, is_active) "
                "SELECT :code, :name, :t, NULL, :p, true "
                "WHERE NOT EXISTS (SELECT 1 FROM acc_accounts WHERE code = :code)"
            ), {"code": code, "name": name, "t": acc_type, "p": is_postable})
            accounts += r.rowcount or 0
    for code, name, acc_type, parent_code, is_postable in DEFAULT_COA:
        if parent_code is not None:
            r = conn.execute(text(
                "INSERT INTO acc_accounts (code, name, account_type, parent_id, is_postable, is_active) "
                "SELECT :code, :name, :t, "
                "       (SELECT account_id FROM acc_accounts WHERE code = :pc), :p, true "
                "WHERE NOT EXISTS (SELECT 1 FROM acc_accounts WHERE code = :code)"
            ), {"code": code, "name": name, "t": acc_type, "pc": parent_code, "p": is_postable})
            accounts += r.rowcount or 0

    mappings = 0
    for source_key, dr_code, cr_code, desc in DEFAULT_MAPPINGS:
        # Skip rows whose accounts a tenant deleted/renamed — same tolerance
        # as the original migration seed.
        r = conn.execute(text(
            "INSERT INTO acc_ledger_mappings "
            "(source_key, debit_account_id, credit_account_id, description, is_active) "
            "SELECT :sk, "
            "       (SELECT account_id FROM acc_accounts WHERE code = :dr), "
            "       (SELECT account_id FROM acc_accounts WHERE code = :cr), "
            "       :d, true "
            "WHERE EXISTS (SELECT 1 FROM acc_accounts WHERE code = :dr) "
            "  AND EXISTS (SELECT 1 FROM acc_accounts WHERE code = :cr) "
            "  AND NOT EXISTS (SELECT 1 FROM acc_ledger_mappings WHERE source_key = :sk)"
        ), {"sk": source_key, "dr": dr_code, "cr": cr_code, "d": desc})
        mappings += r.rowcount or 0

    return {"accounts": accounts, "mappings": mappings}
