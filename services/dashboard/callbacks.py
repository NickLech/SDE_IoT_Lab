import json
from datetime import datetime, timezone
from functools import partial

from dash import ALL, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate

import core
from assignment import grading, monitor
from components.assignment import badge_state, status_alert
from components.header import status_rows
from components.zone_card import decision_row, modal_title, weather_class, zone_facts, zone_hero
from viewmodel import (chart_props, chart_series, gradient_stops, health_checks,
                       sprinkler_state)

RAIN_MODE_COLORS = {"auto": "green", "dry": "orange", "rain": "cyan"}


def _zone_info(zones, zone):
    """Return the zone's data from central, or a stub while central is unavailable."""
    return zones.get(zone) or {"zone": zone}


@callback(
    Output({"type": "zone-card", "zone": ALL}, "className"),
    Output({"type": "zone-sprinkler", "zone": ALL}, "color"),
    Output({"type": "zone-sprinkler", "zone": ALL}, "variant"),
    Output({"type": "zone-sprinkler", "zone": ALL}, "className"),
    Output({"type": "zone-hero", "zone": ALL}, "children"),
    Output({"type": "zone-chart", "zone": ALL}, "data"),
    Output({"type": "zone-chart", "zone": ALL}, "referenceLines"),
    Output({"type": "zone-chart", "zone": ALL}, "referenceAreas"),
    Output({"type": "zone-decision", "zone": ALL}, "children"),
    Output({"type": "zone-facts", "zone": ALL}, "children"),
    Output("conn", "children"),
    Output("conn", "color"),
    Output("status-details", "children"),
    Input("tick", "n_intervals"),
)
def refresh(_n_intervals):
    """Refresh the zone cards and the connection status from the latest data."""
    zones, central_up, wall = core.snapshot()
    zone_ids = [output["id"]["zone"] for output in ctx.outputs_list[0]]
    info = partial(_zone_info, zones)

    rows = [_zone_row(zone, info(zone)) for zone in zone_ids]
    per_zone = [list(column) for column in zip(*rows)]

    checks = health_checks(zone_ids, info, central_up, core.connected.is_set())
    issues = sum(not ok for _, ok, _ in checks)
    # The button stays compact: the timestamp is in the status panel.
    if issues:
        label, color = f"{issues} issue{'s' if issues > 1 else ''}", "red"
    else:
        label, color = "LIVE", "green"
    last_update = wall.strftime("%H:%M:%S") if wall else "--:--:--"

    return (*per_zone, label, color, status_rows(checks, last_update))


def _zone_row(zone, info):
    """Return one value per zone output of refresh(), in the same order."""
    color, variant, pulse = sprinkler_state(info)
    data, lines, areas = chart_props(zone)
    return (
        weather_class(info), color, variant, "sp-pulse" if pulse else "",
        zone_hero(info), data, lines, areas, decision_row(info), zone_facts(zone, info),
    )


@callback(
    Output("zone-modal", "opened"),
    Output("expanded-zone", "data"),
    Input({"type": "zone-expand", "zone": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_zone(_n_clicks):
    """Open the fullscreen modal of the zone whose expand button was clicked."""
    # The value is empty when the buttons are rendered, not clicked.
    if not ctx.triggered_id or not ctx.triggered[0]["value"]:
        raise PreventUpdate
    return True, ctx.triggered_id["zone"]


@callback(
    Output("zone-modal-title", "children"),
    Output("zone-modal-hero", "children"),
    Output("zone-modal-chart", "data"),
    Output("zone-modal-chart", "series"),
    Output("zone-modal-chart", "referenceLines"),
    Output("zone-modal-chart", "referenceAreas"),
    Output("zone-modal-decision", "children"),
    Output("zone-modal-facts", "children"),
    Output("zone-modal-card", "className"),
    Input("tick", "n_intervals"),
    Input("expanded-zone", "data"),
    State("zone-modal", "opened"),
    prevent_initial_call=True,
)
def refresh_modal(_n_intervals, zone, opened):
    """Refresh the fullscreen modal of the opened zone."""
    if not zone or not opened:
        raise PreventUpdate
    info = _zone_info(core.snapshot()[0], zone)
    data, lines, areas = chart_props(zone)
    return (
        modal_title(zone, info), zone_hero(info, big=True), data, chart_series(zone),
        lines, areas, decision_row(info, big=True), zone_facts(zone, info, big=True),
        weather_class(info, "zone zone-modal"),
    )


@callback(
    Output("status-details", "display"),
    Output("log-drawer", "opened"),
    Output("scrim", "style"),
    Input("conn", "n_clicks"),
    Input("open-log", "n_clicks"),
    Input("scrim", "n_clicks"),
    State("status-details", "display"),
    State("log-drawer", "opened"),
    prevent_initial_call=True,
)
def toggle_panels(_conn, _open_log, _scrim, status_display, log_opened):
    """Toggle the status panel and the log modal; an outside click closes the status panel."""
    # Mantine closes the log modal itself (Escape, overlay, close button) and reports
    # opened=False, so this callback only needs to open it. The status panel is a plain
    # Paper that closes through a click on the scrim.
    status_open = status_display not in (None, "none")
    log_open = bool(log_opened)

    if ctx.triggered_id == "conn":
        status_open = not status_open
    elif ctx.triggered_id == "open-log":
        log_open = not log_open
    elif ctx.triggered_id == "scrim":
        status_open = False

    display = "block" if status_open else "none"
    return display, log_open, {"display": display}


@callback(
    Output("log", "children"),
    Input("tick", "n_intervals"),
    Input("show-telemetry", "checked"),
    State("log-drawer", "opened"),
    prevent_initial_call=True,
)
def refresh_log(_n_intervals, telemetry, opened):
    """Show the latest MQTT messages while the log modal is open."""
    if not opened:
        raise PreventUpdate
    return core.recent_log(bool(telemetry)) or "waiting for messages…"


@callback(
    Output("clear-tip", "label"),
    Input("clear-history", "n_clicks"),
    prevent_initial_call=True,
)
def clear_history(_n_clicks):
    """Clear the charts' history and report when it happened."""
    core.clear_history()
    return f"Cleared at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"


@callback(
    Output("rain-mode", "color"),
    Input("rain-mode", "value"),
)
def rain_override(mode):
    """Publish the selected rain mode and tint the selector to match it."""
    if core.connected.is_set():
        _publish_rain_mode(mode)
    return RAIN_MODE_COLORS.get(mode, "gray")


def _publish_rain_mode(mode):
    # The rain service reads this topic to know whether it controls the rain itself.
    core.client.publish("field/rain/mode", json.dumps({"mode": mode}), qos=1, retain=True)
    if mode == "auto":
        return
    payload = json.dumps({"state": "on" if mode == "rain" else "off"})
    for zone in core.ZONES:
        core.client.publish(f"field/{zone}/rain/state", payload, qos=1, retain=True)


@callback(
    Output("asg-banner", "children"),
    Output("asg-temp-chart", "data"),
    Output("asg-temp-chart", "gradientStops"),
    Output("asg-rain-chart", "data"),
    Output("asg-badge", "children"),
    Output("asg-badge", "color"),
    Output("asg-badge", "leftSection"),
    Input("asg-tick", "n_intervals"),
)
def refresh_assignment(_n_intervals):
    """Refresh the Assignment panel: charts, completion banner and badge."""
    temp, rain, temp_ok = monitor.snapshot()
    name = grading.full_name(monitor.STUDENT_NAME, monitor.STUDENT_SURNAME)
    missing = grading.missing_todos(name, monitor.ZONE, monitor.RAIN_TOPIC, temp_ok)
    return (
        status_alert(name, missing),
        temp, gradient_stops([p["temperature"] for p in temp]), rain,
        *badge_state(missing),
    )