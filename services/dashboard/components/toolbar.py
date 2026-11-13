import dash_mantine_components as dmc
from dash import dcc
from dash_iconify import DashIconify

from core import RADIUS


def _step(n, title, formula, note):
    return dmc.Paper(
        radius=RADIUS,
        p="sm",
        bg="var(--mantine-color-gray-0)",
        children=dmc.Stack(
            gap=6,
            children=[
                dmc.Group(
                    gap="sm",
                    wrap="nowrap",
                    align="flex-start",
                    children=[
                        dmc.Badge(str(n), size="sm", circle=True, variant="light",
                                style={"flex": "none"}),
                        dmc.Text(
                            size="xs",
                            c="dimmed",
                            children=[
                                dmc.Text(title, span=True, fw=600, tt="uppercase", inherit=True),
                                f" : {note}" if note else "",
                            ],
                        ),
                    ],
                ),
                dcc.Markdown(f"${formula}$", mathjax=True, className="formula", style={"fontSize": "0.875em", "margin": "-1em 0"}),
            ],
        ),
    )


def _model_paper():
    return dmc.Card(withBorder=True, radius=RADIUS, padding="md", shadow="sm",
                w="100%", className="lift", children=dmc.Stack([
            dmc.SimpleGrid(cols={"base": 1, "md": 3}, spacing="md", children=[
                _step(1, "Saturation pressure",
                      r"\displaystyle e_s(T)=0.6108\,\exp\!\Big(\frac{17.27\,T}{T+237.3}\Big)\;[\mathrm{kPa}]",
                      "Most water vapour the air can hold at temperature T (°C)."),
                _step(2, "Vapour pressure deficit",
                      r"\displaystyle \mathrm{VPD}=e_s(T)\,\Big(1-\frac{\mathrm{RH}}{100}\Big)\;[\mathrm{kPa}]",
                      "How far the air is from saturation (Relative Humidity in %). When the VPD is high, plants lose more water."),
                _step(3, "Irrigation threshold",
                      r"\displaystyle \theta=35+15\,(\mathrm{VPD}-0.8)\;[\%]",
                      "Irrigate when soil moisture falls below θ. θ is 35 % in average air (VPD 0.8 kPa), and increases with VPD to avoid plant stress."),
            ]),
        ]))


def toolbar():
    # Returns a 2-tuple the layout can place separately: the controls Paper
    # goes on top (right-aligned), the model Paper sits under the zone cards.
    controls = dmc.Paper(withBorder=True, radius=RADIUS, p="xs", w="fit-content", ml="auto",
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
    return controls, _model_paper()