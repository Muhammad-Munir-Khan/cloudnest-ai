"""Tool: currency conversion via the free Frankfurter API."""
from functools import lru_cache

import requests
from langchain_core.tools import tool

from app.tools._coercion import CoercionError, coerce_numeric

API_BASE = "https://api.frankfurter.app"


@lru_cache(maxsize=1)
def _supported_currencies() -> set[str]:
    try:
        r = requests.get(f"{API_BASE}/currencies", timeout=5)
        r.raise_for_status()
        return set(r.json().keys())
    except requests.RequestException:
        return {
            "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "HKD",
            "INR", "NZD", "SGD", "ZAR", "BRL", "RUB", "MXN", "KRW", "TRY",
        }


@tool
def currency_converter(
    amount: float | int | str,
    from_currency: str,
    to_currency: str,
) -> str:
    """Convert an amount from one currency to another using current ECB rates.

    Supports ~30 major currencies (USD, EUR, GBP, JPY, INR, etc.).
    Rates update once per business day.

    Args:
        amount: The numeric amount to convert. Accepted as a number, a
            numeric string ("36000", "36,000"), or a math expression
            string ("0.15 * 240000") - smaller models sometimes pass
            expressions instead of pre-computed numbers.
        from_currency: 3-letter currency code (e.g. "USD").
        to_currency: 3-letter currency code (e.g. "EUR").

    Returns:
        A formatted result like "100 USD = 92.35 EUR (rate: 0.9235)".
    """
    # Defensive coercion handles strings, math expressions, thousands separators.
    try:
        amount = coerce_numeric(amount)
    except CoercionError as e:
        return f"Error: {e}"

    src = from_currency.upper().strip()
    dst = to_currency.upper().strip()

    if src == dst:
        return f"{amount} {src} = {amount} {dst} (same currency)"

    supported = _supported_currencies()
    missing = [c for c in (src, dst) if c not in supported]
    if missing:
        return (
            f"Error: currency {missing[0]!r} not supported. "
            f"Supported: {', '.join(sorted(supported))}"
        )

    try:
        r = requests.get(
            f"{API_BASE}/latest",
            params={"amount": amount, "from": src, "to": dst},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        result = data["rates"][dst]
        rate = result / amount if amount else 0
        rate_date = data.get("date", "today")
        return (
            f"{amount} {src} = {result:,.2f} {dst} "
            f"(rate: {rate:.4f}, as of {rate_date})"
        )
    except requests.RequestException as e:
        return f"Error: currency API unavailable: {e}"
    except KeyError:
        return "Error: unexpected API response format"
