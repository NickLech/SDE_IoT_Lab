"""Data fusion (pure functions, no I/O): soil sensors + air temperature/humidity -> one view per zone, with VPD.

  Target formula (shown on the dashboard toolbar):
      es(T) = 0.6108 * exp(17.27 * T / (T + 237.3))      saturation vapour pressure, kPa
      VPD   = es(T) * (1 - RH / 100)                     vapour pressure deficit, kPa
"""
import math
import statistics

from components.config import (AIR_STALE_AFTER_S, SENSOR_IDS, STALE_AFTER_S, SUSPECT_DELTA,
                               VPD_HIGH, VPD_LOW, VPD_OK, VPD_STRESS, ZONES)


# ------------------------------------------------------------------------------------- VPD
# Exercise 3 — Data fusion (VPD)
# Target model (also shown in the dashboard toolbar, "Irrigation model"):
#     es(T) = 0.6108 * exp(17.27 * T / (T + 237.3))   [kPa]  saturation vapour pressure
#     VPD   = es(T) * (1 - RH / 100)                  [kPa]
# TODO: replace the placeholder with that model: compute es(T) from `t_c` (math.exp is
#       already imported), then subtract the actual vapour pressure of the air, es(T) * rh / 100.
# Hint: the placeholder ignores `t_c` entirely — it is humidity-only, so it keeps the
#       dashboard working (VPD fact + band) until the exercise is done.
# Done when: the VPD fact changes with the air temperature, e.g. T = 25 °C and RH = 50 %
#            -> 1.584 kPa (the placeholder gives 1.000 kPa).
def vpd_kpa(t_c, rh):
    """Vapor pressure deficit (kPa). PLACEHOLDER: humidity only, temperature ignored."""
    return max(0.0, 2.0 * (1 - rh / 100))


def vpd_band(vpd):
    """"Qualitative band for a VPD value (kPa), using the thresholds from config.py.

    < VPD_LOW 0.4        -> too humid ("low")
    0.4 .. 0.8           -> ok
    0.8 .. 1.2           -> optimal
    1.2 .. 1.6           -> ok
    > 1.6                -> too dry ("stress")
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
            kpa = vpd_kpa(t, rh)
            vpd = {"kpa": round(kpa, 3), "band": vpd_band(kpa)}

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
