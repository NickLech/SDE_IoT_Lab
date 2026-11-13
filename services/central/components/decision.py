"""Irrigation decision for one zone (pure function, no I/O).

  threshold = SOIL_DRY_BASE + VPD_GAIN * (VPD - VPD_REF)   -> the drier the air, the earlier we irrigate
  duration  = IRRIGATION_S * (1 + max(0, VPD - VPD_REF))   -> ... and the longer
Without VPD it falls back to SOIL_DRY_BASE; without a valid soil reading it never irrigates (fail-safe).
A manual command (no "source": "central") bypasses every rule while it lasts.
"""
import math

from components.config import (COOLDOWN_S, IRRIGATION_S, SOIL_DRY_BASE, SOIL_STOP, SPRINKLER_MAX_S, VPD_GAIN,
                               VPD_REF)


def soil_threshold(kpa):
    if kpa is None:
        return SOIL_DRY_BASE
    return min(95.0, max(5.0, SOIL_DRY_BASE + VPD_GAIN * (kpa - VPD_REF)))


def decide(zone, view, now, mqtt_up, last_cmd):
    """Returns (action, reason, soil_threshold, duration_s); action is "on", "off" or None.
    last_cmd: zone -> monotonic time of the last command (ours or manual), used for the cooldown."""
    soil_v = view["soil"]["median"]
    kpa = view["vpd"]["kpa"] if view["vpd"] else None
    thr = soil_threshold(kpa)
    sp_state = view["sprinkler"]["state"]

    if not mqtt_up:
        return None, "MQTT disconnected: no commands", thr, None
    if view["sprinkler"]["manual"]:
        return None, "manual command active: rules bypassed", thr, None
    if soil_v is None:
        return None, "no valid soil reading: not irrigating", thr, None
    if sp_state == "on":
        if view["rain"] == "on":
            return "off", "raining: stop", thr, None
        if soil_v >= SOIL_STOP:
            return "off", f"soil {soil_v:.0f}% >= stop level {SOIL_STOP:.0f}%", thr, None
        return None, "sprinkler already on", thr, None
    if sp_state != "off":
        return None, f"sprinkler {sp_state}: no commands", thr, None
    if view["rain"] == "on":
        return None, "raining: not irrigating", thr, None
    if soil_v >= thr:
        return None, f"soil {soil_v:.0f}% >= threshold {thr:.0f}%", thr, None
    wait = COOLDOWN_S - (now - last_cmd.get(zone, -math.inf))
    if wait > 0:
        return None, f"soil {soil_v:.0f}% < threshold {thr:.0f}%, cooldown ({wait:.0f}s left)", thr, None
    duration = IRRIGATION_S if kpa is None else IRRIGATION_S * (1 + max(0.0, kpa - VPD_REF))
    duration = min(SPRINKLER_MAX_S, duration)
    basis = "soil only, no VPD" if kpa is None else f"VPD {kpa:.2f} kPa"
    return "on", f"soil {soil_v:.0f}% < threshold {thr:.0f}% ({basis})", thr, duration
