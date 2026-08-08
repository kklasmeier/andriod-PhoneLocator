"""Analytics tuning constants (configurable via environment)."""

import os

STATIONARY_RADIUS_M = float(os.environ.get("PHONE_LOCATOR_STATIONARY_RADIUS_M", "100"))
STATIONARY_SPEED_MPS = float(os.environ.get("PHONE_LOCATOR_STATIONARY_SPEED_MPS", "1.0"))
PLACE_CLUSTER_RADIUS_M = float(os.environ.get("PHONE_LOCATOR_PLACE_CLUSTER_RADIUS_M", "100"))
