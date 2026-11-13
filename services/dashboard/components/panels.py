"""Overlays and notes: fullscreen zone modal, MQTT log drawer, 'how fusion works'."""

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
    # Always-mounted (fixed Paper toggled via `display`), not dmc.Drawer:
    # DMC floating overlays snapshot their children while open, so callback
    # updates to #log never reach the DOM. Same reason as the status panel.
    return dmc.Paper(
        id="log-drawer", withBorder=True, shadow="md", radius=RADIUS, p="md",
        display="none",
        style={"position": "fixed", "top": "80px", "left": "16px",
               "width": "min(560px, 85vw)", "maxHeight": "calc(100vh - 100px)",
               "zIndex": 1000},
        children=[
            dmc.Group(justify="space-between", align="center", mb="sm", children=[
                dmc.Text("MQTT log", fw=600),
                dmc.Group(gap="sm", wrap="nowrap", children=[
                    dmc.Switch(id="show-telemetry", label="telemetry", checked=False, size="xs"),
                    dmc.ActionIcon("✕", id="close-log", variant="subtle", color="gray", size="sm"),
                ]),
            ]),
            dmc.ScrollArea(h="calc(100vh - 200px)", children=dmc.Code(
                id="log", block=True, fz="xs", style={"whiteSpace": "pre"},
                children="waiting for messages…")),
        ],
    )


def about():
    items = [
        "Level 0: drop physically impossible readings (outside 0–100%).",
        "Redundant soil: median of 3 sensors per zone; outliers are flagged.",
        "Cooperative air: temperature + humidity → VPD (kPa).",
        "Decision: soil median vs a VPD-adjusted threshold, with a cooldown.",
    ]
    return dmc.Accordion(variant="contained", radius=RADIUS, children=dmc.AccordionItem(
        value="fusion", children=[
            dmc.AccordionControl("How central fuses the data"),
            dmc.AccordionPanel(dmc.Stack(gap="xs", children=[
                dmc.List(size="sm", children=[dmc.ListItem(t) for t in items]),
                dmc.Text(size="xs", c="dimmed", children=[
                    "Manual rain override publishes the retained ",
                    dmc.Code("field/<zone>/rain/state"),
                    " from the dashboard; the rain service may overwrite it on its next cycle.",
                ]),
            ])),
        ]))
