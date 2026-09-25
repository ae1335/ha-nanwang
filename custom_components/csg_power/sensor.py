"""Sensors for the China Southern Power Grid integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
import traceback
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_USERNAME,
    STATE_UNAVAILABLE,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import CSGClient, CSGElectricityAccount, CSGAPIError, NotLoggedIn
from .const import (
    ATTR_KEY_CURRENT_LADDER_START_DATE,
    ATTR_KEY_LAST_MONTH_BY_DAY,
    ATTR_KEY_LAST_YEAR_BY_MONTH,
    ATTR_KEY_LATEST_DAY_DATE,
    ATTR_KEY_THIS_MONTH_BY_DAY,
    ATTR_KEY_THIS_YEAR_BY_MONTH,
    CONF_AUTH_TOKEN,
    CONF_ELE_ACCOUNTS,
    CONF_SETTINGS,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATED_AT,
    DATA_KEY_LAST_UPDATE_DAY,
    DOMAIN,
    SETTING_LAST_MONTH_UPDATE_DAY_THRESHOLD,
    SETTING_LAST_YEAR_UPDATE_DAY_THRESHOLD,
    SETTING_UPDATE_TIMEOUT,
    STATE_UPDATE_UNCHANGED,
    SUFFIX_ARR,
    SUFFIX_BAL,
    SUFFIX_CURRENT_LADDER,
    SUFFIX_CURRENT_LADDER_REMAINING_KWH,
    SUFFIX_CURRENT_LADDER_TARIFF,
    SUFFIX_LAST_MONTH_COST,
    SUFFIX_LAST_MONTH_KWH,
    SUFFIX_LAST_YEAR_COST,
    SUFFIX_LAST_YEAR_KWH,
    SUFFIX_LATEST_DAY_COST,
    SUFFIX_LATEST_DAY_KWH,
    SUFFIX_THIS_MONTH_COST,
    SUFFIX_THIS_MONTH_KWH,
    SUFFIX_THIS_YEAR_COST,
    SUFFIX_THIS_YEAR_KWH,
    SUFFIX_YESTERDAY_KWH,
    WF_ATTR_CHARGE,
    WF_ATTR_DATE,
    WF_ATTR_KWH,
    WF_ATTR_LADDER,
    WF_ATTR_LADDER_REMAINING_KWH,
    WF_ATTR_LADDER_START_DATE,
    WF_ATTR_LADDER_TARIFF,
)
from .utils import merge_by_day_data

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    if not config_entry.data[CONF_ELE_ACCOUNTS]:
        _LOGGER.info("No ele accounts in config, exit entry setup")
        return

    coordinator = CSGCoordinator(hass, config_entry)
    all_sensors: list[SensorEntity] = []

    for account_number in config_entry.data[CONF_ELE_ACCOUNTS]:
        sensors: list[SensorEntity] = [
            CSGCostSensor(coordinator, account_number, SUFFIX_BAL),
            CSGCostSensor(coordinator, account_number, SUFFIX_ARR),
            CSGEnergySensor(coordinator, account_number, SUFFIX_YESTERDAY_KWH),
            CSGEnergySensor(
                coordinator,
                account_number,
                SUFFIX_LATEST_DAY_KWH,
                extra_state_attributes_key=ATTR_KEY_LATEST_DAY_DATE,
            ),
            CSGCostSensor(
                coordinator,
                account_number,
                SUFFIX_LATEST_DAY_COST,
                extra_state_attributes_key=ATTR_KEY_LATEST_DAY_DATE,
            ),
            CSGEnergySensor(
                coordinator,
                account_number,
                SUFFIX_THIS_YEAR_KWH,
                extra_state_attributes_key=ATTR_KEY_THIS_YEAR_BY_MONTH,
            ),
            CSGCostSensor(coordinator, account_number, SUFFIX_THIS_YEAR_COST),
            CSGEnergySensor(
                coordinator,
                account_number,
                SUFFIX_THIS_MONTH_KWH,
                extra_state_attributes_key=ATTR_KEY_THIS_MONTH_BY_DAY,
            ),
            CSGCostSensor(
                coordinator,
                account_number,
                SUFFIX_THIS_MONTH_COST,
                extra_state_attributes_key=ATTR_KEY_THIS_MONTH_BY_DAY,
            ),
            CSGLadderStageSensor(
                coordinator,
                account_number,
                SUFFIX_CURRENT_LADDER,
                extra_state_attributes_key=ATTR_KEY_CURRENT_LADDER_START_DATE,
            ),
            CSGEnergySensor(
                coordinator, account_number, SUFFIX_CURRENT_LADDER_REMAINING_KWH
            ),
            CSGCostSensor(coordinator, account_number, SUFFIX_CURRENT_LADDER_TARIFF),
            CSGEnergySensor(
                coordinator,
                account_number,
                SUFFIX_LAST_YEAR_KWH,
                extra_state_attributes_key=ATTR_KEY_LAST_YEAR_BY_MONTH,
            ),
            CSGCostSensor(coordinator, account_number, SUFFIX_LAST_YEAR_COST),
            CSGEnergySensor(
                coordinator,
                account_number,
                SUFFIX_LAST_MONTH_KWH,
                extra_state_attributes_key=ATTR_KEY_LAST_MONTH_BY_DAY,
            ),
            CSGCostSensor(
                coordinator,
                account_number,
                SUFFIX_LAST_MONTH_COST,
                extra_state_attributes_key=ATTR_KEY_LAST_MONTH_BY_DAY,
            ),
        ]
        all_sensors.extend(sensors)

    # Fetch the first data set BEFORE adding entities so they are created with
    # valid states, and so that an expired session correctly triggers reauth
    # during setup instead of leaving unavailable sensors behind.
    await coordinator.async_config_entry_first_refresh()

    async_add_entities(all_sensors)
    _LOGGER.debug(
        "created %d sensors for config %s", len(all_sensors), config_entry.title
    )


class CSGBaseSensor(CoordinatorEntity, SensorEntity):
    """Base CSG sensor."""

    # Defaults, overridden by subclasses
    _DEFAULT_ICON = "mdi:flash"
    _DEFAULT_STATE_CLASS: SensorStateClass | None = None

    # Per-suffix overrides (keyed by entity suffix)
    _ICON_OVERRIDES: dict[str, str] = {}
    _STATE_CLASS_OVERRIDES: dict[str, SensorStateClass] = {}
    # Number of decimals displayed in the UI, per suffix (default 2)
    _PRECISION_OVERRIDES: dict[str, int] = {}

    # Friendly name mapping for sensor suffixes
    _SENSOR_NAMES: dict[str, str] = {
        SUFFIX_BAL: "余额",
        SUFFIX_ARR: "欠费",
        SUFFIX_YESTERDAY_KWH: "昨日用电量",
        SUFFIX_LATEST_DAY_KWH: "最近日用电量",
        SUFFIX_LATEST_DAY_COST: "最近日电费",
        SUFFIX_THIS_YEAR_KWH: "本年总用电量",
        SUFFIX_THIS_YEAR_COST: "本年总电费",
        SUFFIX_THIS_MONTH_KWH: "本月累计用电量",
        SUFFIX_THIS_MONTH_COST: "本月累计电费",
        SUFFIX_CURRENT_LADDER: "当前阶梯档位",
        SUFFIX_CURRENT_LADDER_REMAINING_KWH: "阶梯剩余电量",
        SUFFIX_CURRENT_LADDER_TARIFF: "阶梯电价",
        SUFFIX_LAST_YEAR_KWH: "上年总用电量",
        SUFFIX_LAST_YEAR_COST: "上年总电费",
        SUFFIX_LAST_MONTH_KWH: "上月累计用电量",
        SUFFIX_LAST_MONTH_COST: "上月累计电费",
    }

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        account_number: str,
        entity_suffix: str,
        extra_state_attributes_key: str | None = None,
    ) -> None:
        SensorEntity.__init__(self)
        CoordinatorEntity.__init__(self, coordinator)
        self._coordinator = coordinator
        self._account_number = account_number
        self._entity_suffix = entity_suffix
        self._extra_state_attributes_key = extra_state_attributes_key
        self._attr_extra_state_attributes = {}
        self._attr_name = (
            f"{self._account_number} "
            f"{self._SENSOR_NAMES.get(entity_suffix, entity_suffix)}"
        )
        self._attr_icon = self._ICON_OVERRIDES.get(entity_suffix, self._DEFAULT_ICON)
        self._attr_state_class = self._STATE_CLASS_OVERRIDES.get(
            entity_suffix, self._DEFAULT_STATE_CLASS
        )
        self._attr_suggested_display_precision = self._PRECISION_OVERRIDES.get(
            entity_suffix, 2
        )

    @property
    def unique_id(self) -> str | None:
        return f"{DOMAIN}.{self._account_number}.{self._entity_suffix}"

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._account_number)},
            name=f"CSGAccount-{self._account_number}",
            manufacturer="CSG",
            model="CSG Virtual Electricity Meter",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self._coordinator.data:
            _LOGGER.error("%s coordinator has no data", self.unique_id)
            self._attr_available = False
            self.async_write_ha_state()
            return

        account_data = self._coordinator.data.get(self._account_number)
        if account_data is None:
            _LOGGER.warning("%s not found in coordinator data", self.unique_id)
            self._attr_available = False
            self.async_write_ha_state()
            return

        new_native_value = account_data.get(self._entity_suffix)
        if new_native_value is None:
            _LOGGER.warning("%s data not found in coordinator data", self.unique_id)
            self._attr_available = False
            self.async_write_ha_state()
            return

        if new_native_value == STATE_UNAVAILABLE:
            _LOGGER.debug("%s data is unavailable", self.unique_id)
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_available = True

        if new_native_value == STATE_UPDATE_UNCHANGED:
            _LOGGER.debug("%s doesn't need to be updated, skip", self.unique_id)
            return

        self._attr_native_value = new_native_value

        if self._extra_state_attributes_key:
            new_attributes = account_data.get(self._extra_state_attributes_key)
            if new_attributes is None:
                new_attributes = {}
                _LOGGER.warning(
                    "%s attribute %s not found in coordinator data",
                    self.unique_id,
                    self._extra_state_attributes_key,
                )
            self._attr_extra_state_attributes = new_attributes

        _LOGGER.debug("%s state update done!", self.unique_id)
        self.async_write_ha_state()


class CSGEnergySensor(CSGBaseSensor):
    """Energy sensor."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _DEFAULT_ICON = "mdi:lightning-bolt"
    _DEFAULT_STATE_CLASS = SensorStateClass.TOTAL

    # Remaining ladder quota is a level (it decreases over the month),
    # so it must be measured rather than accumulated.
    _STATE_CLASS_OVERRIDES = {
        SUFFIX_CURRENT_LADDER_REMAINING_KWH: SensorStateClass.MEASUREMENT,
    }


class CSGCostSensor(CSGBaseSensor):
    """Cost sensor."""

    # NOTE: HA has no UnitOfCurrency enum; monetary sensors take the currency
    # code as a plain string.
    _attr_native_unit_of_measurement = "CNY"
    _attr_device_class = SensorDeviceClass.MONETARY
    _DEFAULT_ICON = "mdi:currency-cny"
    _DEFAULT_STATE_CLASS = SensorStateClass.TOTAL

    # Balance, arrears and the current tariff are instantaneous levels, not
    # cumulative totals. Using MEASUREMENT keeps long-term statistics correct.
    _STATE_CLASS_OVERRIDES = {
        SUFFIX_BAL: SensorStateClass.MEASUREMENT,
        SUFFIX_ARR: SensorStateClass.MEASUREMENT,
        SUFFIX_CURRENT_LADDER_TARIFF: SensorStateClass.MEASUREMENT,
    }

    # Tariffs need more decimals (e.g. 0.5880 CNY/kWh)
    _PRECISION_OVERRIDES = {SUFFIX_CURRENT_LADDER_TARIFF: 4}


class CSGLadderStageSensor(CSGBaseSensor):
    """Ladder stage sensor."""

    _DEFAULT_ICON = "mdi:stairs"


class CSGCoordinator(DataUpdateCoordinator):
    """Custom coordinator for CSG data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._config = dict(config_entry.data)
        super().__init__(
            hass,
            _LOGGER,
            name=f"CSG Account {self._config[CONF_USERNAME]}",
            update_interval=timedelta(
                seconds=self._config[CONF_SETTINGS][CONF_UPDATE_INTERVAL]
            ),
        )
        self._client: CSGClient | None = None
        self._login_expired = False
        self._if_update_last_month = True
        self._if_update_last_year = True
        self._this_day = 0
        self._this_year = 0
        self._this_month_ym: tuple[int, int] = (0, 0)
        self._last_year = 0
        self._last_month_ym: tuple[int, int] = (0, 0)
        self._this_month_update_completed_flag = asyncio.Event()
        self._gathered_data: dict[str, Any] = {}

    @property
    def _config_entry_id(self) -> str:
        return self._config_entry.entry_id

    async def _async_refresh_client(self) -> None:
        """Refresh the client and verify login."""
        _LOGGER.debug("Refreshing client")
        self._client = await self.hass.async_add_executor_job(
            CSGClient.load,
            {CONF_AUTH_TOKEN: self._config[CONF_AUTH_TOKEN]},
        )
        logged_in = await self.hass.async_add_executor_job(self._client.verify_login)
        if not logged_in:
            _LOGGER.warning("%s: Login expired", self._config[CONF_USERNAME])
            raise ConfigEntryAuthFailed("Login expired")
        _LOGGER.debug("%s: Session still valid", self._config[CONF_USERNAME])
        await self.hass.async_add_executor_job(self._client.initialize)

    async def _async_fetch(self, func: Any, *args: Any, **kwargs: Any) -> tuple[bool, Any]:
        """Fetch data from API with timeout and exception handling."""
        try:
            async with asyncio.timeout(SETTING_UPDATE_TIMEOUT):
                return True, await self.hass.async_add_executor_job(
                    func, *args, **kwargs
                )
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout fetching data in function: %s", func.__name__)
            return False, (func.__name__, err)
        except NotLoggedIn as err:
            self._login_expired = True
            _LOGGER.error(
                "Session invalidated unexpectedly in function: %s", func.__name__
            )
            return False, (func.__name__, err)
        except CSGAPIError as err:
            _LOGGER.error(
                "Error fetching data in coordinator: API error, function %s, %s",
                func.__name__,
                err,
            )
            return False, (func.__name__, err)
        except Exception as err:
            _LOGGER.error("Unexpected exception: %s", err)
            _LOGGER.error(traceback.format_exc())
            return False, (func.__name__, err)

    async def _async_update_bal_arr(self, account: CSGElectricityAccount) -> None:
        """Update balance and arrears."""
        success, result = await self._async_fetch(
            self._client.get_balance_and_arrears, account
        )
        if success:
            balance, arrears = result
        else:
            balance, arrears = STATE_UNAVAILABLE, STATE_UNAVAILABLE
        self._gathered_data[account.account_number][SUFFIX_BAL] = balance
        self._gathered_data[account.account_number][SUFFIX_ARR] = arrears

    async def _async_update_yesterday_kwh(self, account: CSGElectricityAccount) -> None:
        """Update yesterday's kwh."""
        success, result = await self._async_fetch(
            self._client.get_yesterday_kwh, account
        )
        if success and result is not None:
            yesterday_kwh = result
        else:
            yesterday_kwh = STATE_UNAVAILABLE
        self._gathered_data[account.account_number][
            SUFFIX_YESTERDAY_KWH
        ] = yesterday_kwh

    async def _async_update_this_year_stats(self, account: CSGElectricityAccount) -> None:
        """Update this year's data."""
        success, result = await self._async_fetch(
            self._client.get_year_month_stats, account, self._this_year
        )
        if success:
            this_year_cost, this_year_kwh, this_year_by_month = result
        else:
            this_year_cost, this_year_kwh, this_year_by_month = (
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
            )
        self._gathered_data[account.account_number][SUFFIX_THIS_YEAR_KWH] = this_year_kwh
        self._gathered_data[account.account_number][SUFFIX_THIS_YEAR_COST] = this_year_cost
        self._gathered_data[account.account_number][ATTR_KEY_THIS_YEAR_BY_MONTH] = {
            ATTR_KEY_THIS_YEAR_BY_MONTH: this_year_by_month
        }

    async def _async_update_last_year_stats(self, account: CSGElectricityAccount) -> None:
        """Update last year's data."""
        if not self._if_update_last_year:
            self._gathered_data[account.account_number][
                SUFFIX_LAST_YEAR_KWH
            ] = STATE_UPDATE_UNCHANGED
            self._gathered_data[account.account_number][
                SUFFIX_LAST_YEAR_COST
            ] = STATE_UPDATE_UNCHANGED
            self._gathered_data[account.account_number][ATTR_KEY_LAST_YEAR_BY_MONTH] = {
                ATTR_KEY_LAST_YEAR_BY_MONTH: STATE_UPDATE_UNCHANGED
            }
            return
        success, result = await self._async_fetch(
            self._client.get_year_month_stats, account, self._last_year
        )
        if success:
            last_year_cost, last_year_kwh, last_year_by_month = result
        else:
            last_year_cost, last_year_kwh, last_year_by_month = (
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
            )
        self._gathered_data[account.account_number][SUFFIX_LAST_YEAR_KWH] = last_year_kwh
        self._gathered_data[account.account_number][SUFFIX_LAST_YEAR_COST] = last_year_cost
        self._gathered_data[account.account_number][ATTR_KEY_LAST_YEAR_BY_MONTH] = {
            ATTR_KEY_LAST_YEAR_BY_MONTH: last_year_by_month
        }

    async def _async_update_this_month_stats_and_ladder(
        self, account: CSGElectricityAccount
    ) -> None:
        """Update this month's usage, cost and ladder info."""
        task_fetch_usage = asyncio.create_task(
            self._async_fetch(
                self._client.get_month_daily_usage_detail, account, self._this_month_ym
            )
        )
        task_fetch_cost = asyncio.create_task(
            self._async_fetch(
                self._client.get_month_daily_cost_detail, account, self._this_month_ym
            )
        )
        results = await asyncio.gather(task_fetch_usage, task_fetch_cost)
        (success_usage, result_usage), (success_cost, result_cost) = results

        if success_usage:
            this_month_kwh_from_usage, this_month_by_day_from_usage = result_usage
        else:
            this_month_kwh_from_usage = STATE_UNAVAILABLE
            this_month_by_day_from_usage = STATE_UNAVAILABLE

        if success_cost:
            (
                this_month_cost,
                this_month_kwh_from_cost,
                ladder,
                this_month_by_day_from_cost,
            ) = result_cost
            if this_month_cost is None:
                this_month_cost = STATE_UNAVAILABLE
            if this_month_kwh_from_cost is None:
                this_month_kwh_from_cost = STATE_UNAVAILABLE
            ladder_stage = (
                ladder[WF_ATTR_LADDER]
                if ladder[WF_ATTR_LADDER] is not None
                else STATE_UNAVAILABLE
            )
            ladder_remaining_kwh = (
                ladder[WF_ATTR_LADDER_REMAINING_KWH]
                if ladder[WF_ATTR_LADDER_REMAINING_KWH] is not None
                else STATE_UNAVAILABLE
            )
            ladder_tariff = (
                ladder[WF_ATTR_LADDER_TARIFF]
                if ladder[WF_ATTR_LADDER_TARIFF] is not None
                else STATE_UNAVAILABLE
            )
            ladder_start_date = (
                ladder[WF_ATTR_LADDER_START_DATE]
                if ladder[WF_ATTR_LADDER_START_DATE] is not None
                else STATE_UNAVAILABLE
            )
        else:
            (
                this_month_cost,
                this_month_kwh_from_cost,
                this_month_by_day_from_cost,
                ladder_stage,
                ladder_remaining_kwh,
                ladder_tariff,
                ladder_start_date,
            ) = (
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
            )

        this_month_by_day, this_month_kwh = merge_by_day_data(
            by_day_from_usage=this_month_by_day_from_usage,
            kwh_from_usage=this_month_kwh_from_usage,
            by_day_from_cost=this_month_by_day_from_cost,
            kwh_from_cost=this_month_kwh_from_cost,
        )

        if this_month_by_day == STATE_UNAVAILABLE:
            self._if_update_last_month = True

        self._gathered_data[account.account_number][
            SUFFIX_THIS_MONTH_KWH
        ] = this_month_kwh
        self._gathered_data[account.account_number][
            SUFFIX_THIS_MONTH_COST
        ] = this_month_cost
        self._gathered_data[account.account_number][ATTR_KEY_THIS_MONTH_BY_DAY] = {
            ATTR_KEY_THIS_MONTH_BY_DAY: this_month_by_day
        }
        self._gathered_data[account.account_number][
            SUFFIX_CURRENT_LADDER
        ] = ladder_stage
        self._gathered_data[account.account_number][
            SUFFIX_CURRENT_LADDER_REMAINING_KWH
        ] = ladder_remaining_kwh
        self._gathered_data[account.account_number][
            SUFFIX_CURRENT_LADDER_TARIFF
        ] = ladder_tariff
        self._gathered_data[account.account_number][
            ATTR_KEY_CURRENT_LADDER_START_DATE
        ] = {ATTR_KEY_CURRENT_LADDER_START_DATE: ladder_start_date}

        self._this_month_update_completed_flag.set()

    async def _async_update_last_month_stats(
        self, account: CSGElectricityAccount
    ) -> None:
        """Update last month's usage and cost."""
        if not self._if_update_last_month:
            await self._this_month_update_completed_flag.wait()
            if not self._if_update_last_month:
                self._gathered_data[account.account_number][
                    SUFFIX_LAST_MONTH_KWH
                ] = STATE_UPDATE_UNCHANGED
                self._gathered_data[account.account_number][
                    SUFFIX_LAST_MONTH_COST
                ] = STATE_UPDATE_UNCHANGED
                self._gathered_data[account.account_number][
                    ATTR_KEY_LAST_MONTH_BY_DAY
                ] = {ATTR_KEY_LAST_MONTH_BY_DAY: STATE_UPDATE_UNCHANGED}
                return

        task_fetch_usage = asyncio.create_task(
            self._async_fetch(
                self._client.get_month_daily_usage_detail, account, self._last_month_ym
            )
        )
        task_fetch_cost = asyncio.create_task(
            self._async_fetch(
                self._client.get_month_daily_cost_detail, account, self._last_month_ym
            )
        )
        results = await asyncio.gather(task_fetch_usage, task_fetch_cost)
        (success_usage, result_usage), (success_cost, result_cost) = results

        if success_usage:
            last_month_kwh_from_usage, last_month_by_day_from_usage = result_usage
        else:
            last_month_kwh_from_usage = STATE_UNAVAILABLE
            last_month_by_day_from_usage = STATE_UNAVAILABLE

        if success_cost:
            (
                last_month_cost,
                last_month_kwh_from_cost,
                _,
                last_month_by_day_from_cost,
            ) = result_cost
            if not last_month_cost:
                last_month_cost = sum(
                    d[WF_ATTR_CHARGE] for d in last_month_by_day_from_cost
                )
            if not last_month_kwh_from_cost:
                last_month_kwh_from_cost = sum(
                    d[WF_ATTR_KWH] for d in last_month_by_day_from_cost
                )
        else:
            last_month_cost, last_month_kwh_from_cost, last_month_by_day_from_cost = (
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
                STATE_UNAVAILABLE,
            )

        last_month_by_day, last_month_kwh = merge_by_day_data(
            by_day_from_usage=last_month_by_day_from_usage,
            kwh_from_usage=last_month_kwh_from_usage,
            by_day_from_cost=last_month_by_day_from_cost,
            kwh_from_cost=last_month_kwh_from_cost,
        )

        self._gathered_data[account.account_number][
            SUFFIX_LAST_MONTH_KWH
        ] = last_month_kwh
        self._gathered_data[account.account_number][
            SUFFIX_LAST_MONTH_COST
        ] = last_month_cost
        self._gathered_data[account.account_number][ATTR_KEY_LAST_MONTH_BY_DAY] = {
            ATTR_KEY_LAST_MONTH_BY_DAY: last_month_by_day
        }

    def _update_latest_day(self, account: CSGElectricityAccount) -> None:
        """Derive latest-day values from this/last month daily data."""
        this_month_by_day = self._gathered_data[account.account_number][
            ATTR_KEY_THIS_MONTH_BY_DAY
        ][ATTR_KEY_THIS_MONTH_BY_DAY]
        last_month_by_day = self._gathered_data[account.account_number][
            ATTR_KEY_LAST_MONTH_BY_DAY
        ][ATTR_KEY_LAST_MONTH_BY_DAY]

        if (
            this_month_by_day == STATE_UNAVAILABLE
            and last_month_by_day == STATE_UNAVAILABLE
        ):
            latest_day_kwh = STATE_UNAVAILABLE
            latest_day_cost = STATE_UNAVAILABLE
            latest_day_date = STATE_UNAVAILABLE
        elif (
            this_month_by_day != STATE_UNAVAILABLE
            and isinstance(this_month_by_day, list)
            and len(this_month_by_day) >= 1
        ):
            latest_day_kwh = this_month_by_day[-1][WF_ATTR_KWH]
            latest_cost = this_month_by_day[-1].get(WF_ATTR_CHARGE)
            # Explicit None check: a legitimate 0 cost day must not be
            # reported as unavailable.
            latest_day_cost = (
                STATE_UNAVAILABLE if latest_cost is None else latest_cost
            )
            latest_day_date = this_month_by_day[-1][WF_ATTR_DATE]
        elif (
            last_month_by_day not in [STATE_UNAVAILABLE, STATE_UPDATE_UNCHANGED]
            and isinstance(last_month_by_day, list)
            and len(last_month_by_day) >= 1
        ):
            latest_day_kwh = last_month_by_day[-1][WF_ATTR_KWH]
            latest_day_cost = STATE_UNAVAILABLE
            latest_day_date = last_month_by_day[-1][WF_ATTR_DATE]
        else:
            _LOGGER.error(
                "Ele account %s, no latest day data available",
                account.account_number,
            )
            latest_day_kwh = STATE_UNAVAILABLE
            latest_day_cost = STATE_UNAVAILABLE
            latest_day_date = STATE_UNAVAILABLE

        self._gathered_data[account.account_number][
            SUFFIX_LATEST_DAY_KWH
        ] = latest_day_kwh
        self._gathered_data[account.account_number][
            SUFFIX_LATEST_DAY_COST
        ] = latest_day_cost
        self._gathered_data[account.account_number][ATTR_KEY_LATEST_DAY_DATE] = {
            ATTR_KEY_LATEST_DAY_DATE: latest_day_date
        }

    def _update_states(self) -> None:
        """Compute update policy based on current date."""
        current_dt = datetime.datetime.now()
        this_year, this_month, this_day = (
            current_dt.year,
            current_dt.month,
            current_dt.day,
        )
        last_year, last_month = this_year - 1, this_month - 1
        if last_month == 0:
            last_month_ym = (last_year, 12)
        else:
            last_month_ym = (this_year, last_month)

        self._this_day = this_day
        self._this_year = this_year
        self._this_month_ym = (this_year, this_month)
        self._last_year = last_year
        self._last_month_ym = last_month_ym

        last_update_day = self.hass.data.get(DOMAIN, {}).get(
            self._config_entry_id, {}
        ).get(DATA_KEY_LAST_UPDATE_DAY)
        if last_update_day is None:
            update_last_month = True
            update_last_year = True
        else:
            update_last_month = this_day <= SETTING_LAST_MONTH_UPDATE_DAY_THRESHOLD
            update_last_year = False
            if (
                this_month == 1
                and this_day <= SETTING_LAST_YEAR_UPDATE_DAY_THRESHOLD
                and last_update_day != this_day
            ):
                update_last_year = True

        self._if_update_last_month = update_last_month
        self._if_update_last_year = update_last_year

    async def _async_update_account_data(self, account: CSGElectricityAccount) -> None:
        """Fetch all data for one electricity account."""
        start_time = time.time()
        self._this_month_update_completed_flag.clear()
        await asyncio.gather(
            self._async_update_bal_arr(account),
            self._async_update_yesterday_kwh(account),
            self._async_update_this_year_stats(account),
            self._async_update_last_year_stats(account),
            self._async_update_this_month_stats_and_ladder(account),
            self._async_update_last_month_stats(account),
            return_exceptions=True,
        )
        try:
            self._update_latest_day(account)
        except Exception as exc:
            _LOGGER.error(
                "Ele account %s, update latest day data failed: %s",
                account.account_number,
                exc,
            )
        _LOGGER.debug(
            "Ele account %s, update took %s seconds",
            account.account_number,
            time.time() - start_time,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API for all configured accounts."""
        # Always read the latest entry data so that option changes and device
        # removals take effect without waiting for a full reload.
        self._config = dict(self._config_entry.data)
        self.update_interval = timedelta(
            seconds=self._config[CONF_SETTINGS][CONF_UPDATE_INTERVAL]
        )
        self._update_states()
        _LOGGER.debug("Coordinator update started")
        start_time = time.time()

        metering_point_data: dict[str, Any] = {}
        config_entry_need_update = False
        await self._async_refresh_client()
        new_config = dict(self._config)
        new_config[CONF_ELE_ACCOUNTS] = dict(self._config[CONF_ELE_ACCOUNTS])

        for account_number, account_data in self._config[CONF_ELE_ACCOUNTS].items():
            self._gathered_data[account_number] = {}
            account = CSGElectricityAccount.load(account_data)

            if not account.metering_point_number:
                if not metering_point_data:
                    ok, data = await self._async_fetch(
                        self._client.api_get_metering_point,
                        account.area_code,
                        account.ele_customer_id,
                    )
                    if ok:
                        metering_point_data = data
                if metering_point_data:
                    for mp in metering_point_data:
                        if mp["eleCustNumber"] == account.account_number:
                            config_entry_need_update = True
                            account.metering_point_number = mp.get(
                                "meteringPointNumber"
                            )
                            new_config[CONF_ELE_ACCOUNTS][
                                account_number
                            ] = account.dump()
                            break

            await self._async_update_account_data(account)

        if config_entry_need_update:
            new_config[CONF_UPDATED_AT] = str(int(time.time() * 1000))
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=new_config,
            )
            _LOGGER.debug("Updated accounts with metering point number")

        _LOGGER.debug("Coordinator update took %s seconds", time.time() - start_time)
        if DOMAIN in self.hass.data and self._config_entry_id in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][self._config_entry_id][
                DATA_KEY_LAST_UPDATE_DAY
            ] = self._this_day

        if self._login_expired:
            # The session died mid-cycle: trigger the reauth flow immediately
            # instead of waiting for the next polling round.
            raise ConfigEntryAuthFailed("Login expired")

        return self._gathered_data
