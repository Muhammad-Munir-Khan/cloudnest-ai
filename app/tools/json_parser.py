"""Tool: parse and query JSON / JSON-like data."""
import json

from langchain_core.tools import tool


@tool
def json_parser(json_text: str, path: str | None = None) -> str:
    """Parse JSON and optionally extract a value at a given path.

    Useful when another tool returned JSON-shaped text and you need to drill
    into a specific field. Path uses dot/bracket notation:
      "results.0.title"   -> data["results"][0]["title"]
      "user.name"         -> data["user"]["name"]
      "items.length"      -> the count of items in the list

    Args:
        json_text: A string containing JSON.
        path: Optional dotted path to extract. Without it, returns a pretty-
            printed full structure summary.

    Returns:
        The extracted value, or a formatted overview if no path given.
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON: {e.msg} at line {e.lineno} col {e.colno}"

    if path is None:
        return _summarize(data)

    try:
        value = _drill(data, path)
    except (KeyError, IndexError, TypeError) as e:
        return f"Error: path {path!r} not found: {e}"

    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, default=str)
    return str(value)


def _drill(data, path: str):
    """Walk `data` following dot-separated keys / numeric indices."""
    parts = [p for p in path.replace("[", ".").replace("]", "").split(".") if p]
    cursor = data
    for part in parts:
        if part == "length" and isinstance(cursor, (list, str, dict)):
            return len(cursor)
        if part.isdigit() and isinstance(cursor, list):
            cursor = cursor[int(part)]
        elif isinstance(cursor, dict):
            cursor = cursor[part]
        else:
            raise KeyError(f"cannot descend into {type(cursor).__name__} with {part!r}")
    return cursor


def _summarize(data, depth: int = 0, max_depth: int = 3) -> str:
    """Pretty-print the JSON structure, truncating deep/large nodes."""
    indent = "  " * depth
    if depth >= max_depth:
        return f"{indent}{type(data).__name__} (...)"

    if isinstance(data, dict):
        if not data:
            return f"{indent}{{}} (empty)"
        lines = [f"{indent}{{"]
        for k, v in list(data.items())[:20]:
            lines.append(f"{indent}  {k!r}: {_compact(v, depth + 1, max_depth)}")
        if len(data) > 20:
            lines.append(f"{indent}  ... ({len(data) - 20} more keys)")
        lines.append(f"{indent}}}")
        return "\n".join(lines)

    if isinstance(data, list):
        if not data:
            return f"{indent}[] (empty list)"
        lines = [f"{indent}[ ({len(data)} items)"]
        for v in data[:5]:
            lines.append(f"{indent}  {_compact(v, depth + 1, max_depth)}")
        if len(data) > 5:
            lines.append(f"{indent}  ... ({len(data) - 5} more items)")
        lines.append(f"{indent}]")
        return "\n".join(lines)

    return f"{indent}{data!r}"


def _compact(v, depth: int, max_depth: int) -> str:
    """Inline representation of a value for the summary view."""
    if isinstance(v, (dict, list)):
        return _summarize(v, depth, max_depth).lstrip()
    return repr(v)
