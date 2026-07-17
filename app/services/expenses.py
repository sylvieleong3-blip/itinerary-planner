"""Simple equal-split expense balances."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Expense, Member, Trip

EXPENSE_CURRENCIES: list[dict[str, str]] = [
    {"code": "USD", "label": "US Dollar", "symbol": "$"},
    {"code": "EUR", "label": "Euro", "symbol": "€"},
    {"code": "GBP", "label": "British Pound", "symbol": "£"},
    {"code": "MYR", "label": "Malaysian Ringgit", "symbol": "RM"},
    {"code": "THB", "label": "Thai Baht", "symbol": "฿"},
    {"code": "SGD", "label": "Singapore Dollar", "symbol": "S$"},
    {"code": "JPY", "label": "Japanese Yen", "symbol": "¥"},
    {"code": "AUD", "label": "Australian Dollar", "symbol": "A$"},
    {"code": "CAD", "label": "Canadian Dollar", "symbol": "C$"},
    {"code": "CHF", "label": "Swiss Franc", "symbol": "CHF"},
    {"code": "CNY", "label": "Chinese Yuan", "symbol": "¥"},
    {"code": "HKD", "label": "Hong Kong Dollar", "symbol": "HK$"},
    {"code": "IDR", "label": "Indonesian Rupiah", "symbol": "Rp"},
    {"code": "INR", "label": "Indian Rupee", "symbol": "₹"},
    {"code": "KRW", "label": "South Korean Won", "symbol": "₩"},
    {"code": "NZD", "label": "New Zealand Dollar", "symbol": "NZ$"},
    {"code": "PHP", "label": "Philippine Peso", "symbol": "₱"},
    {"code": "TWD", "label": "Taiwan Dollar", "symbol": "NT$"},
    {"code": "VND", "label": "Vietnamese Dong", "symbol": "₫"},
]

_CURRENCY_CODES = {item["code"] for item in EXPENSE_CURRENCIES}
_SYMBOLS = {item["code"]: item["symbol"] for item in EXPENSE_CURRENCIES}

_COUNTRY_DEFAULT_CURRENCY = {
    "us": "USD",
    "gb": "GBP",
    "my": "MYR",
    "th": "THB",
    "sg": "SGD",
    "jp": "JPY",
    "au": "AUD",
    "ca": "CAD",
    "ch": "CHF",
    "cn": "CNY",
    "hk": "HKD",
    "id": "IDR",
    "in": "INR",
    "kr": "KRW",
    "nz": "NZD",
    "ph": "PHP",
    "tw": "TWD",
    "vn": "VND",
    "fr": "EUR",
    "de": "EUR",
    "es": "EUR",
    "it": "EUR",
    "pt": "EUR",
    "nl": "EUR",
    "ie": "EUR",
}


def normalize_currency(code: str | None) -> str:
    normalized = (code or "USD").strip().upper()
    if normalized in _CURRENCY_CODES:
        return normalized
    return "USD"


def default_expense_currency(trip: Trip) -> str:
    from app.services.destinations import trip_country_codes

    for country_code in trip_country_codes(trip):
        currency = _COUNTRY_DEFAULT_CURRENCY.get((country_code or "").lower())
        if currency:
            return currency
    return "USD"


def format_cents(cents: int, currency: str = "USD") -> str:
    code = normalize_currency(currency)
    symbol = _SYMBOLS.get(code, f"{code} ")
    amount = abs(cents) / 100
    if symbol.endswith("$") or symbol in {"€", "£", "¥", "₹", "₩", "₱", "฿", "₫"}:
        return f"{symbol}{amount:.2f}"
    if symbol in {"RM", "Rp", "CHF", "NT$", "HK$", "NZ$", "A$", "C$", "S$"}:
        return f"{symbol} {amount:.2f}"
    return f"{symbol}{amount:.2f}"


def _balances_for_expenses(expenses: list[Expense], members: list[Member]) -> tuple[list[dict], int]:
    if not expenses or not members:
        return [], 0

    member_ids = [m.id for m in members]
    paid: dict[str, int] = {mid: 0 for mid in member_ids}
    owed: dict[str, int] = {mid: 0 for mid in member_ids}
    total_cents = 0

    for expense in expenses:
        total_cents += expense.amount_cents
        if expense.paid_by_member_id in paid:
            paid[expense.paid_by_member_id] += expense.amount_cents
        share = expense.amount_cents // len(member_ids)
        remainder = expense.amount_cents % len(member_ids)
        for i, mid in enumerate(member_ids):
            owed[mid] += share + (1 if i < remainder else 0)

    balances = []
    for member in members:
        net = paid[member.id] - owed[member.id]
        balances.append(
            {
                "member_id": member.id,
                "name": member.display_name,
                "paid_cents": paid[member.id],
                "owed_cents": owed[member.id],
                "net_cents": net,
            }
        )
    return balances, total_cents


def compute_balances(db: Session, trip_id: str, members: list[Member]) -> dict:
    expenses = db.query(Expense).filter(Expense.trip_id == trip_id).all()
    if not expenses or not members:
        return {"groups": [], "total_cents": 0}

    by_currency: dict[str, list[Expense]] = {}
    for expense in expenses:
        currency = normalize_currency(getattr(expense, "currency", None))
        by_currency.setdefault(currency, []).append(expense)

    groups = []
    total_cents = 0
    for currency in sorted(by_currency):
        balances, group_total = _balances_for_expenses(by_currency[currency], members)
        total_cents += group_total
        groups.append(
            {
                "currency": currency,
                "balances": balances,
                "total_cents": group_total,
            }
        )

    return {"groups": groups, "total_cents": total_cents}
