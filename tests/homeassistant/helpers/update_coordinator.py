"""Minimal stub for homeassistant.helpers.update_coordinator."""


class UpdateFailed(Exception):
    """Raised when a coordinator update fails."""


class DataUpdateCoordinator:
    """Minimal stub."""

    def __class_getitem__(cls, item):
        """Allow DataUpdateCoordinator[T] generic syntax."""
        return cls

    def __init__(self, hass, logger, *, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None
