"""Pytest configuration for the csg_power test suite.

Two tiers of stubs are provided when Home Assistant is not installed:

1. Structured stubs for the symbols the integration's *logic* depends on
   (coordinator/entity base classes with real ``__init__`` signatures, and
   real constant values such as ``STATE_UNAVAILABLE``). These are required
   because ``MagicMock`` instances cannot be used as class bases, and logic
   tests need real sentinel values.
2. ``MagicMock`` fallbacks for any remaining Home Assistant modules, so that
   merely importing the package never fails.

The tested code paths never call into these stubs beyond attribute storage.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    importlib.import_module("homeassistant")
    _HA_AVAILABLE = True
except ModuleNotFoundError:
    _HA_AVAILABLE = False

if not _HA_AVAILABLE:

    def _module(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    # --- homeassistant (package root) -------------------------------------
    ha_pkg = _module("homeassistant")
    ha_pkg.__path__ = []  # type: ignore[attr-defined]

    # --- homeassistant.const (real values) --------------------------------
    const_mod = _module("homeassistant.const")
    const_mod.CONF_USERNAME = "username"
    const_mod.STATE_UNAVAILABLE = "unavailable"

    class _UnitOfEnergy:
        KILO_WATT_HOUR = "kWh"

    class _UnitOfCurrency:
        CNY = "CNY"

    class _Platform:
        SENSOR = "sensor"

    const_mod.UnitOfEnergy = _UnitOfEnergy
    const_mod.UnitOfCurrency = _UnitOfCurrency
    const_mod.Platform = _Platform

    # --- homeassistant.core ------------------------------------------------
    core_mod = _module("homeassistant.core")

    def _callback(func):
        return func

    class _HomeAssistant:
        pass

    core_mod.callback = _callback
    core_mod.HomeAssistant = _HomeAssistant

    # --- homeassistant.exceptions ------------------------------------------
    exc_mod = _module("homeassistant.exceptions")

    class _ConfigEntryAuthFailed(Exception):
        pass

    class _ConfigEntryNotReady(Exception):
        pass

    class _ConfigEntryError(Exception):
        pass

    exc_mod.ConfigEntryAuthFailed = _ConfigEntryAuthFailed
    exc_mod.ConfigEntryNotReady = _ConfigEntryNotReady
    exc_mod.ConfigEntryError = _ConfigEntryError

    # --- homeassistant.helpers.update_coordinator ---------------------------
    uc_mod = _module("homeassistant.helpers.update_coordinator")

    class _DataUpdateCoordinator:
        def __init__(self, hass, logger, *, name=None, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval

    class _CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    uc_mod.DataUpdateCoordinator = _DataUpdateCoordinator
    uc_mod.CoordinatorEntity = _CoordinatorEntity

    # --- homeassistant.components.sensor ------------------------------------
    sensor_mod = _module("homeassistant.components.sensor")

    class _SensorDeviceClass:
        ENERGY = "energy"
        MONETARY = "monetary"

    class _SensorStateClass:
        TOTAL = "total"
        MEASUREMENT = "measurement"

    class _SensorEntity:
        def __init__(self):
            pass

        def async_write_ha_state(self):
            pass

    sensor_mod.SensorDeviceClass = _SensorDeviceClass
    sensor_mod.SensorStateClass = _SensorStateClass
    sensor_mod.SensorEntity = _SensorEntity

    # --- homeassistant.helpers.entity ---------------------------------------
    entity_mod = _module("homeassistant.helpers.entity")

    class _DeviceInfo(dict):
        pass

    entity_mod.DeviceInfo = _DeviceInfo

    # --- homeassistant.helpers.entity_platform ------------------------------
    ep_mod = _module("homeassistant.helpers.entity_platform")
    ep_mod.AddEntitiesCallback = object

    # --- other modules referenced only by type annotations / imports --------
    for name, attr_targets in {
        "homeassistant.config_entries": ["ConfigEntry", "ConfigFlow", "OptionsFlow"],
        "homeassistant.data_entry_flow": ["FlowResult"],
        "homeassistant.helpers.device_registry": ["DeviceEntry"],
        "homeassistant.util": [],
    }.items():
        mod = _module(name)
        for attr in attr_targets:
            setattr(mod, attr, object)

    # helpers needs to be importable as a package with submodules
    helpers_mod = _module("homeassistant.helpers")
    helpers_mod.__path__ = []  # type: ignore[attr-defined]
    helpers_mod.entity_registry = MagicMock(name="entity_registry")
    sys.modules.setdefault(
        "homeassistant.helpers.entity_registry", helpers_mod.entity_registry
    )

    # MagicMock fallbacks for anything not structured above
    for name in (
        "homeassistant.components",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.util.dt",
    ):
        sys.modules.setdefault(name, MagicMock())
