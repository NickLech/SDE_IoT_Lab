import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from core import RADIUS, lock, water_s
from viewmodel import (air_text, chart_series, command_text, decision_info,
                       sprinkler_state, spread_text, vpd_text)

DECISION_ICONS = {
    "Irrigating": "tabler:droplets",
    "Stopped": "tabler:circle-check",
    "Hold": "tabler:clock",
    "Idle": "tabler:minus",
}


def weather_layers():
    """Return the rain, sky (fog and sun) and ground layers of the weather animation.

    They must be the first children of an element with the class `zone`.
    """
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
    """Return `base` plus the `raining` / `watering` classes that drive the weather CSS."""
    sprinkler = (info.get("sprinkler") or {}).get("state")
    return (base + (" raining" if info.get("rain") == "on" else "")
            + (" watering" if sprinkler == "on" else ""))


def zone_card(zone):
    return dmc.Paper(
        id={"type": "zone-card", "zone": zone},
        className="zone", withBorder=True, radius=RADIUS, shadow="sm", p="md", pb="lg",
        children=[
            *weather_layers(),
            dmc.Stack(gap="xs", children=[
                dmc.Group(justify="space-between", wrap="nowrap", children=[
                    dmc.Text(_zone_label(zone), fw=700, size="lg"),
                    dmc.Group(gap="xs", wrap="nowrap", children=[
                        _sprinkler_badge({}, id={"type": "zone-sprinkler", "zone": zone}),
                        _expand_button(zone),
                    ]),
                ]),
                dmc.Group(id={"type": "zone-hero", "zone": zone}, justify="space-between",
                          align="flex-end", children=zone_hero({})),
                dmc.Space(h="xs"),
                zone_chart({"type": "zone-chart", "zone": zone}, zone, 190),
                dmc.Space(h="xs"),
                dmc.Group(id={"type": "zone-decision", "zone": zone}, align="center",
                          gap="xs", wrap="nowrap", children=decision_row({})),
                dmc.Space(h=5),
                dmc.SimpleGrid(id={"type": "zone-facts", "zone": zone}, cols=1,
                               spacing="sm", children=zone_facts(zone, {})),
            ]),
        ],
    )


def _zone_label(zone):
    return zone.replace("zone", "Zone #")


def _expand_button(zone):
    return dmc.Tooltip(
        label="Fullscreen",
        children=dmc.ActionIcon(
            DashIconify(icon="tabler:arrows-maximize", width=16),
            id={"type": "zone-expand", "zone": zone},
            variant="default", radius=RADIUS, size="md",
        ),
    )


def zone_hero(info, big=False):
    """Return the soil-moisture badge and the badge with its signed distance from θ."""
    median = (info.get("soil") or {}).get("median")
    threshold = (info.get("decision") or {}).get("soil_threshold")
    badge_size = "xl" if big else "md"

    if median is None:
        return [dmc.Badge("median soil moisture", color="gray", variant="light", size=badge_size)]

    moisture = dmc.Badge(
        dmc.Group(gap=6, wrap="nowrap", align="center", children=[
            dmc.Text(f"{median:.0f}%", size="xl" if big else "md", fw=700),
            dmc.Text("median soil moisture", size="sm" if big else "xs", c="dimmed"),
        ]),
        color="blue", variant="light", size="xl" if big else "lg",
    )

    if threshold is None:
        delta = dmc.Badge("no threshold", color="gray", variant="dot", size=badge_size)
    else:
        gap = median - threshold
        delta = dmc.Badge(f"{gap:+.0f} % from θ", color="green" if gap >= 0 else "orange",
                          variant="dot", size=badge_size)

    return [moisture, delta]


def decision_row(info, big=False):
    """Return the decision status badge, with its detail as muted text."""
    word, detail, color, pulse = decision_info(info)
    row = [
        DashIconify(icon=DECISION_ICONS.get(word, DECISION_ICONS["Idle"]),
                    width=20 if big else 16,
                    style={"color": f"var(--mantine-color-{color}-filled)"}),
        dmc.Badge(word, variant="dot", color=color, size="xl" if big else "lg",
                  className="sp-pulse" if pulse else ""),
    ]
    if detail:
        row.append(dmc.Text(detail, size="sm" if big else "xs", c="dimmed", tt="uppercase"))
    return row


def zone_facts(zone, info, big=False):
    with lock:
        watered = water_s.get(zone, 0.0)
    air = air_text(info)
    return [
        _fact("air", air, "tabler:temperature", big,
              color="red" if "humidity missing" in air else None),
        _fact("VPD", vpd_text(info), "tabler:droplet", big),
        _fact("agreement", spread_text(info), "tabler:activity", big),
        _fact("watered", _duration_text(watered), "tabler:history", big),
    ]


def _fact(label, value, icon=None, big=False, color=None):
    value_props = {"ta": "right"}
    if color:
        value_props["c"] = color

    return dmc.Paper(
        p="sm" if big else "xs", radius="md", bg="var(--mantine-color-gray-0)",
        children=dmc.Group(justify="space-between", wrap="nowrap", gap="xs", children=[
            dmc.Group(gap="xs", wrap="nowrap", align="center", children=[
                *([DashIconify(icon=icon, width=20 if big else 16)] if icon else []),
                dmc.Text(label, size="sm" if big else "xs", c="dimmed", fw=600, tt="uppercase"),
            ]),
            dmc.Text(value, size="sm" if big else "xs", **value_props),
        ]),
    )


def _duration_text(seconds):
    """Format a duration as "never", "MM min SS s" or "HH h MM min SS s"."""
    if seconds <= 0:
        return "never"
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours:02d} h {minutes:02d} min {secs:02d} s"
    return f"{minutes:02d} min {secs:02d} s"


def modal_title(zone, info):
    """Return the modal title row: zone name and live sprinkler badge."""
    return [dmc.Text(_zone_label(zone), fw=700, size="xl"), _sprinkler_badge(info, big=True)]


def _sprinkler_badge(info, big=False, **props):
    """Return the SPRINKLER badge for the live valve state; `props` go to the Badge."""
    color, variant, pulse = sprinkler_state(info)
    return dmc.Badge(
        dmc.Group(gap=4, wrap="nowrap",
                  children=[dmc.Text("SPRINKLER", size="sm" if big else "xs", fw=600)]),
        color=color, variant=variant, size="xl" if big else "lg",
        className="sp-pulse" if pulse else "", **props,
    )


def zone_chart(id_, zone, height):
    return dmc.CompositeChart(
        id=id_, h=height, data=[], dataKey="t", series=chart_series(zone),
        curveType="natural", withDots=False, withLegend=False, unit="%",
        yAxisProps={"domain": [0, 100]}, referenceLines=[], referenceAreas=[],
        gridAxis="y",
        # Recharts would replay its draw animation on every data update.
        areaProps={"strokeWidth": 3, "isAnimationActive": False},
        lineProps={"strokeWidth": 1, "isAnimationActive": False},
    )