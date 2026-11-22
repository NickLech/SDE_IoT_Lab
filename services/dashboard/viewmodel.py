from datetime import datetime

from core import SENSOR_IDS, history, lock

# Wording of the VPD bands reported by central.
VPD_TEXT = {"low": "too humid", "ok": "ok", "optimal": "optimal", "stress": "too dry"}


def air_text(info):
    air = info.get("air") or {}
    temperature, humidity = air.get("temperature"), air.get("humidity")
    if temperature is None and humidity is None:
        return "missing"
    if temperature is None:
        return f"{humidity:.0f}% RH, temp missing"
    if humidity is None:
        return f"{temperature:.1f}°C, humidity missing"
    return f"{temperature:.1f}°C, {humidity:.0f}% RH"


def vpd_text(info):
    vpd = info.get("vpd")
    if not vpd or vpd.get("kpa") is None:
        return "– (no air reading)"
    band = vpd.get("band", "unknown")
    return f"{vpd['kpa']:.2f} kPa ({VPD_TEXT.get(band, band)})"


def spread_text(info):
    sensors = (info.get("sensors") or {}).values()
    readings = [s["value"] for s in sensors
                if s.get("state") == "online" and s.get("value") is not None]
    text = f"± {(max(readings) - min(readings)) / 2:.1f}%" if len(readings) > 1 else "–"
    suspects = sum(1 for s in sensors if s.get("suspect"))
    return text + (f" ({suspects} suspect/s)" if suspects else " (no suspects)")


def decision_info(info):
    """Return (status word, muted detail, alert color, pulse) for the decision row.

    "Irrigating" follows the live sprinkler state, not only the command: central's
    decide() returns action="on" just on the tick that fires the command, then None
    while the sprinkler keeps running.
    """
    decision = info.get("decision") or {}
    action, reason = decision.get("action"), decision.get("reason")
    threshold = decision.get("soil_threshold")
    running = (info.get("sprinkler") or {}).get("state") == "on"

    # A stop that was just commanded (rain, stop level) outranks the still-open valve.
    if action == "off":
        return "Stopped", reason, "gray", False
    if running or action == "on":
        detail = f"soil below {threshold:.0f}%" if threshold is not None else reason
        return "Irrigating", detail, "blue", True
    if threshold is not None:
        return "Hold", f"irrigate below {threshold:.0f}%", "gray", False
    return "Idle", (str(reason) if reason else "no decision yet"), "gray", False


def sprinkler_state(info):
    """Return (color, variant, pulse) of the SPRINKLER badge from the live valve state."""
    if (info.get("sprinkler") or {}).get("state") == "on":
        return "blue", "dot", True
    return "gray", "dot", False


# charts
def chart_series(zone):
    sensors = [{"name": f"s{i}", "color": "gray.5", "type": "line"}
               for i in range(1, len(SENSOR_IDS[zone]) + 1)]
    return [{"name": "median", "color": "blue.6", "type": "area"}] + sensors


def chart_props(zone):
    """Return (data, referenceLines, referenceAreas) for the zone chart."""
    with lock:
        points = list(history.get(zone, []))

    names = {sid: f"s{i}" for i, sid in enumerate(SENSOR_IDS[zone], 1)}
    data, times = [], []
    for point in points:
        label = datetime.fromtimestamp(point["t"]).strftime("%H:%M:%S")
        row = {"t": label, "median": point["median"]}
        row.update({name: point["s"].get(sid) for sid, name in names.items()})
        data.append(row)
        times.append(label)

    threshold = points[-1]["thr"] if points else None
    lines = [{"y": threshold, "color": "orange.6"}] if threshold is not None else []
    bands = _sprinkler_bands(times, [point["on"] for point in points])
    return data, lines, bands[-6:]


def _sprinkler_bands(times, on_flags):
    """Return one shaded band per contiguous sprinkler-on stretch.

    A stretch still running reaches the latest sample.
    """
    bands, start = [], None
    for index, (label, on) in enumerate(zip(times, on_flags)):
        if on and start is None:
            start = label
        elif not on and start is not None:
            bands.append({"x1": start, "x2": times[index - 1], "color": "blue.1"})
            start = None
    if start is not None:
        bands.append({"x1": start, "x2": times[-1], "color": "blue.1"})
    return bands


# health status
def health_checks(zone_ids, info, central_up, mqtt_up):
    """Return [(label, ok, detail)], one per check; the header shows LIVE only if all pass."""
    return [
        ("Central (HTTP pull)", central_up, "connected" if central_up else "unreachable"),
        ("Broker (MQTT subscribe)", mqtt_up, "connected" if mqtt_up else "disconnected"),
        _soil_check(zone_ids, info),
        _zone_check("Temperature (HTTP pull)", zone_ids, info, _has_air("temperature")),
        _zone_check("Humidity (HTTP pull)", zone_ids, info, _has_air("humidity")),
        _zone_check("Sprinklers (MQTT push)", zone_ids, info, _sprinkler_reports),
        _zone_check("Rain (MQTT push)", zone_ids, info, _rain_reports),
    ]


def _has_air(key):
    return lambda info: (info.get("air") or {}).get(key) is not None


def _sprinkler_reports(info):
    return (info.get("sprinkler") or {}).get("state") in ("on", "off")


def _rain_reports(info):
    return info.get("rain") in ("on", "off")


def _soil_online(info):
    return sum(1 for s in (info.get("sensors") or {}).values() if s.get("state") == "online")


def _soil_check(zone_ids, info):
    online = {zone: _soil_online(info(zone)) for zone in zone_ids}
    total = sum(len(SENSOR_IDS[zone]) for zone in zone_ids)
    degraded = [f"{zone} {online[zone]}/{len(SENSOR_IDS[zone])}" for zone in zone_ids
                if online[zone] < len(SENSOR_IDS[zone])]
    detail = f"{sum(online.values())} of {total} online"
    if degraded:
        detail += f" [{', '.join(degraded)}]"
    return "Soil sensors (MQTT push)", not degraded, detail


def _zone_check(label, zone_ids, info, is_ok):
    down = [zone for zone in zone_ids if not is_ok(info(zone))]
    detail = f"{len(zone_ids) - len(down)} of {len(zone_ids)} online"
    if down:
        detail += f" [{', '.join(down)}]"
    return label, not down, detail


# temperature line gradient (assignment panel)
# °C -> color, hottest first (Mantine red.6, orange.6, yellow.5, lime.5, cyan.5, blue.5).
TEMP_STOP_TABLE = [(30, "#fa5252"), (25, "#fd7e14"), (20, "#fab005"),
                   (15, "#94d82d"), (10, "#3bc9db"), (5, "#4dabf7")]
DEFAULT_OFFSETS = [0, 25, 42, 62, 83, 100]


def _rgb(color):
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def _color_at(temp):
    """Return the color for `temp` (°C), interpolated linearly between the table stops."""
    temp = max(TEMP_STOP_TABLE[-1][0], min(TEMP_STOP_TABLE[0][0], temp))
    for (t_hi, c_hi), (t_lo, c_lo) in zip(TEMP_STOP_TABLE, TEMP_STOP_TABLE[1:]):
        if t_lo <= temp <= t_hi:
            fraction = (temp - t_lo) / (t_hi - t_lo)
            channels = zip(_rgb(c_lo), _rgb(c_hi))
            return "#" + "".join(f"{round(lo + fraction * (hi - lo)):02x}" for lo, hi in channels)
    return TEMP_STOP_TABLE[-1][1]


def gradient_stops(values):
    """Return the gradient stops that tie the line color to the absolute temperature.

    The SVG gradient has no gradientUnits, so it spans the curve's own bounding box:
    offset 0 is the maximum of the window, offset 100 its minimum. To keep a pixel's
    color tied to its °C value, every table temperature strictly inside the window gets
    a stop at 100 * (max - T) / (max - min), and both edges get the interpolated color.
    """
    if not values:
        # The chart has no data yet: show the whole table.
        return [{"offset": offset, "color": color}
                for offset, (_, color) in zip(DEFAULT_OFFSETS, TEMP_STOP_TABLE)]

    highest, lowest = max(values), min(values)
    span = highest - lowest
    if span < 0.05:
        # A flat line gets one solid color.
        color = _color_at(highest)
        return [{"offset": 0, "color": color}, {"offset": 100, "color": color}]

    stops = [(0.0, _color_at(highest))]
    stops += [(100.0 * (highest - t) / span, color)
              for t, color in TEMP_STOP_TABLE if lowest < t < highest]
    stops.append((100.0, _color_at(lowest)))
    return [{"offset": round(offset), "color": color} for offset, color in stops]