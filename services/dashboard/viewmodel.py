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
        return f"{rh:.0f}% RH · temp missing"
    if rh is None:
        return f"{t:.1f}°C · humidity missing"
    return f"{t:.1f}°C · {rh:.0f}% RH"


def vpd_text(info):
    vpd = info.get("vpd")
    if not vpd or vpd.get("kpa") is None:
        return "– (no air reading)"
    band = vpd.get("band", "unknown")
    return f"{vpd['kpa']:.2f} kPa · {VPD_TEXT.get(band, band)}"


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
    text = f"±{(max(vals) - min(vals)) / 2:.1f} pts" if len(vals) > 1 else "–"
    suspects = sum(1 for s in sensors if s.get("suspect"))
    return text + (f" · {suspects} suspect" if suspects else "")


def decision_info(info):
    """Return (text, alert color) for the zone decision bar."""
    d = info.get("decision") or {}
    action, reason, thr = d.get("action"), d.get("reason"), d.get("soil_threshold")
    if action == "on":
        return (f"Irrigating — {reason}" if reason else "Irrigating"), "blue"
    if action == "off":
        return (f"Irrigation stopped — {reason}" if reason else "Irrigation stopped"), "gray"
    if thr is not None:
        return f"Hold — irrigate below {thr:.0f}%", "gray"
    return str(reason or "No decision yet"), "gray"


# ---- charts ----------------------------------------------------------------

def chart_series(zone):
    sensors = [{"name": f"s{i}", "color": "gray.5", "type": "line"}
               for i in range(1, len(SENSOR_IDS[zone]) + 1)]
    return [{"name": "median", "color": "blue.6", "type": "area"}] + sensors


def chart_props(zone):
    """Return (data, referenceLines) for the zone chart."""
    with lock:
        pts = list(history.get(zone, []))

    names = {sid: f"s{i}" for i, sid in enumerate(SENSOR_IDS[zone], 1)}
    data, starts, prev = [], [], False
    for p in pts:
        t = datetime.fromtimestamp(p["t"]).strftime("%H:%M:%S")
        row = {"t": t, "median": p["median"]}
        row.update({name: p["s"].get(sid) for sid, name in names.items()})
        data.append(row)
        if p["on"] and not prev:
            starts.append({"x": t, "color": "blue.3", "label": "sprinkler on"})
        prev = p["on"]

    lines = starts[-5:]
    thr = pts[-1]["thr"] if pts else None
    if thr is not None:
        lines.insert(0, {"y": thr, "color": "orange.6", "strokeDasharray": "4 4",
                         "label": f"irrigate below {thr:.0f}%"})
    return data, lines


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
