"""The China Southern Power Grid integration."""

from __future__ import annotations

import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry
from homeassistant.helpers.device_registry import DeviceEntry
from requests import RequestException

from .api import CSGClient, CSGAPIError
from .const import (
    CONF_AUTH_TOKEN,
    CONF_ELE_ACCOUNTS,
    CONF_LOGIN_TYPE,
    CONF_UPDATED_AT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CSG from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = CSGClient.load({CONF_AUTH_TOKEN: entry.data[CONF_AUTH_TOKEN]})

    def verify() -> bool:
        return client.verify_login()

    try:
        logged_in = await hass.async_add_executor_job(verify)
    except (RequestException, CSGAPIError) as err:
        # Temporary network/server problems must trigger a retry instead of
        # failing the entry setup permanently (e.g. HA starts before network
        # is ready).
        raise ConfigEntryNotReady(f"Cannot reach CSG servers: {err}") from err

    if not logged_in:
        raise ConfigEntryAuthFailed("Login expired")

    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry: %s", entry.title)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    _LOGGER.debug(
        "Unload platforms for entry: %s, success: %s", entry.title, unload_ok
    )
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Remove a single electricity account device."""
    if not device_entry.identifiers:
        _LOGGER.warning(
            "Device %s has no identifiers, skip removing", device_entry.name
        )
        return True

    account_num = list(device_entry.identifiers)[0][1]
    _LOGGER.info("Removing device %s", device_entry.name)

    entity_reg = entity_registry.async_get(hass)
    entities = {
        ent.unique_id: ent.entity_id
        for ent in entity_registry.async_entries_for_config_entry(
            entity_reg, config_entry.entry_id
        )
        if account_num in ent.unique_id
    }
    for entity_id in entities.values():
        entity_reg.async_remove(entity_id)

    if account_num in config_entry.data.get(CONF_ELE_ACCOUNTS, {}):
        accounts = dict(config_entry.data[CONF_ELE_ACCOUNTS])
        accounts.pop(account_num, None)
        new_data = dict(config_entry.data)
        new_data[CONF_ELE_ACCOUNTS] = accounts
        new_data[CONF_UPDATED_AT] = str(int(time.time() * 1000))
        hass.config_entries.async_update_entry(config_entry, data=new_data)

        # Reload the entry so the running coordinator stops polling the
        # removed account and recreates the data without it.
        hass.async_create_task(
            hass.config_entries.async_reload(config_entry.entry_id)
        )

    _LOGGER.info(
        "Removed ele account from %s: %s",
        config_entry.data.get(CONF_USERNAME),
        account_num,
    )
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Logout when the integration is removed."""
    _LOGGER.info("Removing entry: account %s", entry.data[CONF_USERNAME])

    def client_logout() -> None:
        client = CSGClient.load({CONF_AUTH_TOKEN: entry.data[CONF_AUTH_TOKEN]})
        try:
            if client.verify_login():
                client.logout(entry.data[CONF_LOGIN_TYPE])
                _LOGGER.info("CSG account %s logged out", entry.data[CONF_USERNAME])
        except (RequestException, CSGAPIError) as err:
            _LOGGER.warning(
                "Could not log out CSG account %s: %s",
                entry.data[CONF_USERNAME],
                err,
            )

    await hass.async_add_executor_job(client_logout)
