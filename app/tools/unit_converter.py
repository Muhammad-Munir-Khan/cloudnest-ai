"""Tool: unit conversion using pint."""
from langchain_core.tools import tool

_ureg = None


def _get_registry():
    global _ureg
    if _ureg is None:
        import pint
        _ureg = pint.UnitRegistry()
    return _ureg


@tool
def unit_converter(
    value: float | int | str,
    from_unit: str,
    to_unit: str,
) -> str:
    """Convert a numeric value from one unit to another.

    Supports a huge range of units: meters/feet/miles, kilograms/pounds/ounces,
    celsius/fahrenheit/kelvin, liters/gallons, joules/calories, km/h vs mph, etc.

    Use simple names: "kg", "lb", "celsius", "fahrenheit", "km", "mile",
    "liter", "gallon", "joule", "calorie", "kph", "mph", "hour", "minute".
    Compound units like "km/h" and "kg/m^3" also work.

    Args:
        value: The numeric value to convert. Accepted as a number OR a
            string of digits (some LLMs occasionally quote numeric arguments).
        from_unit: The source unit (e.g. "kg", "celsius", "mph").
        to_unit: The target unit (e.g. "lb", "fahrenheit", "kph").

    Returns:
        A formatted result like "100 km = 62.137 mile" or an error message.
    """
    # Defensive coercion: smaller LLMs (e.g. gpt-oss-20b) sometimes serialize
    # numeric tool arguments as strings ("100" instead of 100), which Groq's
    # strict schema validation rejects. We declare the parameter as
    # `float | int | str` so the schema accepts both, then coerce here.
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("_", "").strip()
        try:
            value = float(cleaned)
        except ValueError:
            return f"Error: value {value!r} is not a valid number."
    elif not isinstance(value, (int, float)):
        return f"Error: value must be a number, got {type(value).__name__}."

    value = float(value)

    try:
        ureg = _get_registry()
        aliases = {
            "celsius": "degC", "c": "degC", "°c": "degC",
            "fahrenheit": "degF", "f": "degF", "°f": "degF",
            "kelvin": "degK",
            "kph": "kilometer/hour", "mph": "mile/hour",
        }
        f = aliases.get(from_unit.lower().strip(), from_unit)
        t = aliases.get(to_unit.lower().strip(), to_unit)

        quantity = value * ureg(f)
        converted = quantity.to(ureg(t))
        magnitude = converted.magnitude

        if abs(magnitude) >= 1000 or magnitude == int(magnitude):
            display = f"{magnitude:,.4f}".rstrip("0").rstrip(".")
        else:
            display = f"{magnitude:.4g}"

        return f"{value} {from_unit} = {display} {to_unit}"
    except Exception as e:
        return f"Error: {e}"
