import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from core import RADIUS, lock, water_s
from viewmodel import air_text, chart_series, command_text, decision_info, spread_text, vpd_text


def fact(label, value, icon=None):
    return dmc.Paper(
        p="xs", radius="md", bg="var(--mantine-color-gray-0)",
        children=dmc.Group(justify="space-between", wrap="nowrap", gap="xs", children=[
            dmc.Group(gap="xs", wrap="nowrap", align="center", children=[
                *([DashIconify(icon=icon, width=16)] if icon else []),
                dmc.Text(label, size="xs", c="dimmed", fw=600, tt="uppercase"),
            ]),
            dmc.Text(value, size="xs", ta="right"),
        ]),
    )


def zone_facts(zone, info):
    with lock:
        watered = water_s.get(zone, 0.0)
    h, rem = divmod(int(watered), 3600)
    m, s = divmod(rem, 60)
    return [
        fact("air", air_text(info), "tabler:temperature"),
        fact("VPD", vpd_text(info), "tabler:droplet"),
        fact("agreement", spread_text(info), "tabler:activity"),
        (fact("watered", f"{h:02d} h {m:02d} min {s:02d} s", "tabler:history") if h > 0 
         else fact("watered", f"{m:02d} min {s:02d} s", "tabler:history")) if watered > 0 
         else fact("watered", "never", "tabler:history"),
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


DECISION_ICONS = {
    "Irrigating": "tabler:droplets",
    "Stopped": "tabler:circle-check",
    "Hold": "tabler:clock",
    "Idle": "tabler:minus",
}


def decision_row(info):
    """Compact status dot-badge + muted detail, matching the hero/sprinkler badges."""
    word, detail, color, pulse = decision_info(info)
    icon = DECISION_ICONS.get(word, "tabler:minus")
    children = [
        DashIconify(icon=icon, width=16,
                    style={"color": f"var(--mantine-color-{color}-filled)"}),
        dmc.Badge(word, variant="dot", color=color, size="lg",
                  className="sp-pulse" if pulse else ""),
    ]
    if detail:
        children.append(dmc.Text(detail, size="xs", c="dimmed", tt="uppercase"))
    return children


def zone_chart(id_, zone, height):
    return dmc.CompositeChart(
        id=id_, h=height, data=[], dataKey="t", series=chart_series(zone),
        curveType="monotone", withDots=False, withLegend=False, unit="%",
        yAxisProps={"domain": [0, 100]}, referenceLines=[], gridAxis="y",
    )


def zone_card(zone):
    return dmc.Paper(
        id={"type": "zone-card", "zone": zone},
        className="zone", withBorder=True, radius=RADIUS, shadow="sm", p="md", pb="lg",
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
                dmc.Group(id={"type": "zone-decision", "zone": zone}, align="center", gap="xs", wrap="nowrap", children=decision_row({})),
                dmc.Space(h="0.3125rem"),
                dmc.SimpleGrid(id={"type": "zone-facts", "zone": zone}, cols=1, spacing="sm", children=zone_facts(zone, {})),
            ]),
        ],
    )
