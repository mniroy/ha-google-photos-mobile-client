import os
import requests
import logging

class HAStatusReporter:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.supervisor_token = os.getenv("SUPERVISOR_TOKEN")
        
        if self.supervisor_token:
            self.api_url = "http://supervisor/core/api/states/sensor.gpmc_status"
            self.headers = {
                "Authorization": f"Bearer {self.supervisor_token}",
                "Content-Type": "application/json",
            }
            self.logger.info("Home Assistant Supervisor Token found. HA sensor reporting enabled.")
        else:
            self.logger.info("No SUPERVISOR_TOKEN found. HA sensor reporting disabled.")

    def update_state(self, state: str, attributes: dict = None):
        if not self.supervisor_token:
            return

        payload = {
            "state": state,
            "attributes": attributes or {}
        }
        
        # Add a friendly name and icon to the sensor
        payload["attributes"].setdefault("friendly_name", "Google Photos Upload Status")
        payload["attributes"].setdefault("icon", "mdi:google-photos")

        try:
            response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Failed to update Home Assistant sensor: {e}")
