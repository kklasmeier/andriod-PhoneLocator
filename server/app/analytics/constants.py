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

# 1 mph in meters per second. Trip mode uses these cuts, not the phone activity field.
MPH_IN_MPS = 1609.344 / 3600
WALK_SPEED_MPS = 2 * MPH_IN_MPS
RUN_SPEED_MPS = 4.5 * MPH_IN_MPS
VEHICLE_SPEED_MPS = 12 * MPH_IN_MPS
# A single short GPS jump is not a drive. A stretch is two fast legs, or 80 m of them.
VEHICLE_STRETCH_MIN_LEGS = 2
VEHICLE_STRETCH_MIN_M = 80.0
VEHICLE_NEIGHBOR_GAP_SEC = 30 * 60
MOTION_LEG_MAX_GAP_SEC = 600
