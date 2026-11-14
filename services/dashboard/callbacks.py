"""All dashboard callbacks (registered on import)."""

import json
from datetime import datetime, timezone

from dash import ALL, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate

import core
from components.header import status_rows
from components.zone_card import (decision_row, modal_title, weather_class,
                                  zone_facts, zone_hero)
from viewmodel import chart_props, chart_series, health_checks, sprinkler_state


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
def refresh(_):
    zones, _, central_up, _, wall = core.snapshot()
    zone_ids = [o["id"]["zone"] for o in ctx.outputs_list[0]]

    def info(z):
        return zones.get(z) or {"zone": z}

    keys = ("card", "sp_color", "sp_variant", "sp_class",
            "hero", "data", "lines", "areas", "dec", "facts")
    col = {k: [] for k in keys}

    for z in zone_ids:
        i = info(z)
        col["card"].append(weather_class(i))

        s_color, s_variant, s_pulse = sprinkler_state(i)
        col["sp_color"].append(s_color)
        col["sp_variant"].append(s_variant)
        col["sp_class"].append("sp-pulse" if s_pulse else "")

        col["hero"].append(zone_hero(i))

        data, lines, areas = chart_props(z)
        col["data"].append(data)
        col["lines"].append(lines)
        col["areas"].append(areas)

        col["dec"].append(decision_row(i))
        col["facts"].append(zone_facts(z, i))

    checks = health_checks(zone_ids, info, central_up, core.connected.is_set())
    issues = sum(1 for _, ok, _ in checks if not ok)
    last = wall.strftime("%H:%M:%S") if wall else "--:--:--"
    # The pill stays compact — the timestamp lives in the status panel
    # ("Last update …"), so the button only says LIVE or "n issue(s)".
    if issues:
        conn_text, conn_color = f"{issues} issue{'s' if issues != 1 else ''}", "red"
    else:
        conn_text, conn_color = "LIVE", "green"

    return (
        col["card"], col["sp_color"], col["sp_variant"], col["sp_class"],
        col["hero"], col["data"], col["lines"], col["areas"],
        col["dec"], col["facts"],
        conn_text, conn_color, status_rows(checks, last),
    )


# ---- fullscreen zone ---------------------------------------------------------

@callback(
    Output("zone-modal", "opened"),
    Output("expanded-zone", "data"),
    Input({"type": "zone-expand", "zone": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_zone(_):
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
def refresh_modal(_, zone, opened):
    if not zone or not opened:
        raise PreventUpdate
    zones = core.snapshot()[0]
    i = zones.get(zone) or {"zone": zone}
    data, lines, areas = chart_props(zone)
    return (modal_title(zone, i), zone_hero(i, big=True), data, chart_series(zone),
            lines, areas, decision_row(i, big=True), zone_facts(zone, i, big=True),
            weather_class(i, "zone zone-modal"))


# ---- popup panels: status popover + log modal -------------------------------
# Two independent mechanisms now:
#  * Log drawer is a proper dmc.Modal (withOverlay, withCloseButton, escape and
#    outside-click all handled by Mantine itself) — DMC reports those closes
#    back as opened=False, so this callback only ever OPENS it (via open-log).
#  * The popover uses the #scrim click-catcher (z-index 900) so an outside
#    click dismisses it while the status panel itself (z-index 1000) stays
#    clickable. The scrim is only used for the popover, not the modal.

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
def toggle_panels(conn, open_log, scrim_click, status_shown, log_shown):
    status = status_shown not in (None, "none")
    log = bool(log_shown)
    trig = ctx.triggered_id
    if trig == "conn":
        status = not status
    elif trig == "open-log":
        log = not log
    elif trig == "scrim":
        status = False
    style = {"display": "block"} if status else {"display": "none"}
    return ("block" if status else "none"), log, style


# ---- log drawer content ------------------------------------------------------


@callback(
    Output("log", "children"),
    Input("tick", "n_intervals"),
    Input("show-telemetry", "checked"),
    State("log-drawer", "opened"),
    prevent_initial_call=True,
)
def refresh_log(_, telemetry, opened):
    if not opened:
        raise PreventUpdate
    return core.recent_log(bool(telemetry)) or "waiting for messages…"


# ---- controls ----------------------------------------------------------------

@callback(
    Output("clear-tip", "label"),
    Input("clear-history", "n_clicks"),
    prevent_initial_call=True,
)
def clear_history(_):
    core.clear_history()
    return f"Cleared at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"


# The active segment's indicator colour follows the choice: leaf/auto -> green,
# sun/dry -> orange, cloud-rain/rain -> cyan (matches the rain badge). No
# prevent_initial_call: it also fires on load to set the initial (green) tint.
@callback(
    Output("rain-mode", "color"),
    Input("rain-mode", "value"),
)
def rain_override(mode):
    color = {"auto": "green", "dry": "orange", "rain": "cyan"}.get(mode, "gray")
    if core.connected.is_set():
        # il servizio legge questo topic per sapere se deve comandare lui
        core.client.publish("field/rain/mode", json.dumps({"mode": mode}),
                            qos=1, retain=True)
        if mode != "auto":
            state = "on" if mode == "rain" else "off"
            payload = json.dumps({"state": state})
            for z in core.ZONES:
                core.client.publish(f"field/{z}/rain/state", payload,
                                    qos=1, retain=True)
    return color