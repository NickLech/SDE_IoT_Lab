from __future__ import annotations

from datetime import datetime

from core import SENSOR_IDS, history, lock

VPD_TEXT = {"low": "too humid", "ok": "ok", "optimal": "optimal", "stress": "too dry"}


# ---- text ------------------------------------------------------------------

def air_text(info):
    air = info.get("air") or {}
    t, rh = air.get("temperature"), air.get("humidity")
    if t is None and rh is None:
        return "missing"
    if t is None:
        return f"{rh:.0f}% RH, temp missing"
    if rh is None:
        return f"{t:.1f}°C, humidity missing"
    return f"{t:.1f}°C, {rh:.0f}% RH"


def vpd_text(info):
    vpd = info.get("vpd")
    if not vpd or vpd.get("kpa") is None:
        return "– (no air reading)"
    band = vpd.get("band", "unknown")
    return f"{vpd['kpa']:.2f} kPa ({VPD_TEXT.get(band, band)})"


def command_text(info):
    last = info.get("last_command")
    if not last:
        return "none"
    parts = [last.get("action", "?")]
    if last.get("duration_s") is not None:
        parts.append(f"{last['duration_s']}s")
    parts.append(str(last.get("at")))
    return " · ".join(parts)


def spread_text(info):
    sensors = (info.get("sensors") or {}).values()
    vals = [s["value"] for s in sensors
            if s.get("state") == "online" and s.get("value") is not None]
    text = f"± {(max(vals) - min(vals)) / 2:.1f}%" if len(vals) > 1 else "–"
    suspects = sum(1 for s in sensors if s.get("suspect"))
    return text + (f" ({suspects} suspect/s)" if suspects else " (no suspects)")


def decision_info(info):
    """Return (status word, muted detail, alert color, pulse) for the decision row.

    Irrigating is the *live* sprinkler state, not the instantaneous command: central's
    decide() returns action="on" only on the one tick it fires the command, then keeps
    the sprinkler running with action=None, so we must key off sprinkler.state too.
    """
    d = info.get("decision") or {}
    action, reason, thr = d.get("action"), d.get("reason"), d.get("soil_threshold")
    running = (info.get("sprinkler") or {}).get("state") == "on"
    if action == "off":
        # a stop the controller just commanded (rain / stop level) outranks the still-open valve
        return "Stopped", reason, "gray", False
    if running or action == "on":
        detail = f"soil below {thr:.0f}%" if thr is not None else reason
        return "Irrigating", detail, "blue", True
    if thr is not None:
        return "Hold", f"irrigate below {thr:.0f}%", "gray", False
    return "Idle", (str(reason) if reason else "no decision yet"), "gray", False


def sprinkler_state(info):
    """(color, variant, pulse) for the SPRINKLER badge, from the live valve state."""
    if (info.get("sprinkler") or {}).get("state") == "on":
        return "blue", "dot", True
    return "gray", "dot", False


# ---- charts ----------------------------------------------------------------

def chart_series(zone):
    sensors = [{"name": f"s{i}", "color": "gray.5", "type": "line"}
               for i in range(1, len(SENSOR_IDS[zone]) + 1)]
    return [{"name": "median", "color": "blue.6", "type": "area"}] + sensors


def chart_props(zone):
    """Return (data, referenceLines, referenceAreas) for the zone chart."""
    with lock:
        pts = list(history.get(zone, []))

    names = {sid: f"s{i}" for i, sid in enumerate(SENSOR_IDS[zone], 1)}
    data, times, on_flags = [], [], []
    for p in pts:
        t = datetime.fromtimestamp(p["t"]).strftime("%H:%M:%S")
        row = {"t": t, "median": p["median"]}
        row.update({name: p["s"].get(sid) for sid, name in names.items()})
        data.append(row)
        times.append(t)
        on_flags.append(p["on"])

    # One shaded band per contiguous sprinkler-ON stretch; an ongoing stretch
    # reaches the latest sample. Reference areas render behind the series.
    areas, start = [], None
    for idx, (t, on) in enumerate(zip(times, on_flags)):
        if on and start is None:
            start = t
        elif not on and start is not None:
            areas.append({"x1": start, "x2": times[idx - 1], "color": "blue.1"})
            start = None
    if start is not None:
        areas.append({"x1": start, "x2": times[-1], "color": "blue.1"})

    thr = pts[-1]["thr"] if pts else None
    lines = [{"y": thr, "color": "orange.6"}] if thr is not None else []
    return data, lines, areas[-6:]


# ---- health (every online/offline status lives here) -----------------------

def _soil_online(info):
    return sum(1 for s in (info.get("sensors") or {}).values() if s.get("state") == "online")


def health_checks(zone_ids, info, central_up, mqtt_up):
    """Return [(label, ok, detail)]; the header shows LIVE only if all are ok."""
    n = len(zone_ids)
    rows = [
        ("Central (HTTP pull)", central_up, "connected" if central_up else "unreachable"),
        ("Broker (MQTT subscribe)", mqtt_up, "connected" if mqtt_up else "disconnected"),
    ]

    soil_bad = [f"{z} {_soil_online(info(z))}/{len(SENSOR_IDS[z])}" for z in zone_ids if _soil_online(info(z)) < len(SENSOR_IDS[z])]
    total = sum(len(SENSOR_IDS[z]) for z in zone_ids)
    online = sum(_soil_online(info(z)) for z in zone_ids)
    rows.append(("Soil sensors (MQTT push)", not soil_bad, f"{online} of {total} online" + (f" [{', '.join(soil_bad)}]" if soil_bad else "")))

    def per_zone(label, ok):
        bad = [z for z in zone_ids if not ok(info(z))]
        text = f"{n - len(bad)} of {n} online" + (f" [{', '.join(bad)}]" if bad else "")
        rows.append((label, not bad, text))

    per_zone("Temperature (HTTP pull)", lambda i: (i.get("air") or {}).get("temperature") is not None)
    per_zone("Humidity (HTTP pull)", lambda i: (i.get("air") or {}).get("humidity") is not None)
    per_zone("Sprinklers (MQTT push)", lambda i: (i.get("sprinkler") or {}).get("state") in ("on", "off"))
    per_zone("Rain (MQTT push)", lambda i: i.get("rain") in ("on", "off"))
    return rows
