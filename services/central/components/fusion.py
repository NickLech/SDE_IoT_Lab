"""Data fusion (pure functions, no I/O): soil sensors + air temperature/humidity -> one view per zone, with VPD.

  VPD = SVP(leaf) - SVP(air) * RH/100        (kPa, Tetens/Magnus formula)
"""
import math
import statistics

from components.config import (AIR_STALE_AFTER_S, LEAF_TEMP_OFFSET, SENSOR_IDS, STALE_AFTER_S, SUSPECT_DELTA,
                               VPD_HIGH, VPD_LOW, VPD_OK, VPD_STRESS, ZONES)


# ------------------------------------------------------------------------------------- VPD
def svp_kpa(t_c):
    """Saturation vapor pressure (kPa), Tetens/Magnus formula."""
    return 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3))


def vpd_kpa(t_c, rh, leaf_offset=0.0):
    """Vapor pressure deficit (kPa) = SVP(leaf) - actual vapor pressure of the air."""
    return max(0.0, svp_kpa(t_c - leaf_offset) - svp_kpa(t_c) * rh / 100)


def vpd_band(vpd):          
    """ This only says that these are the values:  
                                                < 0.4 kPa (too humid)
                                                0.4 to 0.8 kPa   &  1.2 to 1.6 kPa (ok)
                                                0.8 to 1.2 kPa (optimal)
                                                > 1.6 kPa (too dry)
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


# ------------------------------------------------------------------------- per-zone fusion
def fresh(store, zone, lo, hi, now):
    """Air value used for the fusion: median of the recent, plausible samples of the zone, else None.
    The median rejects an isolated spike (the temperature service injects them on purpose)."""
    samples = [v for v, t in store.get(zone, ()) if now - t <= AIR_STALE_AFTER_S and lo <= v <= hi]
    return round(statistics.median(samples), 2) if samples else None


def build_view(now, soil_c, status_c, temp_c, humid_c, sprinkler_c, sprinkler_status_c, rain_c, manual_c):
    """Turns the raw state into one dict per zone (soil + air + VPD + sprinkler + rain)."""
    zones = {}
    for zone in ZONES:
        sensors = {}
        for sid in SENSOR_IDS[zone]:
            reading = soil_c.get((zone, sid))
            age = now - reading[1] if reading else None
            offline = status_c.get((zone, sid)) == "offline" or reading is None or age > STALE_AFTER_S
            sensors[sid] = {"state": "offline" if offline else "online",
                            "value": reading[0] if reading else None, "age_s": age}

        valid = [s["value"] for s in sensors.values() if s["state"] == "online" and 0 <= s["value"] <= 100]
        median = statistics.median(valid) if valid else None
        for s in sensors.values():
            s["suspect"] = s["state"] == "online" and (
                not 0 <= s["value"] <= 100 or (median is not None and abs(s["value"] - median) > SUSPECT_DELTA))
            s["age_s"] = None if s["age_s"] is None else round(s["age_s"], 1)

        t, rh = fresh(temp_c, zone, -40, 60, now), fresh(humid_c, zone, 0, 100, now)
        vpd = None
        if t is not None and rh is not None:
            kpa = vpd_kpa(t, rh, LEAF_TEMP_OFFSET)
            vpd = {"kpa": round(kpa, 3), "band": vpd_band(kpa), "leaf_offset_c": LEAF_TEMP_OFFSET}

        sp = sprinkler_c[zone]
        # Liveness wins over the last retained on/off: the device may be gone while its last state
        # lingers (retained) on the broker. Only an explicit "offline" marks it gone.
        sp_state = "offline" if sprinkler_status_c.get(zone) == "offline" else (sp["state"] or "unknown")
        remaining = max(0.0, sp["until"] - now) if sp_state == "on" and sp["until"] else None
        zones[zone] = {
            "soil": {"median": None if median is None else round(median, 1),
                     "valid": len(valid), "expected": len(SENSOR_IDS[zone])},
            "air": {"temperature": t, "humidity": rh},
            "vpd": vpd,
            "sprinkler": {"state": sp_state,
                          "remaining_s": None if remaining is None else round(remaining, 1),
                          "manual": manual_c.get(zone, -math.inf) > now},
            "rain": rain_c.get(zone) or "unknown",
            "sensors": sensors,
        }
    return zones
