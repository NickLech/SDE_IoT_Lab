import dash_mantine_components as dmc
from dash import dcc
from dash_iconify import DashIconify

from core import RADIUS

MODEL_STEPS = [
    (
        "Saturation pressure",
        r"\displaystyle e_s(T)=0.6108\,\exp\!\Big(\frac{17.27\,T}{T+237.3}\Big)\;[\mathrm{kPa}]",
        "Maximum water vapour pressure the air can hold at temperature T (°C).",
    ),
    (
        "Vapour pressure deficit",
        r"\displaystyle \mathrm{VPD}=e_s(T)\,\Big(1-\frac{\mathrm{RH}}{100}\Big)\;[\mathrm{kPa}]",
        "How far the air is from saturation (relative humidity RH in %). "
        "The higher the VPD, the more water plants lose.",
    ),
    (
        "Irrigation threshold",
        r"\displaystyle \theta=35+15\,(\mathrm{VPD}-0.8)\;[\%]",
        "Irrigate when soil moisture falls below θ. θ is 35 % at the reference VPD of "
        "0.8 kPa (the lower edge of the optimal band) and rises with VPD, so irrigation "
        "starts earlier in drier air.",
    ),
]


def _icon(name, size=18):
    return DashIconify(icon=f"tabler:{name}", width=size)


def toolbar():
    return dmc.Paper(
        withBorder=True, radius=RADIUS, p="xs", w="fit-content", ml="auto",
        children=dmc.Group(gap="sm", children=[_log_button(), _rain_selector()]),
    )


def _log_button():
    return dmc.Tooltip(
        label="MQTT logs", radius=RADIUS,
        children=dmc.ActionIcon(
            _icon("terminal-2", 20), id="open-log", variant="light", size="lg"),
    )


def _rain_selector():
    return dmc.SegmentedControl(
        id="rain-mode", value="auto", radius=RADIUS,
        data=[
            {"value": "auto", "label": dmc.Group(
                gap=4, align="center", wrap="nowrap",
                children=[_icon("leaf"), dmc.Text("AUTO", size="xs", fw=600)])},
            {"value": "dry", "label": dmc.Center(_icon("sun"))},
            {"value": "rain", "label": dmc.Center(_icon("cloud-rain"))},
        ],
    )


def irrigation_model():
    steps = [_step(n, *step) for n, step in enumerate(MODEL_STEPS, start=1)]
    return dmc.Card(
        withBorder=True, radius=RADIUS, padding="md", pb="lg", mt="sm", mb="sm",
        shadow="sm", w="100%", className="lift",
        children=dmc.Stack([
            dmc.Text("Irrigation model", fw=700, size="lg"),
            dmc.SimpleGrid(cols={"base": 1, "md": 3}, spacing="md", children=steps),
        ]),
    )


def _step(number, title, formula, note):
    return dmc.Paper(
        radius=RADIUS, p="sm", bg="var(--mantine-color-gray-0)",
        children=dmc.Stack(gap=6, children=[
            dmc.Group(gap="sm", wrap="nowrap", align="flex-start", children=[
                dmc.Badge(str(number), size="sm", circle=True, variant="light",
                          style={"flex": "none"}),
                dmc.Text(size="xs", c="dimmed", children=[
                    dmc.Text(title, span=True, fw=600, tt="uppercase", inherit=True),
                    f" : {note}",
                ]),
            ]),
            # The negative margin cancels the paragraph margin that Markdown adds.
            dcc.Markdown(f"${formula}$", mathjax=True, className="formula",
                         style={"fontSize": "0.875em", "margin": "-1em 0"}),
        ]),
    )