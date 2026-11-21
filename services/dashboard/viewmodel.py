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


# ---- temperature line gradient (assignment panel) --------------------------

# fixed color thresholds (°C -> color); hex values of red.6 / orange.6 / yellow.5
# / lime.5 / cyan.5 / blue.5 (Mantine palette)
TEMP_STOP_TABLE = [(30, "#fa5252"), (25, "#fd7e14"), (20, "#fab005"),
                   (15, "#94d82d"), (10, "#3bc9db"), (5, "#4dabf7")]


def color_at(temp):
    """Color of the table piecewise-linearly interpolated at the given °C value."""
    temp = max(5.0, min(30.0, temp))
    for (t_hi, c_hi), (t_lo, c_lo) in zip(TEMP_STOP_TABLE, TEMP_STOP_TABLE[1:]):
        if t_lo <= temp <= t_hi:
            f = (temp - t_lo) / (t_hi - t_lo)
            lo = [int(c_lo[i:i + 2], 16) for i in (1, 3, 5)]
            hi = [int(c_hi[i:i + 2], 16) for i in (1, 3, 5)]
            return "#" + "".join(f"{round(lo[i] + f * (hi[i] - lo[i])):02x}" for i in range(3))
    return TEMP_STOP_TABLE[-1][1]


def gradient_stops(values):
    """Stops that link the line color to the ABSOLUTE temperature.

    The SVG gradient has no gradientUnits, so it spans the curve's own
    bounding box: offset 0 is the window maximum, 100 the window minimum.
    To keep a pixel's color tied to its °C value, every threshold strictly
    inside the current window gets a stop at offset = 100 * (wmax - T) / (wmax - wmin),
    and the two window edges get the interpolated colors at wmax / wmin.
    """
    if not values:                                   # chart not fed yet: default ramp
        ramp = ["#fa5252", "#fd7e14", "#fab005", "#94d82d", "#3bc9db", "#4dabf7"]
        return [{"offset": o, "color": c} for o, c in zip([0, 25, 42, 62, 83, 100], ramp)]
    wmax, wmin = max(values), min(values)
    span = wmax - wmin
    if span < 0.05:                                  # flat line: one solid color for its value
        color = color_at(wmax)
        return [{"offset": 0, "color": color}, {"offset": 100, "color": color}]
    stops = [(0.0, color_at(wmax))]                  # color at the top of the curve
    stops += [(100.0 * (wmax - t) / span, c) for t, c in TEMP_STOP_TABLE if wmin < t < wmax]
    stops.append((100.0, color_at(wmin)))            # color at the bottom of the curve
    return [{"offset": round(offset), "color": color} for offset, color in stops]
