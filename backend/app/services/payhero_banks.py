"""Pay Hero supported settlement banks.

Pay Hero settles merchant proceeds via the SasaPay rails (verified against
the official PayHero PHP SDK — bank withdraws hit ``/withdraw`` with
``channel=bank`` and a SasaPay ``network_code``). The codes below are the
SasaPay channel codes, mirrored verbatim from
https://docs.sasapay.app/docs/waas/getchannelcodes/ so that what we save
on the tenant config is exactly what Pay Hero / SasaPay accept on the wire.

If Pay Hero adds a bank, append a row — never reuse a code.

Mobile-money channels (M-Pesa, AirtelMoney, T-Kash) and the SasaPay wallet
itself are intentionally excluded — this catalogue is for **bank account**
settlement only. Stima Sacco is kept because Pay Hero accepts it as a
deposit-taking destination.
"""
from __future__ import annotations

from typing import TypedDict


class Bank(TypedDict):
    code: str
    name: str


PAYHERO_BANKS: list[Bank] = [
    {"code": "01", "name": "KCB Bank"},
    {"code": "02", "name": "Standard Chartered Bank Kenya"},
    {"code": "03", "name": "Absa Bank Kenya"},
    {"code": "07", "name": "NCBA Bank"},
    {"code": "10", "name": "Prime Bank"},
    {"code": "11", "name": "Co-operative Bank of Kenya"},
    {"code": "12", "name": "National Bank of Kenya"},
    {"code": "14", "name": "M-Oriental Bank"},
    {"code": "16", "name": "Citibank Kenya"},
    {"code": "18", "name": "Middle East Bank Kenya"},
    {"code": "19", "name": "Bank of Africa Kenya"},
    {"code": "23", "name": "Consolidated Bank of Kenya"},
    {"code": "25", "name": "Credit Bank"},
    {"code": "31", "name": "Stanbic Bank Kenya"},
    {"code": "35", "name": "ABC Bank (African Banking Corporation)"},
    {"code": "36", "name": "Choice Microfinance Bank"},
    {"code": "43", "name": "Ecobank Kenya"},
    {"code": "50", "name": "Paramount Universal Bank"},
    {"code": "51", "name": "Kingdom Bank"},
    {"code": "53", "name": "Guaranty Trust Bank Kenya"},
    {"code": "54", "name": "Victoria Commercial Bank"},
    {"code": "55", "name": "Guardian Bank"},
    {"code": "57", "name": "I&M Bank"},
    {"code": "61", "name": "HFC Bank (Housing Finance)"},
    {"code": "63", "name": "Diamond Trust Bank (DTB)"},
    {"code": "65", "name": "Mayfair CIB Bank"},
    {"code": "66", "name": "Sidian Bank"},
    {"code": "68", "name": "Equity Bank Kenya"},
    {"code": "70", "name": "Family Bank"},
    {"code": "72", "name": "Gulf African Bank"},
    {"code": "74", "name": "First Community Bank"},
    {"code": "75", "name": "DIB Bank Kenya"},
    {"code": "76", "name": "UBA Kenya Bank"},
    {"code": "78", "name": "Kenya Women Microfinance Bank (KWFT)"},
    {"code": "89", "name": "Stima Sacco"},
]


def is_supported(code: str) -> bool:
    return any(b["code"] == code for b in PAYHERO_BANKS)


def name_for(code: str) -> str | None:
    for b in PAYHERO_BANKS:
        if b["code"] == code:
            return b["name"]
    return None
