import dash_mantine_components as dmc
from dash import html
from dash_iconify import DashIconify

from core import RADIUS


def status_rows(checks, last_update):
    rows = [dmc.Text(f"Last update {last_update}", size="xs", c="dimmed", ta="right", fs="italic", mb="xs")]
    for label, ok, detail in checks:
        rows.append(dmc.Group(justify="space-between", wrap="nowrap", gap="xs", children=[
            dmc.Group(gap=6, wrap="nowrap", children=[
                dmc.Text("●", size="xs", c="green.6" if ok else "red.6"),
                dmc.Text(label, size="sm"),
            ]),
            dmc.Text(detail, size="xs", ta="right", c="dimmed" if ok else "red.7"),
        ]))
    return dmc.Stack(gap="xs", children=rows)


def header():
    return dmc.Group(h="100%", px="md", justify="space-between", wrap="nowrap", children=[
        dmc.Stack(gap=0, children=[
            dmc.Title(
                ['LAB6 "', html.I("IoT monitoring with SOA"), '"'],
                order=3
            ),
            dmc.Text("Service Design & Engineering @UniTN", size="sm", c="dimmed"),
        ]),
        dmc.Group(gap="sm", wrap="nowrap", children=[
            # Native DMC way: DashIconify bundles the full Iconify dataset
            # locally, so "tabler:..." icons render with no CDN / network.
            # ActionIcon `size` sets the button box only — icon size is set
            # separately via `width` on the icon component (docs pattern).
            dmc.Tooltip(id="clear-tip", label="Clear historical data", children=
                dmc.ActionIcon(
                    DashIconify(icon="tabler:rotate-clockwise-2", width=20), 
                    id="clear-history", variant="default", radius="xl", size="lg")
                ),
            # Always-mounted Paper instead of dmc.Popover: DMC's floating
            # overlays (Popover, Drawer) snapshot their children while open,
            # so callback updates never reach the live dropdown content.
            dmc.Box(pos="relative", children=[
                # leftSection (not children): the refresh callback rewrites
                # `children` ("LIVE" / "n issue(s)") every tick, and `color`
                # too — but leftSection is a separate prop, so the chevron
                # survives those updates. "···" is just the bootstrap label
                # shown for the first second before the first health check.
                dmc.Button("···", id="conn", color="gray", variant="light", radius="xl", size="compact-md",
                    leftSection=DashIconify(icon="tabler:circle-chevron-down", width=16)
                ),
                dmc.Paper(id="status-details", withBorder=True, shadow="md", radius=RADIUS, p="sm", display="none",
                    style={"position": "absolute", "right": 0, "top": "calc(100% + 10px)", "width": "360px", "zIndex": 1000},
                    children=dmc.Text("waiting for data…", size="sm")
                ),
            ]),
        ]),
    ])
