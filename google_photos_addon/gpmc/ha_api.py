import os
import requests
import logging
import time

class HAStatusReporter:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.supervisor_token = os.getenv("SUPERVISOR_TOKEN")
        self.last_update_time = 0.0
        self.min_update_interval = 10.0  # seconds
        
        if self.supervisor_token:
            self.api_url = "http://supervisor/core/api/states/sensor.gpmc_status"
            self.headers = {
                "Authorization": f"Bearer {self.supervisor_token}",
                "Content-Type": "application/json",
            }
            self.logger.info("Home Assistant Supervisor Token found. HA sensor reporting enabled.")
        else:
            self.logger.info("No SUPERVISOR_TOKEN found. HA sensor reporting disabled.")

    def update_state(self, state: str, attributes: dict = None, force: bool = False):
        if not self.supervisor_token:
            return

        current_time = time.time()
        # Only throttle 'Uploading' states, allow others (Idle, Error, Completed, etc.) to pass immediately
        if not force and state.startswith("Uploading") and (current_time - self.last_update_time) < self.min_update_interval:
            return

        self.last_update_time = current_time

        payload = {
            "state": state,
            "attributes": attributes or {}
        }
        
        # Add a friendly name, icon, and unique_id to the sensor
        payload["attributes"].setdefault("friendly_name", "Google Photos Upload Status")
        payload["attributes"].setdefault("icon", "mdi:google-photos")
        # Adding a unique_id might help some HA versions or configurations recognize the entity better
        payload["attributes"].setdefault("unique_id", "google_photos_mobile_client_status")

        try:
            response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Failed to update Home Assistant sensor: {e}")
