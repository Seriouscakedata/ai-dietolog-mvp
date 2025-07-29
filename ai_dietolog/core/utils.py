import re
from typing import Any, Optional

__all__ = ["parse_int"]


def parse_int(value: Any) -> Optional[int]:
    """Return ``value`` as ``int`` if possible.

    Strings may contain optional units like ``"150 kcal"`` or ``"20 г"``.
    Commas and spaces are ignored. If conversion fails, ``None`` is returned.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        m = re.search(r"[-+]?[0-9]+(?:[\s,.][0-9]+)?", value)
        if m:
            num_str = m.group(0).replace(" ", "").replace(",", ".")
            try:
                return int(round(float(num_str)))
            except ValueError:
                return None
    return None
