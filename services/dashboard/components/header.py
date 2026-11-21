import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from core import RADIUS


def header():
    return dmc.Group(
        h="100%", px="md", justify="space-between", wrap="nowrap",
        children=[
            _title(),
            dmc.Group(gap="sm", wrap="nowrap", children=[_clear_button(), _status_menu()]),
        ],
    )


def _title():
    return dmc.Stack(gap=0, children=[
        dmc.Title(['LAB6 "', html.I("IoT monitoring with SOA"), '"'], order=3),
        dmc.Text("Service Design & Engineering @UniTN", size="sm", c="dimmed"),
    ])


def _clear_button():
    return dmc.Tooltip(
        id="clear-tip", label="Clear historical data",
        children=dmc.ActionIcon(
            DashIconify(icon="tabler:rotate-clockwise-2", width=20),
            id="clear-history", variant="default", radius="xl", size="lg",
        ),
    )


def _status_menu():
    """Status button and its dropdown, toggled by toggle_panels() in callbacks.py."""
    return dmc.Box(pos="relative", children=[
        dmc.Button(
            "···", id="conn", color="gray", variant="light", radius="xl", size="compact-md",
            leftSection=DashIconify(icon="tabler:circle-chevron-down", width=16),
        ),
        dmc.Paper(
            id="status-details", withBorder=True, shadow="md", radius=RADIUS, p="sm",
            display="none", pos="absolute", right=0, top="calc(100% + 10px)", w="360px",
            style={"zIndex": 1000},     # above the click-catcher scrim (900)
            children=dmc.Text("waiting for data…", size="sm"),
        ),
    ])


def status_rows(checks, last_update):
    """Return the dropdown content: the update time and one row per health check."""
    rows = [dmc.Text(f"Last update {last_update}", size="xs", c="dimmed",
                     ta="right", fs="italic", mb="xs")]
    rows += [_check_row(*check) for check in checks]
    return dmc.Stack(gap="xs", children=rows)


def _check_row(label, ok, detail):
    return dmc.Group(justify="space-between", wrap="nowrap", gap="xs", children=[
        dmc.Group(gap=6, wrap="nowrap", children=[
            dmc.Text("●", size="xs", c="green.6" if ok else "red.6"),
            dmc.Text(label, size="sm"),
        ]),
        dmc.Text(detail, size="xs", ta="right", c="dimmed" if ok else "red.7"),
    ])