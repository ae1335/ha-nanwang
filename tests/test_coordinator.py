"""Unit tests for CSGCoordinator business logic (sensor.py).

These run against the structured HA stubs from conftest.py. The coordinator
is instantiated via ``__new__`` to skip DataUpdateCoordinator.__init__; only
the attributes each method actually touches are provided.
"""

from __future__ import annotations

import asyncio
import datetime
import types
import unittest.mock as mock

from custom_components.csg_power import sensor as sensor_mod
from custom_components.csg_power.api import (
    CSGAPIError,
    CSGElectricityAccount,
    NotLoggedIn,
)
from custom_components.csg_power.const import (
    ATTR_KEY_LAST_MONTH_BY_DAY,
    ATTR_KEY_LATEST_DAY_DATE,
    ATTR_KEY_THIS_MONTH_BY_DAY,
    CONF_SETTINGS,
    CONF_UPDATE_INTERVAL,
    DATA_KEY_LAST_UPDATE_DAY,
    DOMAIN,
    STATE_UPDATE_UNCHANGED,
    SUFFIX_LATEST_DAY_COST,
    SUFFIX_LATEST_DAY_KWH,
)
from homeassistant.const import CONF_USERNAME, STATE_UNAVAILABLE

ACCOUNT_NUMBER = "1234567890"
ENTRY_ID = "entry-1"


def make_coordinator() -> sensor_mod.CSGCoordinator:
    """Build a coordinator instance without running the parent __init__."""
    coord = sensor_mod.CSGCoordinator.__new__(sensor_mod.CSGCoordinator)
    coord._gathered_data = {}
    coord._login_expired = False
    coord.hass = mock.Mock()
    coord._config = {
        CONF_USERNAME: "13800000000",
        CONF_SETTINGS: {CONF_UPDATE_INTERVAL: 14400},
    }
    coord._config_entry = mock.Mock(entry_id=ENTRY_ID)
    return coord


# ---------------------------------------------------------------------------
# _update_latest_day
# ---------------------------------------------------------------------------


class TestUpdateLatestDay:
    def _run(self, coord, this_month, last_month):
        account = CSGElectricityAccount(account_number=ACCOUNT_NUMBER)
        coord._gathered_data = {
            ACCOUNT_NUMBER: {
                ATTR_KEY_THIS_MONTH_BY_DAY: {
                    ATTR_KEY_THIS_MONTH_BY_DAY: this_month
                },
                ATTR_KEY_LAST_MONTH_BY_DAY: {
                    ATTR_KEY_LAST_MONTH_BY_DAY: last_month
                },
            }
        }
        coord._update_latest_day(account)
        data = coord._gathered_data[ACCOUNT_NUMBER]
        return (
            data[SUFFIX_LATEST_DAY_KWH],
            data[SUFFIX_LATEST_DAY_COST],
            data[ATTR_KEY_LATEST_DAY_DATE][ATTR_KEY_LATEST_DAY_DATE],
        )

    def test_takes_last_day_of_this_month(self):
        kwh, cost, date = self._run(
            make_coordinator(),
            [
                {"date": "2026-03-09", "kwh": 4.0, "charge": 2.0},
                {"date": "2026-03-10", "kwh": 5.0, "charge": 2.5},
            ],
            STATE_UPDATE_UNCHANGED,
        )
        assert (kwh, cost, date) == (5.0, 2.5, "2026-03-10")

    def test_zero_cost_is_valid_not_unavailable(self):
        # Regression for v2.1.3: `charge or STATE_UNAVAILABLE` turned a
        # legitimate 0-cost day into "unavailable".
        kwh, cost, _ = self._run(
            make_coordinator(),
            [{"date": "2026-03-10", "kwh": 0.0, "charge": 0.0}],
            STATE_UPDATE_UNCHANGED,
        )
        assert kwh == 0.0
        assert cost == 0.0

    def test_falls_back_to_last_month(self):
        kwh, cost, date = self._run(
            make_coordinator(),
            STATE_UNAVAILABLE,
            [{"date": "2026-02-28", "kwh": 3.0, "charge": 1.5}],
        )
        # Last month has no cost in the latest-day sensor (by design)
        assert (kwh, cost, date) == (3.0, STATE_UNAVAILABLE, "2026-02-28")

    def test_both_unavailable(self):
        kwh, cost, date = self._run(
            make_coordinator(), STATE_UNAVAILABLE, STATE_UNAVAILABLE
        )
        assert kwh == STATE_UNAVAILABLE
        assert cost == STATE_UNAVAILABLE
        assert date == STATE_UNAVAILABLE

    def test_unchanged_last_month_is_not_used(self):
        kwh, cost, date = self._run(
            make_coordinator(),
            [],  # empty this month, no entries yet
            STATE_UPDATE_UNCHANGED,
        )
        assert kwh == STATE_UNAVAILABLE
        assert cost == STATE_UNAVAILABLE
        assert date == STATE_UNAVAILABLE


# ---------------------------------------------------------------------------
# _update_states (date-based refresh throttling)
# ---------------------------------------------------------------------------


class TestUpdateStates:
    def _run(self, year, month, day, last_update_day):
        coord = make_coordinator()
        hass_data = {DOMAIN: {ENTRY_ID: {}}}
        if last_update_day is not None:
            hass_data[DOMAIN][ENTRY_ID][DATA_KEY_LAST_UPDATE_DAY] = last_update_day
        coord.hass = types.SimpleNamespace(data=hass_data)

        fixed = datetime.datetime(year, month, day)
        with mock.patch.object(sensor_mod.datetime, "datetime") as fake_dt:
            fake_dt.now.return_value = fixed
            coord._update_states()
        return coord

    def test_first_ever_update_refreshes_everything(self):
        coord = self._run(2026, 3, 10, None)
        assert coord._if_update_last_month is True
        assert coord._if_update_last_year is True

    def test_early_month_refreshes_last_month_only(self):
        coord = self._run(2026, 3, 2, 5)
        assert coord._if_update_last_month is True
        assert coord._if_update_last_year is False

    def test_late_month_skips_last_month(self):
        coord = self._run(2026, 3, 10, 5)
        assert coord._if_update_last_month is False
        assert coord._if_update_last_year is False

    def test_early_january_refreshes_last_year(self):
        coord = self._run(2026, 1, 2, 5)
        assert coord._if_update_last_month is True
        assert coord._if_update_last_year is True

    def test_early_january_same_day_skips_last_year(self):
        # Already refreshed earlier on the same day -> no need again
        coord = self._run(2026, 1, 2, 2)
        assert coord._if_update_last_month is True
        assert coord._if_update_last_year is False

    def test_period_variables_are_set(self):
        coord = self._run(2026, 1, 2, 5)
        assert coord._this_year == 2026
        assert coord._this_month_ym == (2026, 1)
        assert coord._last_year == 2025
        assert coord._last_month_ym == (2025, 12)


# ---------------------------------------------------------------------------
# _async_fetch (exception dispatch)
# ---------------------------------------------------------------------------


class TestAsyncFetch:
    def _probe(self, x):  # named function so func.__name__ is stable
        return x

    def test_success(self):
        coord = make_coordinator()
        coord.hass.async_add_executor_job = mock.AsyncMock(return_value=42)
        ok, result = asyncio.run(coord._async_fetch(self._probe, 1))
        assert (ok, result) == (True, 42)
        assert coord._login_expired is False

    def test_not_logged_in_sets_expiry_flag(self):
        coord = make_coordinator()
        coord.hass.async_add_executor_job = mock.AsyncMock(
            side_effect=NotLoggedIn("04", "expired")
        )
        ok, result = asyncio.run(coord._async_fetch(self._probe, 1))
        assert ok is False
        assert coord._login_expired is True
        assert result[0] == "_probe"

    def test_api_error_does_not_set_expiry_flag(self):
        coord = make_coordinator()
        coord.hass.async_add_executor_job = mock.AsyncMock(
            side_effect=CSGAPIError("xx", "boom")
        )
        ok, _result = asyncio.run(coord._async_fetch(self._probe, 1))
        assert ok is False
        assert coord._login_expired is False

    def test_generic_exception_is_caught(self):
        coord = make_coordinator()
        coord.hass.async_add_executor_job = mock.AsyncMock(
            side_effect=ValueError("boom")
        )
        ok, _result = asyncio.run(coord._async_fetch(self._probe, 1))
        assert ok is False
        assert coord._login_expired is False
