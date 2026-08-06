"""Minimal inline-SVG line charts for the printable experiment report.

Deliberately dependency-free: the report has to be a single self-contained HTML
file that prints correctly offline, so pulling in matplotlib (and emitting a
binary image) would work against that. These are simple polylines with axes —
enough to show the shape of a residual/flow/current trace.
"""
from xml.sax.saxutils import escape

WIDTH = 720
HEIGHT = 220
PAD_LEFT = 52
PAD_RIGHT = 14
PAD_TOP = 16
PAD_BOTTOM = 30


def _nice_bounds(values):
    lo, hi = min(values), max(values)
    if lo == hi:
        # A flat trace still needs a visible band or the polyline collapses onto
        # the axis and reads as "no data".
        pad = abs(lo) * 0.1 or 1.0
        return lo - pad, hi + pad
    span = hi - lo
    return lo - span * 0.08, hi + span * 0.08


def line_chart(series, title, y_label, color="#2563eb", shaded_spans=None, unit=""):
    """series: list of (x, y). shaded_spans: list of (x_start, x_end) drawn as
    highlight bands — used to mark ground-truth leak windows."""
    points = [(float(x), float(y)) for x, y in series if y is not None]
    if len(points) < 2:
        return f'<div class="chart-empty">No data available for {escape(title)}</div>'

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = _nice_bounds(ys)
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0

    plot_w = WIDTH - PAD_LEFT - PAD_RIGHT
    plot_h = HEIGHT - PAD_TOP - PAD_BOTTOM

    def px(x):
        return PAD_LEFT + (x - x_min) / x_span * plot_w

    def py(y):
        return PAD_TOP + (1 - (y - y_min) / y_span) * plot_h

    parts = [f'<svg class="chart" viewBox="0 0 {WIDTH} {HEIGHT}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(title)}">']

    for span_start, span_end in (shaded_spans or []):
        x0, x1 = px(max(span_start, x_min)), px(min(span_end, x_max))
        if x1 > x0:
            parts.append(
                f'<rect x="{x0:.1f}" y="{PAD_TOP}" width="{x1 - x0:.1f}" height="{plot_h}" '
                f'fill="#fecaca" opacity="0.55" />'
            )

    # Horizontal gridlines + y-axis labels
    for i in range(5):
        val = y_min + (y_span * i / 4)
        y = py(val)
        parts.append(f'<line x1="{PAD_LEFT}" y1="{y:.1f}" x2="{WIDTH - PAD_RIGHT}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1" />')
        parts.append(f'<text x="{PAD_LEFT - 6}" y="{y + 3.5:.1f}" text-anchor="end" class="axis-label">{val:.2f}</text>')

    # X-axis labels in elapsed seconds from the start of the run
    for i in range(5):
        x_val = x_min + (x_span * i / 4)
        x = px(x_val)
        parts.append(f'<text x="{x:.1f}" y="{HEIGHT - 10}" text-anchor="middle" class="axis-label">{x_val - x_min:.0f}s</text>')

    path = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in points)
    parts.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round" />')
    parts.append(f'<line x1="{PAD_LEFT}" y1="{PAD_TOP}" x2="{PAD_LEFT}" y2="{HEIGHT - PAD_BOTTOM}" stroke="#94a3b8" stroke-width="1" />')
    parts.append(f'<line x1="{PAD_LEFT}" y1="{HEIGHT - PAD_BOTTOM}" x2="{WIDTH - PAD_RIGHT}" y2="{HEIGHT - PAD_BOTTOM}" stroke="#94a3b8" stroke-width="1" />')
    parts.append("</svg>")

    label = f"{escape(y_label)}{f' ({escape(unit)})' if unit else ''}"
    return (
        f'<figure class="chart-block"><figcaption><strong>{escape(title)}</strong>'
        f'<span class="chart-axis-note">y: {label} · x: elapsed time</span></figcaption>'
        + "".join(parts)
        + "</figure>"
    )
