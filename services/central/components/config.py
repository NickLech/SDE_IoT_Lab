"""Configuration: every tunable value comes from an environment variable (see docker-compose.yml)."""
import os

# ---- connections
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
# One temperature/humidity sensor per zone container: "{zone}" is replaced by the zone name
# (e.g. http://zone1:5001). A URL without "{zone}" still works (single shared service).
TEMPERATURE_URL = os.environ.get("TEMPERATURE_URL", "http://{zone}:5001").rstrip("/")
HUMIDITY_URL = os.environ.get("HUMIDITY_URL", "http://{zone}:5002").rstrip("/")
PORT = int(os.environ.get("PORT", 5000))                                      # HTTP API read by the dashboard

# ---- field layout
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
SENSORS_PER_ZONE = int(os.environ.get("SENSORS_PER_ZONE", 3))
SENSOR_IDS = {z: [f"soil-{z}-{i}" for i in range(1, SENSORS_PER_ZONE + 1)] for z in ZONES}

# ---- timing / data quality
POLL_INTERVAL_S = float(os.environ.get("POLL_INTERVAL_S", 5))
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", 1.5))
TICK_S = float(os.environ.get("TICK_S", 1))                                   # fusion + decision cycle
STALE_AFTER_S = float(os.environ.get("STALE_AFTER_S", 8))                     # soil sensor silent -> offline
AIR_STALE_AFTER_S = float(os.environ.get("AIR_STALE_AFTER_S", 3 * POLL_INTERVAL_S))   # air value too old -> unusable
SUSPECT_DELTA = float(os.environ.get("SUSPECT_DELTA", 15))                    # distance from zone median (%)
AIR_WINDOW = int(os.environ.get("AIR_WINDOW", 3))                             # last N air samples -> median (spike filter)

# ---- VPD
VPD_LOW = float(os.environ.get("VPD_LOW", 0.4))
VPD_OK = float(os.environ.get("VPD_OK", 0.8))
VPD_HIGH = float(os.environ.get("VPD_HIGH", 1.2))
VPD_STRESS = float(os.environ.get("VPD_STRESS", 1.6))
LEAF_TEMP_OFFSET = float(os.environ.get("LEAF_TEMP_OFFSET", 0))               # leaf is this many degC colder than air

# ---- irrigation decision
SOIL_DRY_BASE = float(os.environ.get("SOIL_DRY_BASE", 35))                    # % : irrigate below this (VPD = VPD_REF)
SOIL_STOP = float(os.environ.get("SOIL_STOP", 70))                            # % : stop irrigating above this
VPD_REF = float(os.environ.get("VPD_REF", 0.8))
VPD_GAIN = float(os.environ.get("VPD_GAIN", 15))                              # % of threshold per kPa of VPD
IRRIGATION_S = float(os.environ.get("IRRIGATION_S", 20))
SPRINKLER_DEFAULT_S = float(os.environ.get("SPRINKLER_DEFAULT_S", 30))        # same as the sprinkler service
SPRINKLER_MAX_S = float(os.environ.get("SPRINKLER_MAX_S", 120))               # cap on our own commands
COOLDOWN_S = float(os.environ.get("COOLDOWN_S", 60))                          # min time between two commands per zone
