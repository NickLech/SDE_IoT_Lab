import logging
import os
import threading

# dash-mantine-components v3 needs React 19, but Dash 4 still ships React 18.3.1 by default.
from dash._dash_renderer import _set_react_version

_set_react_version("19.2.4", "19.2.4")

import dash_mantine_components as dmc
from dash import Dash, dcc, html
from waitress import serve

import core
from assignment import monitor
from components.assignment import assignment_panel
from components.header import header
from components.panels import log_drawer, zone_modal
from components.toolbar import irrigation_model, toolbar
from components.zone_card import zone_card

log = logging.getLogger("dashboard")

# core.RADIUS is the radius token every surface uses.
THEME = {"radius": {"xl": "1rem"}}

app = Dash(
    __name__,
    title='LAB6 "IoT Monitoring with SOA"',
    enable_mcp=True,
    mcp_path="/_mcp",
    health_endpoint="health",
)

try:
    from dash.mcp import configure_mcp_server
    configure_mcp_server(expose_callback_docstrings=True)
except ImportError:
    pass


def build_layout():
    zone_cards = [zone_card(zone) for zone in core.ZONES]
    return dmc.MantineProvider(theme=THEME, children=[
        dmc.AppShell(header={"height": 72}, padding="md", children=[
            dmc.AppShellHeader(header()),
            dmc.AppShellMain(dmc.Container(size="xl", children=dmc.Stack(gap="md", children=[
                toolbar(),
                dmc.SimpleGrid(cols={"base": 1, "md": 2, "xl": 3}, children=zone_cards),
                irrigation_model(),
                assignment_panel(),
            ]))),
        ]),
        log_drawer(),
        zone_modal(),
        dmc.Space(h="8rem"),    # clearance below the page
        # Transparent full-screen layer behind the popup panels: clicking it closes them.
        # See `.scrim` in dashboard.css and toggle_panels() in callbacks.py.
        html.Div(id="scrim", className="scrim", style={"display": "none"}),
        dcc.Store(id="expanded-zone"),
        dcc.Interval(id="tick", interval=core.REFRESH_MS),
    ])


app.layout = build_layout()

import callbacks  # noqa: E402,F401  (registers all callbacks)


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    threading.Thread(target=core.poll_central, daemon=True, name="central-poller").start()
    core.client.connect_async(core.MQTT_HOST, core.MQTT_PORT, keepalive=30)
    core.client.loop_start()
    monitor.start()
    log.info("serving on port %d, central at %s", core.PORT, core.CENTRAL_URL)
    serve(app.server, host="0.0.0.0", port=core.PORT, threads=16)


if __name__ == "__main__":
    main()