"""Pure helper functions for the CSG integration.

This module deliberately has no runtime dependency on Home Assistant so that
the logic can be unit-tested in a plain Python environment.
"""

from __future__ import annotations

from typing import Any

# Must match homeassistant.const.STATE_UNAVAILABLE ("unavailable"). Duplicated
# here to keep this module importable without Home Assistant installed.
STATE_UNAVAILABLE = "unavailable"


def merge_by_day_data(
    by_day_from_cost: list | str,
    kwh_from_cost: float | str,
    by_day_from_usage: list | str,
    kwh_from_usage: float | str,
) -> tuple[list | str, float | str]:
    """Merge daily cost and usage data, preferring the newer source.

    ``STATE_UNAVAILABLE`` sentinels are propagated: the merged result is only
    unavailable when both sources are unavailable.
    """
    if (
        by_day_from_cost == STATE_UNAVAILABLE
        and by_day_from_usage == STATE_UNAVAILABLE
    ):
        by_day = STATE_UNAVAILABLE
    elif by_day_from_cost == STATE_UNAVAILABLE:
        by_day = by_day_from_usage
    elif by_day_from_usage == STATE_UNAVAILABLE:
        by_day = by_day_from_cost
    else:
        if len(by_day_from_cost) >= len(by_day_from_usage):
            by_day = by_day_from_cost
        else:
            by_day = by_day_from_usage
            for idx, item in enumerate(by_day_from_cost):
                by_day[idx][WF_ATTR_CHARGE] = item[WF_ATTR_CHARGE]

    if kwh_from_cost == STATE_UNAVAILABLE and kwh_from_usage == STATE_UNAVAILABLE:
        kwh = STATE_UNAVAILABLE
    elif kwh_from_cost == STATE_UNAVAILABLE:
        kwh = kwh_from_usage
    elif kwh_from_usage == STATE_UNAVAILABLE:
        kwh = kwh_from_cost
    else:
        kwh = max(kwh_from_cost, kwh_from_usage)
    return by_day, kwh


# Kept in this module (instead of importing from .const) to avoid a Home
# Assistant import; values must match the ones used in the coordinator.
WF_ATTR_CHARGE = "charge"
WF_ATTR_KWH = "kwh"


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert a value to float, returning default when not convertible."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
