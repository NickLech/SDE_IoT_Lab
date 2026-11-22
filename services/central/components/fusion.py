import math
import statistics

from components.config import AIR_STALE_AFTER_S, SENSOR_IDS, STALE_AFTER_S, SUSPECT_DELTA, VPD_HIGH, VPD_LOW, VPD_OK, VPD_STRESS, ZONES

# Readings outside these limits are discarded as implausible.
TEMPERATURE_LIMITS = (-40, 60)      # °C
HUMIDITY_LIMITS = (0, 100)          # %RH


# ---- VPD -----------------------------------------------------------------------

# Exercise 3 - Data fusion (VPD)
# TODO: replace the es placeholder with the actual formula.
# Hint: the formula is avaialble in the dashboard's "Irrigation model" panel.
def vpd_kpa(t_c, rh):
    """Return the vapour pressure deficit in kPa. PLACEHOLDER: humidity only."""
    es = 2.0      # TODO: add your code here
    return max(0.0, es * (1 - rh / 100))


def vpd_band(vpd):
    """Return the qualitative band of a VPD value (kPa), using the thresholds in config.py.

        below VPD_LOW (0.4)      "low"      too humid
        below VPD_OK (0.8)       "ok"
        up to VPD_HIGH (1.2)     "optimal"
        up to VPD_STRESS (1.6)   "ok"
        above                    "stress"   too dry
    """
    if vpd < VPD_LOW:
        return "low"
    if vpd < VPD_OK:
        return "ok"
    if vpd <= VPD_HIGH:
        return "optimal"
    if vpd <= VPD_STRESS:
        return "ok"
    return "stress"


# ---- per-zone fusion -----------------------------------------------------------

def fresh(store, zone, lo, hi, now):
    """Return the median of the zone's recent samples within [lo, hi], or None.

    The median rejects isolated spikes (the temperature service injects them on purpose).
    """
    samples = [v for v, t in store.get(zone, ()) if now - t <= AIR_STALE_AFTER_S and lo <= v <= hi]
    return round(statistics.median(samples), 2) if samples else None


def build_view(now, soil_c, status_c, temp_c, humid_c, sprinkler_c, sprinkler_status_c,
               rain_c, manual_c):
    """Fuse the raw state into one dict per zone (soil, air, VPD, sprinkler, rain)."""
    zones = {}
    for zone in ZONES:
        sensors, median, valid = _soil_view(zone, now, soil_c, status_c)
        air, vpd = _air_view(zone, now, temp_c, humid_c)
        zones[zone] = {
            "soil": {"median": None if median is None else round(median, 1),
                     "valid": valid, "expected": len(SENSOR_IDS[zone])},
            "air": air,
            "vpd": vpd,
            "sprinkler": _sprinkler_view(zone, now, sprinkler_c, sprinkler_status_c, manual_c),
            "rain": rain_c.get(zone) or "unknown",
            "sensors": sensors,
        }
    return zones


def _is_percentage(value):
    return 0 <= value <= 100


def _soil_view(zone, now, soil_c, status_c):
    """Return (sensors, median, number of valid readings) for the zone's soil sensors."""
    sensors = {}
    for sid in SENSOR_IDS[zone]:
        reading = soil_c.get((zone, sid))
        age = now - reading[1] if reading else None
        offline = status_c.get((zone, sid)) == "offline" or reading is None or age > STALE_AFTER_S
        sensors[sid] = {"state": "offline" if offline else "online",
                        "value": reading[0] if reading else None, "age_s": age}

    valid = [s["value"] for s in sensors.values()
             if s["state"] == "online" and _is_percentage(s["value"])]
    median = statistics.median(valid) if valid else None

    for sensor in sensors.values():
        sensor["suspect"] = sensor["state"] == "online" and _is_suspect(sensor["value"], median)
        sensor["age_s"] = None if sensor["age_s"] is None else round(sensor["age_s"], 1)
    return sensors, median, len(valid)


def _is_suspect(value, median):
    """A reading is suspect if it is not a percentage or is far from the zone median."""
    if not _is_percentage(value):
        return True
    return median is not None and abs(value - median) > SUSPECT_DELTA


def _air_view(zone, now, temp_c, humid_c):
    """Return (air readings, VPD) for the zone; the VPD needs both readings."""
    temperature = fresh(temp_c, zone, *TEMPERATURE_LIMITS, now)
    humidity = fresh(humid_c, zone, *HUMIDITY_LIMITS, now)
    vpd = None
    if temperature is not None and humidity is not None:
        kpa = vpd_kpa(temperature, humidity)
        vpd = {"kpa": round(kpa, 3), "band": vpd_band(kpa)}
    return {"temperature": temperature, "humidity": humidity}, vpd


def _sprinkler_view(zone, now, sprinkler_c, sprinkler_status_c, manual_c):
    sprinkler = sprinkler_c[zone]
    # An explicit "offline" wins: the last retained on/off state can outlive the device.
    if sprinkler_status_c.get(zone) == "offline":
        state = "offline"
    else:
        state = sprinkler["state"] or "unknown"
    remaining = None
    if state == "on" and sprinkler["until"]:
        remaining = max(0.0, sprinkler["until"] - now)
    return {"state": state,
            "remaining_s": None if remaining is None else round(remaining, 1),
            "manual": manual_c.get(zone, -math.inf) > now}