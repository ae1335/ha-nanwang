"""Pytest configuration for the csg_power test suite.

The tests target the Home-Assistant-independent parts of the integration
(``api`` and ``utils``). Importing them still executes the package
``__init__``, which imports Home Assistant. When HA is not installed (plain
CI environment), lightweight stub modules are injected so the package
initializes; the stubs are never exercised by the tested code paths.
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
    ha_pkg = types.ModuleType("homeassistant")
    ha_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["homeassistant"] = ha_pkg
    for _name in (
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.core",
        "homeassistant.data_entry_flow",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.util",
    ):
        sys.modules.setdefault(_name, MagicMock())
