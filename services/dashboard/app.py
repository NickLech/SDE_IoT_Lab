import logging
import os
import threading

# Dash 4.x still ships React 18.3.1 by default; dash_mantine_components v3 requires React 19.
from dash._dash_renderer import _set_react_version
_set_react_version("19.2.4", "19.2.4")

import dash_mantine_components as dmc
from dash import Dash, dcc, html
from waitress import serve

import core
from components.header import header
from components.panels import assignment, log_drawer, zone_modal
from components.toolbar import toolbar
from components.zone_card import zone_card

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

# Global radius: core.RADIUS is the token every surface uses; this theme fixes
# what that token renders to (change it to retune all corners at once).
controls, model = toolbar()
app.layout = dmc.MantineProvider(theme={"radius": {"xl": "1rem"}}, children=[
    dmc.AppShell(header={"height": 72}, padding="md", children=[
        dmc.AppShellHeader(header()),
        dmc.AppShellMain(dmc.Container(size="xl", children=dmc.Stack(gap="md", children=[
            controls,
            dmc.SimpleGrid(cols={"base": 1, "md": 2, "xl": 3}, children=[zone_card(z) for z in core.ZONES]),
            model,
            assignment(),
        ]))),
    ]),
    log_drawer(),
    zone_modal(),
    dmc.Space(h="xl"),
    dmc.Space(h="xl"),
    dmc.Space(h="xl"),
    dmc.Space(h="xl"),
    # Transparent full-screen catch layer: clicking it closes the popup panels
    # above. It sits UNDER both (z-index 900 vs their 1000), so the status
    # pill's popover and the log drawer stay clickable while the rest of the
    # page is blocked by it. See .scrim in dashboard.css + toggle_panels().
    html.Div(id="scrim", className="scrim", style={"display": "none"}),
    dcc.Store(id="expanded-zone"),
    dcc.Interval(id="tick", interval=core.REFRESH_MS),
])

import callbacks  # (registers all callbacks)

if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    threading.Thread(target=core.poll_central, daemon=True, name="central-poller").start()
    core.client.connect_async(core.MQTT_HOST, core.MQTT_PORT, keepalive=30)
    core.client.loop_start()
    log = logging.getLogger("dashboard")
    log.info("serving on port %d, central at %s", core.PORT, core.CENTRAL_URL)
    serve(app.server, host="0.0.0.0", port=core.PORT, threads=16)
