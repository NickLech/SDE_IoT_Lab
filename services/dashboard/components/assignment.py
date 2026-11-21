import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify

from assignment.monitor import ZONE_TEXT
from core import RADIUS
from viewmodel import gradient_stops

INSTRUCTIONS = (
    f"Your own monitoring panel for {ZONE_TEXT}: temperature over HTTP and rain "
    "over MQTT. Complete the TODOs in the code and watch it update live."
)
ALERT_STYLE = {"variant": "light", "radius": RADIUS, "fw": 600}


def _icon(name, size):
    return DashIconify(icon=f"tabler:{name}", width=size)


def assignment_panel():
    return dmc.Paper(
        shadow="sm", radius=RADIUS, p=0, className="lift",
        children=dmc.Accordion(
            variant="contained", radius=RADIUS,
            children=dmc.AccordionItem(value="assignment", children=[_header(), _body()]),
        ),
    )


def _header():
    text, color, icon = badge_state(missing=True)   # placeholder until the first refresh
    return dmc.AccordionControl(dmc.Group(
        justify="space-between", wrap="nowrap", align="center", w="100%",
        children=[
            dmc.Text("Assignment", fw=700, size="lg"),
            dmc.Badge(text, id="asg-badge", color=color, leftSection=icon,
                      variant="light", size="lg", mr="md"),
        ],
    ))


def _body():
    return dmc.AccordionPanel(dmc.Stack(gap="md", pb=5, children=[
        dmc.Text(INSTRUCTIONS, size="sm", c="dimmed"),
        html.Div(id="asg-banner"),
        dmc.SimpleGrid(cols={"base": 1, "md": 2}, spacing="md", children=[
            _chart_card("Air temperature (°C)", "temperature", _temperature_chart()),
            _chart_card("Rain sensor", "umbrella", _rain_chart()),
        ]),
        dcc.Interval(id="asg-tick", interval=1000),
    ]))


def _chart_card(label, icon, chart):
    return dmc.Paper(
        radius=RADIUS, p="md", shadow="sm", bg="var(--mantine-color-gray-1)",
        children=dmc.Stack(gap="xs", children=[
            dmc.Group(gap="xs", wrap="nowrap", align="center", children=[
                _icon(icon, 16),
                dmc.Text(label, size="xs", fw=600, c="dimmed", tt="uppercase"),
            ]),
            chart,
        ]),
    )


def _temperature_chart():
    return dmc.LineChart(
        id="asg-temp-chart", h=220, data=[], dataKey="t",
        series=[{"name": "temperature"}],
        type="gradient", strokeWidth=4,
        gradientStops=gradient_stops([]),       # default ramp, rewritten by the callback
        curveType="natural", withDots=False, withLegend=False,
        unit="°C", gridAxis="y",
        yAxisProps={"domain": [5, 30], "ticks": [5, 10, 15, 20, 25, 30]},
        lineProps={"isAnimationActive": False}, p="xs",
    )


def _rain_chart():
    return dmc.AreaChart(
        id="asg-rain-chart", h=220, data=[], dataKey="t",
        series=[{"name": "rain", "color": "cyan.6"}],
        curveType="stepAfter", withDots=False, withLegend=False,
        withGradient=True, fillOpacity=0.6, gridAxis="y",
        yAxisProps={"domain": [0, 1], "ticks": [0, 1],
                    "tick": {"function": "rainTick"}},      # see assets/rain-tick.js
        areaProps={"strokeWidth": 2, "isAnimationActive": False}, p="xs",
    )


def status_alert(name, missing):
    """Return the red list of open TODOs, or the green "well done" message."""
    if missing:
        return dmc.Alert("Complete: " + ", ".join(missing), color="red",
                         icon=_icon("tool", 22), **ALERT_STYLE)
    return dmc.Alert(f"Well done {name}! You are now monitoring {ZONE_TEXT} over MQTT and HTTP.",
                     color="green", icon=_icon("circle-check", 22), **ALERT_STYLE)


def badge_state(missing):
    """Return (children, color, leftSection) of the accordion badge."""
    if missing:
        return "Not completed", "red", _icon("circle-x", 16)
    return "Completed", "green", _icon("circle-check", 16)