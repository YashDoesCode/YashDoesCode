#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_SVG = ROOT_DIR / "timeline.svg"

GRAPHQL_URL = "https://api.github.com/graphql"


def get_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("METRICS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    try:
        proc = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
        token = proc.stdout.strip()
        if token:
            return token
    except Exception:
        pass
    print("Error: No GitHub token found. Please export GH_TOKEN.", file=sys.stderr)
    sys.exit(1)


def execute_graphql(token: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "YashDoesCode-Profile-Timeline",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "errors" in data and not data.get("data"):
                raise RuntimeError(f"GraphQL error: {data['errors']}")
            return data.get("data", {})
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} error: {err_msg}") from e


def fetch_timeline_data(token: str) -> dict[str, Any]:
    user_query = """
    query {
      viewer {
        createdAt
        login
      }
    }
    """
    user_data = execute_graphql(token, user_query)
    viewer = user_data.get("viewer") or {}
    created_str = viewer.get("createdAt") or "2024-01-01T00:00:00Z"
    start_dt = dt.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)

    intervals: list[tuple[str, str]] = []
    cur = start_dt
    while cur < now:
        nxt = min(cur + dt.timedelta(days=365), now)
        intervals.append((cur.strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%Y-%m-%dT%H:%M:%SZ")))
        cur = nxt

    cal_query = """
    query($from: DateTime!, $to: DateTime!) {
      viewer {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks {
              firstDay
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """

    all_days: dict[str, int] = {}
    last_year_weeks: list[dict[str, Any]] = []
    yearly_total: int = 0

    for idx, (f_date, t_date) in enumerate(intervals):
        data = execute_graphql(token, cal_query, {"from": f_date, "to": t_date})
        cal = data.get("viewer", {}).get("contributionsCollection", {}).get("contributionCalendar", {})
        if idx == len(intervals) - 1:
            yearly_total = cal.get("totalContributions", 0)
        for week in cal.get("weeks", []):
            for day in week.get("contributionDays", []):
                all_days[day["date"]] = day["contributionCount"]

    current_cal_query = """
    query {
      viewer {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              firstDay
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    current_data = execute_graphql(token, current_cal_query)
    cur_cal = current_data.get("viewer", {}).get("contributionsCollection", {}).get("contributionCalendar", {})
    last_year_weeks = cur_cal.get("weeks", [])
    if cur_cal.get("totalContributions"):
        yearly_total = cur_cal["totalContributions"]

    sorted_dates = sorted(all_days.keys())
    cur_streak = 0
    cur_start: str | None = None
    max_streak = 0
    max_start: str | None = None
    max_end: str | None = None

    for d_str in sorted_dates:
        count = all_days[d_str]
        if count > 0:
            if cur_streak == 0:
                cur_start = d_str
            cur_streak += 1
            if cur_streak > max_streak:
                max_streak = cur_streak
                max_start = cur_start
                max_end = d_str
        else:
            cur_streak = 0
            cur_start = None

    return {
        "yearly_total": yearly_total,
        "max_streak": max_streak,
        "streak_start": max_start,
        "streak_end": max_end,
        "weeks": last_year_weeks,
    }


def render_svg(data: dict[str, Any]) -> str:
    streak = data["max_streak"]
    s_start_str = data["streak_start"] or ""
    s_end_str = data["streak_end"] or ""

    s_start_dt = dt.date.fromisoformat(s_start_str) if s_start_str else None
    s_end_dt = dt.date.fromisoformat(s_end_str) if s_end_str else None

    weeks = data["weeks"]
    num_weeks = len(weeks)
    weekly_totals: list[int] = []
    week_start_dates: list[dt.date] = []

    for w in weeks:
        days = w.get("contributionDays", [])
        total = sum(d.get("contributionCount", 0) for d in days)
        weekly_totals.append(total)
        week_start_dates.append(dt.date.fromisoformat(w["firstDay"]))

    chart_start_date = week_start_dates[0] if week_start_dates else dt.date.today()
    chart_end_date = week_start_dates[-1] + dt.timedelta(days=6) if week_start_dates else dt.date.today()

    is_in_chart = False
    if s_start_dt and s_end_dt:
        if s_start_dt >= chart_start_date:
            is_in_chart = True

    date_fmt_start = f"{s_start_dt.strftime('%b')} {s_start_dt.day}, {s_start_dt.year}" if s_start_dt else ""
    date_fmt_end = f"{s_end_dt.strftime('%b')} {s_end_dt.day}, {s_end_dt.year}" if s_end_dt else ""

    if is_in_chart:
        subtitle = f"From {date_fmt_start} to {date_fmt_end}, highlighted below."
    else:
        subtitle = f"From {date_fmt_start} to {date_fmt_end} · all-time best"

    chart_x = 32.0
    chart_width = 816.0
    chart_y_top = 115.0
    chart_baseline = 250.0
    chart_height = chart_baseline - chart_y_top

    max_count = max(weekly_totals) if weekly_totals else 1
    if max_count == 0:
        max_count = 1

    points: list[tuple[float, float]] = []
    for i, count in enumerate(weekly_totals):
        px = chart_x + (i / max(num_weeks - 1, 1)) * chart_width
        py = chart_baseline - (count / max_count) * chart_height
        points.append((round(px, 1), round(py, 1)))

    line_d = " ".join([f"M{points[0][0]},{points[0][1]}"] + [f"L{px},{py}" for px, py in points[1:]])
    area_d = f"{line_d} L{points[-1][0]},{chart_baseline} L{points[0][0]},{chart_baseline} Z"

    peak_idx = weekly_totals.index(max(weekly_totals)) if weekly_totals else 0
    peak_count = weekly_totals[peak_idx] if weekly_totals else 0
    peak_x, peak_y = points[peak_idx]
    peak_date = week_start_dates[peak_idx] if peak_idx < len(week_start_dates) else dt.date.today()
    peak_label_text = f"{peak_count:,} · week of {peak_date.strftime('%b')} {peak_date.day}"

    if peak_x > 700:
        label_anchor = "end"
        label_x = peak_x - 10
    elif peak_x < 150:
        label_anchor = "start"
        label_x = peak_x + 10
    else:
        label_anchor = "middle"
        label_x = peak_x
    label_y = peak_y - 10

    band_svg = ""
    if s_start_dt and s_end_dt and s_end_dt >= chart_start_date and s_start_dt <= chart_end_date:
        band_start_date = max(s_start_dt, chart_start_date)
        band_end_date = min(s_end_dt, chart_end_date)

        b_start_idx = 0
        b_end_idx = num_weeks - 1
        for i, w_date in enumerate(week_start_dates):
            w_end = w_date + dt.timedelta(days=6)
            if w_end >= band_start_date and b_start_idx == 0:
                b_start_idx = i
            if w_date <= band_end_date:
                b_end_idx = i

        bx1 = chart_x + (b_start_idx / max(num_weeks - 1, 1)) * chart_width
        bx2 = chart_x + (min(b_end_idx + 1, num_weeks - 1) / max(num_weeks - 1, 1)) * chart_width
        bw = max(bx2 - bx1, 12.0)
        band_svg = f'<rect class="streak-band" x="{round(bx1, 1)}" y="{round(chart_y_top - 15, 1)}" width="{round(bw, 1)}" height="{round(chart_height + 15, 1)}" rx="4"/>'

    month_labels: list[str] = []
    last_month: int | None = None
    for i, w_date in enumerate(week_start_dates):
        if w_date.month != last_month:
            last_month = w_date.month
            mx = chart_x + (i / max(num_weeks - 1, 1)) * chart_width
            m_name = w_date.strftime("%b")
            month_labels.append(f'<text class="lbl" x="{round(mx, 1)}" y="272">{m_name}</text>')
    months_str = "".join(month_labels)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="880" height="284" viewBox="0 0 880 284" role="img" aria-label="Contributions week by week; longest streak {streak} days">
<defs>
  <linearGradient id="areaGradient" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#3fb950" stop-opacity="0.32"/>
    <stop offset="100%" stop-color="#3fb950" stop-opacity="0.0"/>
  </linearGradient>
  <linearGradient id="areaGradientLight" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#1a7f37" stop-opacity="0.25"/>
    <stop offset="100%" stop-color="#1a7f37" stop-opacity="0.0"/>
  </linearGradient>
</defs>
<style>
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; }}
    .line {{ stroke-dashoffset: 0 !important; }}
    .area {{ opacity: 1 !important; }}
    .streak-band {{ opacity: 0.14 !important; }}
    .peak-dot {{ opacity: 1 !important; transform: none !important; }}
    .peak-label {{ opacity: 1 !important; }}
  }}
  .subhead {{ font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; font-weight: 600; letter-spacing: .14em; fill: #3fb950; }}
  .headline {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 26px; font-weight: 700; letter-spacing: -.02em; fill: #f0f6fc; }}
  .subtitle {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 15px; fill: #9198a1; }}
  .divider {{ stroke: #262c36; stroke-width: 1px; }}
  .lbl {{ font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 11px; fill: #7d8590; text-anchor: middle; }}
  .streak-band {{ fill: #3fb950; opacity: 0; animation: bandFade 0.8s ease-out 1.6s forwards; }}
  .area {{ fill: url(#areaGradient); opacity: 0; animation: areaFade 0.8s ease-out 1.6s forwards; }}
  .line {{ fill: none; stroke: #3fb950; stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; stroke-dasharray: 1; stroke-dashoffset: 1; animation: drawLine 2s ease-out forwards; }}
  .peak-dot {{ fill: #3fb950; opacity: 0; transform-origin: {peak_x}px {peak_y}px; animation: popDot 0.5s ease-out 2.0s forwards, pulseDot 2.5s ease-in-out 2.5s infinite; }}
  .peak-label {{ font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 11px; font-weight: 600; fill: #3fb950; opacity: 0; animation: areaFade 0.5s ease-out 2.1s forwards; }}

  @keyframes drawLine {{
    to {{ stroke-dashoffset: 0; }}
  }}
  @keyframes bandFade {{
    to {{ opacity: 0.14; }}
  }}
  @keyframes areaFade {{
    to {{ opacity: 1; }}
  }}
  @keyframes popDot {{
    0% {{ opacity: 0; transform: scale(0); }}
    70% {{ opacity: 1; transform: scale(1.3); }}
    100% {{ opacity: 1; transform: scale(1); }}
  }}
  @keyframes pulseDot {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.25); }}
  }}

  @media (prefers-color-scheme: light) {{
    .subhead {{ fill: #1a7f37; }}
    .headline {{ fill: #1f2328; }}
    .subtitle {{ fill: #59636e; }}
    .divider {{ stroke: #e4e8ec; }}
    .lbl {{ fill: #59636e; }}
    .streak-band {{ fill: #1a7f37; }}
    .area {{ fill: url(#areaGradientLight); }}
    .line {{ stroke: #1a7f37; }}
    .peak-dot {{ fill: #1a7f37; }}
    .peak-label {{ fill: #1a7f37; }}
  }}
</style>
<text class="subhead" x="32" y="38">THE YEAR, WEEK BY WEEK</text>
<text class="headline" x="32" y="68">Longest streak: {streak} days in a row</text>
<text class="subtitle" x="32" y="94">{html.escape(subtitle)}</text>
{band_svg}
<path d="{area_d}" class="area"/>
<path d="{line_d}" class="line" pathLength="1"/>
<line class="divider" x1="32" y1="250" x2="848" y2="250"/>
{months_str}
<circle class="peak-dot" cx="{peak_x}" cy="{peak_y}" r="4.5"/>
<text class="peak-label" x="{label_x}" y="{label_y}" text-anchor="{label_anchor}">{peak_label_text}</text>
</svg>
"""


def main() -> None:
    token = get_token()
    data = fetch_timeline_data(token)
    svg_content = render_svg(data)
    with OUTPUT_SVG.open("w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated {OUTPUT_SVG} ({len(svg_content)} bytes)")
    print(f"Longest streak: {data['max_streak']} days ({data['streak_start']} to {data['streak_end']})")
    print(f"Last year total: {data['yearly_total']}")


if __name__ == "__main__":
    main()
