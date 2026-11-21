import dash_mantine_components as dmc
from dash import html

from components.zone_card import decision_row, weather_layers, zone_chart, zone_facts
from core import RADIUS, ZONES


def zone_modal():
    """Fullscreen view of one zone. The callbacks fill it in when a zone is opened."""
    return dmc.Modal(
        id="zone-modal", opened=False, fullScreen=True, padding=0,
        children=html.Div(id="zone-modal-card", className="zone zone-modal", children=[
            *weather_layers(),
            dmc.Stack(gap="md", children=[
                dmc.Group(id="zone-modal-title", align="center", gap="sm"),
                dmc.Group(id="zone-modal-hero", justify="space-between", align="flex-end"),
                dmc.Grid(gap="lg", align="stretch", mt="xl", children=[
                    dmc.GridCol(span={"base": 12, "lg": 8},
                                children=zone_chart("zone-modal-chart", ZONES[0], 520)),
                    dmc.GridCol(span={"base": 6, "lg": 4}, children=_side_column()),
                ]),
            ]),
        ]),
    )


def _side_column():
    return dmc.Stack(gap="sm", children=[
        dmc.Group(id="zone-modal-decision", align="center", gap="xs", wrap="nowrap",
                  children=decision_row({}, big=True)),
        dmc.SimpleGrid(id="zone-modal-facts", cols=1, spacing="sm",
                       children=zone_facts(ZONES[0], {}, big=True)),
    ])


def log_drawer():
    """MQTT log, shown in a modal. The id `log-drawer` is kept from an earlier drawer."""
    return dmc.Modal(
        id="log-drawer", opened=False, centered=True, size="80%", radius=RADIUS, padding="md",
        title=dmc.Text("MQTT logs", fw=600, size="lg"),
        children=[
            dmc.Switch(
                id="show-telemetry", label="Include raw sensor data", checked=True,
                onLabel="ON", offLabel="OFF", size="sm", mb="sm", withThumbIndicator=False,
            ),
            dmc.ScrollArea(h="70vh", mt="xs", children=dmc.Code(
                id="log", block=True, fz="xs", style={"whiteSpace": "pre"},
                children="waiting for messages…",
            )),
        ],
    )