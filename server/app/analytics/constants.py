"""Analytics tuning constants (configurable via environment)."""

import os

STATIONARY_RADIUS_M = float(os.environ.get("PHONE_LOCATOR_STATIONARY_RADIUS_M", "100"))
STATIONARY_SPEED_MPS = float(os.environ.get("PHONE_LOCATOR_STATIONARY_SPEED_MPS", "1.0"))
PLACE_CLUSTER_RADIUS_M = float(os.environ.get("PHONE_LOCATOR_PLACE_CLUSTER_RADIUS_M", "50"))

# Timeline / places presentation (raw location_points are never modified)
PLACE_MERGE_RADIUS_M = float(os.environ.get("PHONE_LOCATOR_PLACE_MERGE_RADIUS_M", "50"))
MIN_VISIT_PRESENTATION_SEC = int(os.environ.get("PHONE_LOCATOR_MIN_VISIT_SEC", "300"))
MIN_TRAVEL_PRESENTATION_SEC = int(os.environ.get("PHONE_LOCATOR_MIN_TRAVEL_SEC", "180"))
MIN_TRAVEL_PRESENTATION_M = float(os.environ.get("PHONE_LOCATOR_MIN_TRAVEL_M", "200"))
# Travel between visits at the same named place below this distance is parking/GPS drift.
SAME_PLACE_LOCAL_MAX_M = float(os.environ.get("PHONE_LOCATOR_SAME_PLACE_LOCAL_M", "800"))
