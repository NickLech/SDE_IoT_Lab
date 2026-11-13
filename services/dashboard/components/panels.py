import dash_mantine_components as dmc

from core import RADIUS
from components.zone_card import zone_chart


def zone_modal():
    return dmc.Modal(
        id="zone-modal", opened=False, fullScreen=True,
        title=dmc.Text(id="zone-modal-title", fw=600),
        children=dmc.Stack(gap="md", children=[
            dmc.Group(id="zone-modal-hero", justify="space-between", align="flex-end"),
            zone_chart("zone-modal-chart", "zone1", 460),
            dmc.Alert("–", id="zone-modal-decision", color="gray", variant="light", p="xs"),
            dmc.SimpleGrid(id="zone-modal-facts", cols={"base": 2, "md": 3}, spacing="xs"),
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
