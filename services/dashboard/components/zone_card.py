import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from core import RADIUS, lock, water_s
from viewmodel import (air_text, chart_series, command_text, decision_info,
                       sprinkler_state, spread_text, vpd_text)


def weather_layers():
    """Rain / sky (fog + sun) / ground layers, shared by the zone cards and the
    fullscreen modal. Use as the FIRST children of an element with class `zone`."""
    return [
        html.Div(className="rain-layer"),
        html.Div(className="sky", children=[
            html.Div(className="fog fog-a"),
            html.Div(className="fog fog-b"),
            html.Div(className="fog fog-c"),
        ]),
        html.Div(className="ground"),
    ]


def weather_class(info, base="zone"):
    """`base` plus the state classes that drive the weather CSS."""
    sprinkler = (info.get("sprinkler") or {}).get("state")
    return (base + (" raining" if info.get("rain") == "on" else "")
            + (" watering" if sprinkler == "on" else ""))


def fact(label, value, icon=None, big=False):
    return dmc.Paper(
        p="sm" if big else "xs", radius="md", bg="var(--mantine-color-gray-0)",
        children=dmc.Group(justify="space-between", wrap="nowrap", gap="xs", children=[
            dmc.Group(gap="xs", wrap="nowrap", align="center", children=[
                *([DashIconify(icon=icon, width=20 if big else 16)] if icon else []),
                dmc.Text(label, size="sm" if big else "xs", c="dimmed", fw=600, tt="uppercase"),
            ]),
            dmc.Text(value, size="sm" if big else "xs", ta="right"),
        ]),
    )


def zone_facts(zone, info, big=False):
    with lock:
        watered = water_s.get(zone, 0.0)
    h, rem = divmod(int(watered), 3600)
    m, s = divmod(rem, 60)
    return [
        fact("air", air_text(info), "tabler:temperature", big),
        fact("VPD", vpd_text(info), "tabler:droplet", big),
        fact("agreement", spread_text(info), "tabler:activity", big),
        (fact("watered", f"{h:02d} h {m:02d} min {s:02d} s", "tabler:history", big) if h > 0 
         else fact("watered", f"{m:02d} min {s:02d} s", "tabler:history", big)) if watered > 0 
         else fact("watered", "never", "tabler:history", big),
    ]


def zone_hero(info, big=False):
    """Two compact dot-badges: soil moisture + signed distance to threshold."""
    median = (info.get("soil") or {}).get("median")
    thr = (info.get("decision") or {}).get("soil_threshold")

    if median is None:
        return [dmc.Badge("avg. soil moisture", color="gray", variant="light",
                          size="xl" if big else "md")]

    moisture = dmc.Badge(
        dmc.Group(gap=6, wrap="nowrap", align="center", children=[
            dmc.Text(f"{median:.0f}%", size="xl" if big else "md", fw=700),
            dmc.Text("avg. soil moisture", size="sm" if big else "xs", c="dimmed"),
        ]),
        color="blue", variant="light", size="xl" if big else "lg",
    )

    if thr is None:
        delta = dmc.Badge("no threshold", color="gray", variant="dot",
                          size="xl" if big else "md")
    else:
        gap = median - thr
        delta = dmc.Badge(f"{gap:+.0f} % from θ",
                          color="green" if gap >= 0 else "orange",
                          variant="dot", size="xl" if big else "md")

    return [moisture, delta]


DECISION_ICONS = {
    "Irrigating": "tabler:droplets",
    "Stopped": "tabler:circle-check",
    "Hold": "tabler:clock",
    "Idle": "tabler:minus",
}


def decision_row(info, big=False):
    """Compact status dot-badge + muted detail, matching the hero/sprinkler badges."""
    word, detail, color, pulse = decision_info(info)
    icon = DECISION_ICONS.get(word, "tabler:minus")
    children = [
        DashIconify(icon=icon, width=20 if big else 16,
                    style={"color": f"var(--mantine-color-{color}-filled)"}),
        dmc.Badge(word, variant="dot", color=color, size="xl" if big else "lg",
                  className="sp-pulse" if pulse else ""),
    ]
    if detail:
        children.append(dmc.Text(detail, size="sm" if big else "xs", c="dimmed", tt="uppercase"))
    return children


def sprinkler_badge(info, big=False):
    """SPRINKLER dot-badge reflecting the live valve state (card badge mirror)."""
    color, variant, pulse = sprinkler_state(info)
    return dmc.Badge(
        dmc.Group(gap=4, wrap="nowrap",
                  children=[dmc.Text("SPRINKLER", size="sm" if big else "xs", fw=600)]),
        color=color, variant=variant, size="xl" if big else "lg",
        className="sp-pulse" if pulse else "")


def modal_title(zone, info):
    """Title row for the fullscreen modal: zone name + live SPRINKLER badge."""
    return [dmc.Text(zone.replace("zone", "Zone #"), fw=700, size="xl"),
            sprinkler_badge(info, big=True)]


def zone_chart(id_, zone, height):
    return dmc.CompositeChart(
        id=id_, h=height, data=[], dataKey="t", series=chart_series(zone),
        curveType="natural", withDots=False, withLegend=False, unit="%",
        yAxisProps={"domain": [0, 100]}, referenceLines=[], referenceAreas=[],
        gridAxis="y",
        # recharts replays its draw animation on every data update (every second): off.
        areaProps={"strokeWidth": 3, "isAnimationActive": False},
        lineProps={"strokeWidth": 1, "isAnimationActive": False},
    )


def zone_card(zone):
    return dmc.Paper(
        id={"type": "zone-card", "zone": zone},
        className="zone", withBorder=True, radius=RADIUS, shadow="sm", p="md", pb="lg",
        children=[
            *weather_layers(),
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
                dmc.Group(id={"type": "zone-decision", "zone": zone}, align="center", gap="xs", wrap="nowrap", children=decision_row({})),
                dmc.Space(h="0.3125rem"),
                dmc.SimpleGrid(id={"type": "zone-facts", "zone": zone}, cols=1, spacing="sm", children=zone_facts(zone, {})),
            ]),
        ],
    )