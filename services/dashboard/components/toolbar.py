import dash_mantine_components as dmc
from dash_iconify import DashIconify

from core import RADIUS


def toolbar():
    return dmc.Paper(withBorder=True, radius=RADIUS, p="xs", w="fit-content", ml="auto",
                     children=dmc.Group(gap="sm", children=[
        dmc.Tooltip(label="MQTT log", radius=RADIUS, children=dmc.ActionIcon(
            DashIconify(icon="tabler:terminal-2", width=20), id="open-log", variant="light", size="lg")),
        dmc.SegmentedControl(id="rain-mode", value="auto", radius=RADIUS, data=[
            {"value": "auto", "label": dmc.Group(gap=4, align="center", wrap="nowrap", children=[
                DashIconify(icon="tabler:leaf", width=18),
                dmc.Text("AUTO", size="xs", fw=600),
            ])},
            {"value": "dry", "label": dmc.Center(DashIconify(icon="tabler:sun", width=18))},
            {"value": "rain", "label": dmc.Center(DashIconify(icon="tabler:cloud-rain", width=18))},
        ]),
    ]))
