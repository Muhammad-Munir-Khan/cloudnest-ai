"""Tool: date and time queries.

A single tool with an `operation` argument keeps the LLM's tool list small
while covering the common date-related questions an agent gets.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool

Operation = Literal[
    "now",
    "today",
    "weekday",
    "days_between",
    "add_days",
    "convert_timezone",
    "parse",
]


def _parse_date(s: str) -> datetime:
    """Try several common formats. Raises ValueError on failure."""
    s = s.strip()
    fmts = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    raise ValueError(f"Could not parse date: {s!r}")


@tool
def datetime_tool(
    operation: Operation,
    date: str | None = None,
    date2: str | None = None,
    days: int | None = None,
    timezone_name: str | None = None,
) -> str:
    """Date and time operations.

    Operations:
        now: Current datetime (UTC by default, or in a given timezone).
            Optional args: timezone_name (e.g. "Asia/Karachi", "America/New_York").
        today: Today's date as YYYY-MM-DD.
        weekday: Day of the week for a given date.
            Required: date.
        days_between: Number of days between two dates.
            Required: date, date2.
        add_days: Add N days to a date.
            Required: date, days.
        convert_timezone: Convert a datetime from UTC to another timezone.
            Required: date (ISO format), timezone_name.
        parse: Parse a date string and return ISO format.
            Required: date.

    Args:
        operation: Which operation to perform.
        date: A date string (YYYY-MM-DD or natural format).
        date2: A second date string for operations that compare two dates.
        days: An integer number of days for add_days.
        timezone_name: An IANA timezone name like "Europe/London".

    Returns:
        A human-readable result string.
    """
    try:
        if operation == "now":
            if timezone_name:
                tz = ZoneInfo(timezone_name)
                return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
            return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        if operation == "today":
            return datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if operation == "weekday":
            if not date:
                return "Error: 'weekday' requires the 'date' argument."
            d = _parse_date(date)
            return d.strftime("%A")

        if operation == "days_between":
            if not date or not date2:
                return "Error: 'days_between' requires both 'date' and 'date2'."
            d1 = _parse_date(date)
            d2 = _parse_date(date2)
            delta = (d2 - d1).days
            return f"{abs(delta)} days ({'after' if delta > 0 else 'before' if delta < 0 else 'same day'})"

        if operation == "add_days":
            if not date or days is None:
                return "Error: 'add_days' requires 'date' and 'days'."
            d = _parse_date(date)
            result = d + timedelta(days=days)
            return result.strftime("%Y-%m-%d")

        if operation == "convert_timezone":
            if not date or not timezone_name:
                return "Error: 'convert_timezone' requires 'date' and 'timezone_name'."
            d = _parse_date(date)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            tz = ZoneInfo(timezone_name)
            return d.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")

        if operation == "parse":
            if not date:
                return "Error: 'parse' requires 'date'."
            return _parse_date(date).isoformat()

        return f"Error: unknown operation {operation!r}"

    except ZoneInfoNotFoundError as e:
        return f"Error: unknown timezone {e}. Use IANA names like 'Asia/Karachi'."
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"
