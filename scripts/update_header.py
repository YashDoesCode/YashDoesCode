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
OUTPUT_SVG = ROOT_DIR / "header.svg"

GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_USER = "YashDoesCode"
MAX_BIO_LEN = 75


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
            "User-Agent": "YashDoesCode-Profile-Header",
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


def fetch_header_data(token: str, username: str) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    year = now.year
    from_date = f"{year}-01-01T00:00:00Z"
    to_date = f"{year}-12-31T23:59:59Z"

    pr_query = f"is:pr author:{username} created:>={year}-01-01"
    review_query = f"is:pr reviewed-by:{username} -author:{username} created:>={year}-01-01"

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!, $prQuery: String!, $reviewQuery: String!) {
      viewer {
        login
        name
        bio
      }
      user(login: $login) {
        name
        bio
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
          }
          totalCommitContributions
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
    user_info = data.get("user") or {}
    viewer_info = data.get("viewer") or {}

    display_name = user_info.get("name") or viewer_info.get("name") or username
    bio = user_info.get("bio") or viewer_info.get("bio") or ""

    contrib_coll = user_info.get("contributionsCollection") or {}
    total_contribs = contrib_coll.get("contributionCalendar", {}).get("totalContributions", 0)
    total_commits = contrib_coll.get("totalCommitContributions", 0)

    total_prs = data.get("prs", {}).get("issueCount", 0)
    total_reviews = data.get("reviews", {}).get("issueCount", 0)

    return {
        "year": year,
        "name": display_name,
        "bio": bio,
        "contributions": total_contribs,
        "commits": total_commits,
        "pull_requests": total_prs,
        "reviews": total_reviews,
        "updated_date": now.strftime("%b %d, %Y"),
    }


def render_svg(data: dict[str, Any]) -> str:
    name = html.escape(str(data["name"]))
    bio_raw = str(data.get("bio", "")).replace("\r\n", " ").replace("\n", " ").strip()
    if len(bio_raw) > MAX_BIO_LEN:
        bio_raw = bio_raw[:MAX_BIO_LEN].rstrip() + "…"
    bio = html.escape(bio_raw)

    year = data["year"]
    contributions = f"{data['contributions']:,}"
    commits = f"{data['commits']:,}"
    prs = f"{data['pull_requests']:,}"
    reviews = f"{data['reviews']:,}"
    updated = html.escape(str(data["updated_date"]))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="880" height="260" viewBox="0 0 880 260" role="img" aria-label="{name}: the year in data">
<style>
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; }}
  }}
  .subhead {{ font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; font-weight: 600; letter-spacing: .14em; fill: #3fb950; }}
  .title {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 46px; font-weight: 700; letter-spacing: -.04em; fill: #f0f6fc; }}
  .bio {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 16px; fill: #d1d7e0; }}
  .divider {{ stroke: #262c36; stroke-width: 1px; }}
  .stat-contrib {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 32px; font-weight: 700; letter-spacing: -.03em; fill: #3fb950; }}
  .stat-val {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 32px; font-weight: 700; letter-spacing: -.03em; fill: #f0f6fc; }}
  .stat-lbl {{ font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; fill: #9198a1; }}
  .updated {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 10px; font-weight: 500; fill: #7d8590; }}

  @media (prefers-color-scheme: light) {{
    .subhead {{ fill: #1a7f37; }}
    .title {{ fill: #1f2328; }}
    .bio {{ fill: #353c44; }}
    .divider {{ stroke: #e4e8ec; }}
    .stat-contrib {{ fill: #1a7f37; }}
    .stat-val {{ fill: #1f2328; }}
    .stat-lbl {{ fill: #59636e; }}
    .updated {{ fill: #656d76; }}
  }}
</style>
<text class="subhead" x="32" y="38">THE YEAR IN DATA · {year}</text>
<text class="title" x="30" y="90">{name}</text>
<text class="bio" x="32" y="124">{bio}</text>
<line class="divider" x1="32" y1="150" x2="848" y2="150"/>
<text class="stat-contrib" x="32" y="196">{contributions}</text>
<text class="stat-lbl" x="32" y="218">contributions</text>
<text class="stat-val" x="236" y="196">{commits}</text>
<text class="stat-lbl" x="236" y="218">commits</text>
<text class="stat-val" x="440" y="196">{prs}</text>
<text class="stat-lbl" x="440" y="218">pull requests</text>
<text class="stat-val" x="644" y="196">{reviews}</text>
<text class="stat-lbl" x="644" y="218">reviews</text>
<text class="updated" x="848" y="244" text-anchor="end">updated {updated}</text>
</svg>
"""


def main() -> None:
    token = get_token()
    username = os.environ.get("GITHUB_ACTOR") or os.environ.get("GH_USER") or DEFAULT_USER
    data = fetch_header_data(token, username)
    svg_content = render_svg(data)
    with OUTPUT_SVG.open("w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated {OUTPUT_SVG} ({len(svg_content)} bytes)")


if __name__ == "__main__":
    main()

