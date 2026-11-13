"""One zone card: header badges, hero readout, chart, decision, facts."""

import dash_mantine_components as dmc
from dash import html

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
    """Big readout: fused soil moisture + distance from the irrigation threshold."""
    median = (info.get("soil") or {}).get("median")
    thr = (info.get("decision") or {}).get("soil_threshold")
    if median is None:
        return [dmc.Stack(gap=0, children=[
            dmc.Text("–", fz="2.5rem", fw=700, lh=1),
            dmc.Text("median soil moisture", size="xs", c="dimmed"),
        ])]

    if thr is None:
        delta = dmc.Badge("no threshold", color="gray", variant="light")
    elif median >= thr:
        delta = dmc.Badge(f"{median - thr:.0f} pts above threshold", color="green", variant="light")
    else:
        delta = dmc.Badge(f"{thr - median:.0f} pts below threshold", color="orange", variant="light")

    return [
        dmc.Stack(gap=4, children=[
            dmc.Group(gap=2, align="baseline", children=[
                dmc.Text(f"{median:.0f}", fz="2.5rem", fw=700, lh=1),
                dmc.Text("%", size="lg", c="dimmed", fw=600),
            ]),
            dmc.Text("median soil moisture", size="xs", c="dimmed"),
        ]),
        delta,
    ]


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
            dmc.Stack(gap="sm", children=[
                dmc.Group(justify="space-between", wrap="nowrap", children=[
                    dmc.Text(zone.replace("zone", "Zone "), fw=600),
                    dmc.Group(gap="xs", wrap="nowrap", children=[
                        dmc.Badge("rain –", id={"type": "zone-rain", "zone": zone},
                                  color="gray", variant="light"),
                        dmc.Badge("sprinkler –", id={"type": "zone-sprinkler", "zone": zone},
                                  color="gray", variant="light"),
                        dmc.Tooltip(label="Fullscreen", children=dmc.ActionIcon(
                            "⛶", id={"type": "zone-expand", "zone": zone},
                            variant="subtle", color="gray", size="sm")),
                    ]),
                ]),
                dmc.Group(id={"type": "zone-hero", "zone": zone}, justify="space-between",
                          align="flex-end", children=zone_hero({})),
                zone_chart({"type": "zone-chart", "zone": zone}, zone, 190),
                dmc.Alert("–", id={"type": "zone-decision", "zone": zone},
                          color="gray", variant="light", p="xs"),
                dmc.SimpleGrid(id={"type": "zone-facts", "zone": zone}, cols=2,
                               spacing="xs", children=zone_facts(zone, {})),
            ]),
        ],
    )
