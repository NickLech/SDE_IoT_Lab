import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from core import RADIUS, lock, water_s
from viewmodel import air_text, chart_series, command_text, spread_text, vpd_text


def fact(label, value):
    return dmc.Paper(
        p="xs", radius=RADIUS, bg="var(--mantine-color-gray-0)",
        children=dmc.Group(justify="space-between", wrap="nowrap", gap="xs", children=[
            dmc.Text(label, size="xs", c="dimmed"),
            dmc.Text(value, size="xs", ta="right"),
        ]),
    )


def zone_facts(zone, info):
    with lock:
        watered = water_s.get(zone, 0.0)
    return [
        fact("air", air_text(info)),
        fact("VPD", vpd_text(info)),
        fact("agreement", spread_text(info)),
        fact("watered", f"{watered / 60:.1f} min"),
        fact("last cmd", command_text(info)),
    ]


def zone_hero(info):
    """Two compact dot-badges: soil moisture + signed distance to threshold."""
    median = (info.get("soil") or {}).get("median")
    thr = (info.get("decision") or {}).get("soil_threshold")

    if median is None:
        return [dmc.Badge("avg. soil moisture", color="gray", variant="light", size="md")]

    moisture = dmc.Badge(
        dmc.Group(gap=6, wrap="nowrap", align="center", children=[
            dmc.Text(f"{median:.0f}%", size="md", fw=700),
            dmc.Text("avg. soil moisture", size="xs", c="dimmed"),
        ]),
        color="blue", variant="light", size="lg",
    )

    if thr is None:
        delta = dmc.Badge("no threshold", color="gray", variant="dot", size="md")
    else:
        gap = median - thr
        delta = dmc.Badge(f"{gap:+.0f} % from θ",
                          color="green" if gap >= 0 else "orange",
                          variant="dot", size="md")

    return [moisture, delta]


def zone_chart(id_, zone, height):
    return dmc.CompositeChart(
        id=id_, h=height, data=[], dataKey="t", series=chart_series(zone),
        curveType="monotone", withDots=False, withLegend=False, unit="%",
        yAxisProps={"domain": [0, 100]}, referenceLines=[], gridAxis="y",
    )


def zone_card(zone):
    return dmc.Paper(
        id={"type": "zone-card", "zone": zone},
        className="zone", withBorder=True, radius=RADIUS, shadow="sm", p="md",
        children=[
            html.Div(className="rain-layer"),
            dmc.Stack(gap="xs", children=[
                dmc.Group(justify="space-between", wrap="nowrap", children=[
                    dmc.Text(zone.replace("zone", "Zone #"), fw=700, size="lg"),
                    dmc.Group(gap="xs", wrap="nowrap", children=[
                        dmc.Badge(dmc.Group(gap=4, wrap="nowrap", children=[
                            dmc.Text("SPRINKLER", size="xs", fw=600),
                        ]),
                            id={"type": "zone-sprinkler", "zone": zone},
                            color="gray", variant="dot", size="lg"
                        ),
                        dmc.Tooltip(label="Fullscreen", children=
                            dmc.ActionIcon(
                                DashIconify(icon="tabler:arrows-maximize", width=16),
                                id={"type": "zone-expand", "zone": zone},
                                variant="default", radius=RADIUS, size="md"
                            )
                        ),
                    ]),
                ]),
                dmc.Group(id={"type": "zone-hero", "zone": zone}, justify="space-between", align="flex-end", children=zone_hero({})),
                dmc.Space(h="xs"),
                zone_chart({"type": "zone-chart", "zone": zone}, zone, 190),
                dmc.Space(h="xs"),
                dmc.Alert("–", id={"type": "zone-decision", "zone": zone}, color="gray", variant="light", p="xs"),
                dmc.SimpleGrid(id={"type": "zone-facts", "zone": zone}, cols=2,
                               spacing="xs", children=zone_facts(zone, {})),
            ]),
        ],
    )
