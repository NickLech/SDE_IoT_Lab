// Custom y-axis tick renderer for the Assignment rain chart:
// renders the numeric ticks 0 / 1 as "<tabler icon> (0)" and "<tabler icon> (1)" (sun / cloud-rain).
// Used from Python as yAxisProps={"tick": {"function": "rainTick"}}
// (dmc "functions as props": resolved from window.dashMantineFunctions).

var dmcfuncs = window.dashMantineFunctions = window.dashMantineFunctions || {};

dmcfuncs.rainTick = function (props) {
    const React = window.React;
    const Icon = window.dash_iconify && window.dash_iconify.DashIconify;
    const value = props.payload ? Number(props.payload.value) : NaN;

    // Label layout: "<icon> (0)" / "<icon> (1)", right edge aligned with the temperature
    // chart's tick labels (both end 18px left of the plot area). The group origin sits at
    // that column, so the (0)/(1) text is anchored "end" at x=0 and the icon goes to its left.
    const size = 16;     // icon box (the glyph itself is ~14px, ~1px viewBox padding per side)
    const gap = 5;       // space between icon and the (0)/(1) text
    const textW = 17;    // rendered width of "(0)"/"(1)" at 12px
    const dx = -10;      // keeps the text's right edge at the temp labels' column (measured live: grid at 135, text right at 117 = 18px gap)
    const dy = -8;       // center the label vertically on the tick point

    const x = (props.x || 0) + dx;
    const y = (props.y || 0) + dy;
    const label = value === 1 ? "(1)" : "(0)";

    const text = React.createElement(
        "text",
        { x: 0, y: 12, fill: "currentColor", "font-size": 12, "text-anchor": "end" },  // baseline for font 12
        label
    );

    if (!Icon) {   // fallback if the iconify bundle is not loaded: number only
        return React.createElement("g", { transform: `translate(${x},${y})` }, text);
    }

    // the icon glyph's ink starts ~2px into its box and ends ~14px, so offset its box by:
    const iconX = -(gap + textW + size - 2);
    return React.createElement(
        "g",
        { transform: `translate(${x},${y})` },
        React.createElement("g", { transform: `translate(${iconX},0)` },
            React.createElement(Icon, {
                icon: value === 1 ? "tabler:cloud-rain" : "tabler:sun",
                width: size,
                height: size,
            })),
        text
    );
};
