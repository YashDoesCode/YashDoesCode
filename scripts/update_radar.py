#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_SVG = ROOT_DIR / "radar.svg"

GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_USER = "YashDoesCode"
NUM_FRAMES = 20
ANIM_START = 1.5
ANIM_DUR = 1.2


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


def execute_graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "YashDoesCode-Profile-Radar",
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


def fetch_radar_data(token: str, username: str) -> dict[str, int]:
    now = dt.datetime.now(dt.timezone.utc)
    one_year_ago = now - dt.timedelta(days=365)
    from_date = one_year_ago.strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    from_ymd = one_year_ago.strftime("%Y-%m-%d")

    pr_query = f"is:pr author:{username} created:>={from_ymd}"
    review_query = f"is:pr reviewed-by:{username} -author:{username} created:>={from_ymd}"

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!, $prQuery: String!, $reviewQuery: String!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalRepositoryContributions
        }
      }
      prs: search(query: $prQuery, type: ISSUE) {
        issueCount
      }
      reviews: search(query: $reviewQuery, type: ISSUE) {
        issueCount
      }
    }
    """
    variables = {
        "login": username,
        "from": from_date,
        "to": to_date,
        "prQuery": pr_query,
        "reviewQuery": review_query,
    }

    data = execute_graphql(token, query, variables)
    user_data = data.get("user", {})
    contribs = user_data.get("contributionsCollection", {})

    commits = contribs.get("totalCommitContributions", 0)
    issues = contribs.get("totalIssueContributions", 0)
    repos = contribs.get("totalRepositoryContributions", 0)

    prs = data.get("prs", {}).get("issueCount", 0)
    reviews = data.get("reviews", {}).get("issueCount", 0)

    return {
        "commits": commits,
        "pull_requests": prs,
        "reviews": reviews,
        "issues": issues,
        "new_repos": repos,
    }


def render_svg(stats: dict[str, int]) -> str:
    axes_keys = ["commits", "pull_requests", "reviews", "issues", "new_repos"]
    labels = ["Commits", "Pull requests", "Reviews", "Issues", "New repos"]
    values = [stats[k] for k in axes_keys]

    max_val = max(values) if values else 1
    if max_val == 0:
        max_val = 1
    log_max = math.log10(max_val + 1)
    min_frac = 0.08
    max_radius = 130.0

    cx, cy = 300.0, 238.0
    angles_deg = [-90.0, -18.0, 54.0, 126.0, 198.0]

    radii: list[float] = []
    for v in values:
        frac = math.log10(v + 1) / log_max
        r = (min_frac + (1.0 - min_frac) * frac) * max_radius
        radii.append(r)

    pts_final: list[tuple[float, float]] = []
    for r, deg in zip(radii, angles_deg):
        rad = math.radians(deg)
        px = cx + r * math.cos(rad)
        py = cy + r * math.sin(rad)
        pts_final.append((round(px, 1), round(py, 1)))

    pts_final_str = " ".join(f"{x},{y}" for x, y in pts_final)
    pts_center_str = " ".join(f"{cx},{cy}" for _ in range(5))

    ring_fractions = [0.25, 0.5, 0.75, 1.0]
    rings_svg: list[str] = []
    for f in ring_fractions:
        r = f * max_radius
        r_pts: list[str] = []
        for deg in angles_deg:
            rad = math.radians(deg)
            rx = cx + r * math.cos(rad)
            ry = cy + r * math.sin(rad)
            r_pts.append(f"{round(rx, 1)},{round(ry, 1)}")
        rings_svg.append(f'<polygon points="{" ".join(r_pts)}" fill="none" class="grid-ring"/>')

    axis_lines_svg: list[str] = []
    outer_pts: list[tuple[float, float]] = []
    for deg in angles_deg:
        rad = math.radians(deg)
        ox = round(cx + max_radius * math.cos(rad), 1)
        oy = round(cy + max_radius * math.sin(rad), 1)
        outer_pts.append((ox, oy))
        axis_lines_svg.append(f'<line x1="{cx}" y1="{cy}" x2="{ox}" y2="{oy}" class="axis-line"/>')

    label_configs = [
        {"lbl_x": 300, "lbl_y": 80, "num_x": 300, "num_y": 97, "anchor": "middle"},
        {"lbl_x": 448, "lbl_y": 188, "num_x": 448, "num_y": 205, "anchor": "start"},
        {"lbl_x": 392, "lbl_y": 362, "num_x": 392, "num_y": 379, "anchor": "start"},
        {"lbl_x": 208, "lbl_y": 362, "num_x": 208, "num_y": 379, "anchor": "end"},
        {"lbl_x": 152, "lbl_y": 188, "num_x": 152, "num_y": 205, "anchor": "end"},
    ]

    text_frames_svg: list[str] = []
    for i, (name, val, cfg) in enumerate(zip(labels, values, label_configs)):
        text_frames_svg.append(
            f'<text x="{cfg["lbl_x"]}" y="{cfg["lbl_y"]}" text-anchor="{cfg["anchor"]}" class="axis-lbl">{name}</text>'
        )
        for k in range(NUM_FRAMES):
            t = k / max(NUM_FRAMES - 1, 1)
            eased = 1.0 - math.pow(1.0 - t, 2.2)
            frame_val = round(eased * val)
            text_frames_svg.append(
                f'<text x="{cfg["num_x"]}" y="{cfg["num_y"]}" text-anchor="{cfg["anchor"]}" class="num f{k}">{frame_val:,}</text>'
            )

    dots_svg: list[str] = []
    for pt in pts_final:
        dots_svg.append(
            f'<circle cx="{cx}" cy="{cy}" r="4" class="radar-dot">'
            f'<animate attributeName="cx" begin="{ANIM_START}s" dur="{ANIM_DUR}s" from="{cx}" to="{pt[0]}" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1" keyTimes="0;1"/>'
            f'<animate attributeName="cy" begin="{ANIM_START}s" dur="{ANIM_DUR}s" from="{cy}" to="{pt[1]}" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1" keyTimes="0;1"/>'
            f'</circle>'
        )

    summary_map = {
        "commits": "Mostly shipping code.",
        "pull_requests": "Mostly opening PRs.",
        "reviews": "Mostly reviewing code.",
        "issues": "Mostly tracking issues.",
        "new_repos": "Mostly starting projects.",
    }
    max_key = max(axes_keys, key=lambda k: stats[k])
    summary_text = summary_map.get(max_key, "Mostly shipping code.")

    frame_rules: list[str] = []
    frame_dur = ANIM_DUR / max(NUM_FRAMES - 1, 1)
    frame_rules.append(f'.f0 {{ opacity: 1; animation: hideF0 0.001s {ANIM_START:.3f}s forwards; }}')
    for k in range(1, NUM_FRAMES - 1):
        t_start = ANIM_START + (k - 1) * frame_dur
        frame_rules.append(f'.f{k} {{ animation: flashFrame {frame_dur:.3f}s {t_start:.3f}s forwards; }}')
    t_final = ANIM_START + (NUM_FRAMES - 2) * frame_dur
    frame_rules.append(f'.f{NUM_FRAMES - 1} {{ animation: showFinal 0.001s {t_final:.3f}s forwards; }}')

    css_frames = "\n  ".join(frame_rules)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="880" height="410" viewBox="0 0 880 410" role="img" aria-label="How I work: where my time goes">
<style>
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; }}
    .grid-ring, .axis-line, .axis-lbl {{ opacity: 1 !important; }}
    .radar-shape {{ opacity: 1 !important; }}
    .radar-dot {{ opacity: 1 !important; }}
    .summary-line, .note-text {{ opacity: 1 !important; }}
    .num {{ opacity: 0 !important; animation: none !important; }}
    .f{NUM_FRAMES - 1} {{ opacity: 1 !important; }}
  }}
  .subhead {{ font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; font-weight: 600; letter-spacing: .14em; fill: #3fb950; }}
  .title {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 26px; font-weight: 700; letter-spacing: -.02em; fill: #f0f6fc; }}
  .grid-ring, .axis-line {{ stroke: #262c36; stroke-width: 1px; opacity: 0; animation: fadeIn 0.4s ease-out {ANIM_START}s forwards; }}
  .axis-lbl {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 14px; font-weight: 600; fill: #9198a1; opacity: 0; animation: fadeIn 0.4s ease-out {ANIM_START}s forwards; }}
  .radar-shape {{ fill: #3fb950; fill-opacity: .22; stroke: #3fb950; stroke-width: 2.5; stroke-linejoin: round; }}
  .radar-dot {{ fill: #3fb950; opacity: 0; animation: fadeIn 0.2s ease-out {ANIM_START}s forwards; }}
  .summary-line {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 22px; font-weight: 700; fill: #f0f6fc; opacity: 0; animation: fadeIn 0.6s ease-out 2.5s forwards; }}
  .note-text {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 15px; fill: #9198a1; opacity: 0; animation: fadeIn 0.6s ease-out 2.7s forwards; }}
  .num {{ opacity: 0; font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; font-weight: 700; fill: #f0f6fc; }}

  {css_frames}

  @keyframes fadeIn {{
    to {{ opacity: 1; }}
  }}
  @keyframes hideF0 {{
    to {{ opacity: 0; }}
  }}
  @keyframes flashFrame {{
    0% {{ opacity: 1; }}
    99% {{ opacity: 1; }}
    100% {{ opacity: 0; }}
  }}
  @keyframes showFinal {{
    to {{ opacity: 1; }}
  }}

  @media (prefers-color-scheme: light) {{
    .subhead {{ fill: #1a7f37; }}
    .title {{ fill: #1f2328; }}
    .grid-ring, .axis-line {{ stroke: #e4e8ec; }}
    .axis-lbl {{ fill: #59636e; }}
    .radar-shape {{ fill: #1a7f37; stroke: #1a7f37; fill-opacity: .2; }}
    .radar-dot {{ fill: #1a7f37; }}
    .num {{ fill: #1f2328; }}
    .summary-line {{ fill: #1f2328; }}
    .note-text {{ fill: #59636e; }}
  }}
</style>
<text class="subhead" x="32" y="38">HOW I WORK</text>
<text class="title" x="32" y="70">Where my time goes</text>
{"".join(rings_svg)}
{"".join(axis_lines_svg)}
<polygon points="{pts_center_str}" class="radar-shape">
  <animate attributeName="points" begin="{ANIM_START}s" dur="{ANIM_DUR}s" from="{pts_center_str}" to="{pts_final_str}" fill="freeze" calcMode="spline" keySplines="0.25 0.1 0.25 1" keyTimes="0;1"/>
</polygon>
{"".join(dots_svg)}
{"".join(text_frames_svg)}
<text x="560" y="170" class="summary-line">{summary_text}</text>
<text x="560" y="214" class="note-text">Scales are logarithmic, so a few</text>
<text x="560" y="235" class="note-text">reviews still show. Numbers are the</text>
<text x="560" y="256" class="note-text">last 12 months of public, private and org activity.</text>
</svg>
"""


def main() -> None:
    token = get_token()
    username = os.environ.get("GITHUB_ACTOR") or os.environ.get("GH_USER") or DEFAULT_USER
    stats = fetch_radar_data(token, username)
    svg_content = render_svg(stats)
    with OUTPUT_SVG.open("w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated {OUTPUT_SVG} ({len(svg_content)} bytes)")
    print(f"Stats: {stats}")


if __name__ == "__main__":
    main()
