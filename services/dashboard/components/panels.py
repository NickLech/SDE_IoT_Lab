import dash_mantine_components as dmc

from core import RADIUS
from components.zone_card import decision_row, zone_chart, zone_facts


def zone_modal():
    return dmc.Modal(
        id="zone-modal", opened=False, fullScreen=True,
        title=dmc.Group(id="zone-modal-title", align="center", gap="sm"),
        children=dmc.Stack(gap="md", children=[
            dmc.Group(id="zone-modal-hero", justify="space-between", align="flex-end"),
            dmc.Grid(gap="lg", align="stretch", children=[
                dmc.GridCol(span={"base": 12, "lg": 8}, children=zone_chart("zone-modal-chart", "zone1", 520)),
                dmc.GridCol(span={"base": 6, "lg": 4}, children=dmc.Stack(gap="sm", children=[
                    dmc.Group(id="zone-modal-decision", align="center", gap="xs", wrap="nowrap", children=decision_row({}, big=True)),
                    dmc.SimpleGrid(id="zone-modal-facts", cols=1, spacing="sm", children=zone_facts("zone1", {}, big=True)),
                ])),
            ]),
        ]),
    )


def log_drawer():
    return dmc.Modal(
        id="log-drawer", opened=False, centered=True, size="80%", radius=RADIUS,
        padding="md", withCloseButton=True, withOverlay=True,
        closeOnClickOutside=True, closeOnEscape=True,
        title=dmc.Text("MQTT logs", fw=600, size="lg"),
        children=[
            dmc.Switch(id="show-telemetry", label="Include raw sensor data", onLabel="ON", offLabel="OFF", checked=True, size="sm", mb="sm", withThumbIndicator=False),
            dmc.ScrollArea(h="70vh", mt="xs", children=dmc.Code(
                id="log", block=True, fz="xs", style={"whiteSpace": "pre"},
                children="waiting for messages…")),
        ],
    )


def assignment():
    return dmc.Accordion(variant="contained", radius=RADIUS, className="lift", children=
        dmc.AccordionItem(value="fusion", children=[
            dmc.AccordionControl(dmc.Text("Assignment", fw=600, size="sm")),
            dmc.AccordionPanel(),
        ]))
