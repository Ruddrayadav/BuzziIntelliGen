"""Convert service return values into safe JSON without changing their meaning."""

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import math
from typing import Any

import pandas as pd


def to_jsonable(value: Any) -> Any:
    """Serialize DataFrames, dataclasses, dates, and non-finite numbers safely."""
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return [to_jsonable(row) for row in value.to_dict(orient="records")]
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return to_jsonable(value.item())
        except ValueError:
            pass
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value
