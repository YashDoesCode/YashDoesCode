#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_SVG = ROOT_DIR / "contrib-heatmap.svg"
OUTPUT_JSON = ROOT_DIR / "data" / "contributions.json"

GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_USER = "YashDoesCode"

LEVEL_MAP = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

COLOR_MAP = {
    0: ("#161b22", "c e"),
    1: ("#0e4429", "c g"),
    2: ("#006d32", "c g"),
    3: ("#26a641", "c g"),
    4: ("#39d353", "c g"),
}

MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


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
            "User-Agent": "YashDoesCode-Profile-Heatmap",
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


def fetch_contributions_data(token: str, username: str) -> dict[str, Any]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              firstDay
              contributionDays {
                date
                contributionCount
                contributionLevel
                weekday
              }
            }
          }
        }
      }
    }
    """
    data = execute_graphql(token, query, {"login": username})
    user_info = data.get("user") or {}
    calendar = user_info.get("contributionsCollection", {}).get("contributionCalendar", {})
    weeks = calendar.get("weeks", [])
    total_contributions = calendar.get("totalContributions", 0)

    days: list[dict[str, Any]] = []
    for w in weeks:
        for d in w.get("contributionDays", []):
            days.append({
                "date": d["date"],
                "count": d["contributionCount"],
                "level": LEVEL_MAP.get(d.get("contributionLevel"), 0),
            })

    longest_streak = 0
    cur_streak = 0
    for d in days:
        if d["count"] > 0:
            cur_streak += 1
            if cur_streak > longest_streak:
                longest_streak = cur_streak
        else:
            cur_streak = 0

    current_streak = 0
    started = False
    for d in reversed(days):
        if d["count"] > 0:
            started = True
            current_streak += 1
        elif started:
            break

    return {
        "username": username,
        "total": {
            "lastYear": total_contributions,
        },
        "total_contributions": total_contributions,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "contributions": days,
        "days": days,
        "weeks": weeks,
    }


def render_svg(data: dict[str, Any]) -> str:
    weeks = data.get("weeks", [])
    total_contributions = data["total_contributions"]

    month_labels: list[str] = []
    prev_month: int | None = None
    for w_idx, week in enumerate(weeks):
        first_day_date = week.get("firstDay")
        if not first_day_date and week.get("contributionDays"):
            first_day_date = week["contributionDays"][0]["date"]
        if first_day_date:
            m = int(first_day_date.split("-")[1])
            if m != prev_month:
                x = 34 + w_idx * 16
                month_labels.append(f'<text class="lbl" x="{x}" y="16">{MONTH_NAMES[m]}</text>')
                prev_month = m

    day_labels = '<text class="lbl" x="2" y="51">Mon</text><text class="lbl" x="2" y="83">Wed</text><text class="lbl" x="2" y="115">Fri</text>'
    header_line = "".join(month_labels) + day_labels

    rects: list[str] = []
    for w_idx, week in enumerate(weeks):
        for day in week.get("contributionDays", []):
            weekday = day.get("weekday", 0)
            x = 34 + w_idx * 16
            y = 24 + weekday * 16
            level = LEVEL_MAP.get(day.get("contributionLevel"), 0)
            color, cls = COLOR_MAP.get(level, ("#161b22", "c e"))
            delay = round(2.0 + w_idx * 0.0651 + weekday * 0.0358, 3)
            delay_str = f"{delay:.1f}" if round(delay, 1) == delay else f"{delay:.3f}".rstrip("0")
            rects.append(
                f'<rect class="{cls}" x="{x}" y="{y}" width="13" height="13" rx="2.5" fill="{color}" style="animation-delay:{delay_str}s"/>'
            )

    rects_str = "".join(rects)
    total_formatted = f"{total_contributions:,}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="888" height="158" viewBox="0 0 888 158" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">
<style>
  text.lbl {{ fill:#7d8590; font-size:13px; font-weight:600; }}
  text.total {{ fill:#e6edf3; font-size:15px; font-weight:700; }}
  .c {{ transform-box:fill-box; transform-origin:center; opacity:0; animation:pop 0.55s ease-out both; }}
  .g {{ animation:pop 0.55s ease-out both, flash 0.7000000000000001s ease-out both; }}
  @keyframes pop {{ 0%{{opacity:0;transform:scale(.2)}} 60%{{opacity:1;transform:scale(1.1)}} 100%{{opacity:1;transform:scale(1)}} }}
  @keyframes flash {{ 0%{{filter:brightness(2.4)}} 45%{{filter:brightness(2.4)}} 100%{{filter:brightness(1)}} }}
  @media (prefers-reduced-motion: reduce) {{ .c {{ opacity:1 !important; animation:none !important; }} }}
</style>
<rect width="888" height="158" fill="none"/>
{header_line}
{rects_str}
<text class="total" x="34" y="152">{total_formatted} contributions in the last year</text>
</svg>"""


def main() -> None:
    token = get_token()
    username = os.environ.get("GH_USER") or os.environ.get("GITHUB_ACTOR") or DEFAULT_USER
    if not username or "[bot]" in username:
        username = DEFAULT_USER

    data = fetch_contributions_data(token, username)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json_data = {
        "username": data["username"],
        "total": data["total"],
        "total_contributions": data["total_contributions"],
        "current_streak": data["current_streak"],
        "longest_streak": data["longest_streak"],
        "contributions": data["contributions"],
        "days": data["days"],
    }
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)
    print(f"Updated {OUTPUT_JSON} ({len(json_data['contributions'])} days recorded)")

    svg_content = render_svg(data)
    with OUTPUT_SVG.open("w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated {OUTPUT_SVG} ({len(svg_content)} bytes)")
    print(f"Last year total: {data['total_contributions']}")
    print(f"Current streak: {data['current_streak']}, Longest streak: {data['longest_streak']}")


if __name__ == "__main__":
    main()
