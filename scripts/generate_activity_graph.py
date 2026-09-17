#!/usr/bin/env python3
"""
GitHub Activity Graph Generator (Monochrome & Animated Multi-Year Showcase)
Author: Yash Srivastava (YashDoesCode)

Features:
- Pure monochrome luxury dark theme matching Vercel / Linear / Apple style.
- Smooth CSS animations (line drawing + area gradient fade-in + pulsating end dot).
- Dynamically retrieves 5-10 years of historical and real-time GitHub activity.
- Automatically extends the timeline when a new year begins (e.g., 2027, 2028) with pure year numbers.
- Zero hardcoded "new" or "Now" labels.
- Dual ingestion: GitHub GraphQL API (with GITHUB_TOKEN) and zero-token public fallback.
"""

import os
import sys
import re
import json
import math
import ssl
import argparse
import urllib.request
from datetime import datetime, date, timezone
from collections import defaultdict

def create_ssl_context():
    """Create SSL context with system certs or unverified fallback."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        ctx = ssl._create_unverified_context()
        return ctx

def fetch_graphql_contributions(username, token, start_year, end_year):
    """Fetch contribution data using GitHub GraphQL API."""
    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "GitHub-Activity-Graph-Generator"
    }
    
    yearly_data = {}
    daily_data = {}
    
    query = """
    query($username: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $username) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks {
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
    
    ssl_ctx = create_ssl_context()
    for year in range(start_year, end_year + 1):
        from_dt = f"{year}-01-01T00:00:00Z"
        to_dt = f"{year}-12-31T23:59:59Z"
        payload = {
            "query": query,
            "variables": {
                "username": username,
                "from": from_dt,
                "to": to_dt
            }
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                user_data = result.get("data", {}).get("user", {})
                if not user_data:
                    continue
                col = user_data.get("contributionsCollection", {})
                cal = col.get("contributionCalendar", {})
                total = cal.get("totalContributions", 0)
                yearly_data[year] = total
                
                for week in cal.get("weeks", []):
                    for day in week.get("contributionDays", []):
                        d_str = day.get("date")
                        count = day.get("contributionCount", 0)
                        daily_data[d_str] = count
        except Exception as e:
            print(f"GraphQL error for {year}: {e}", file=sys.stderr)
            return None, None
            
    return yearly_data, daily_data

def fetch_public_contributions(username, start_year, end_year):
    """Fallback: Fetch contribution data from GitHub public profile contributions endpoint."""
    yearly_data = {}
    daily_data = {}
    
    ssl_ctx = ssl._create_unverified_context()
    for year in range(start_year, end_year + 1):
        url = f"https://github.com/users/{username}/contributions?from={year}-01-01&to={year}-12-31"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                html = resp.read().decode("utf-8")
                
                m = re.search(r"id=\"js-contribution-activity-description\"[^>]*>\s*([\d,]+)\s*contributions", html)
                if m:
                    yearly_data[year] = int(m.group(1).replace(",", ""))
                else:
                    yearly_data[year] = 0
                
                days = re.findall(r"data-date=\"(\d{4}-\d{2}-\d{2})\".*?<tool-tip[^>]*>(\d+)\s+contribution", html, re.DOTALL)
                for d_str, count in days:
                    daily_data[d_str] = int(count)
        except Exception as e:
            print(f"Public scraper warning for {year}: {e}", file=sys.stderr)
            if year not in yearly_data:
                yearly_data[year] = 0
                
    return yearly_data, daily_data

def format_number(val):
    """Format large numbers (e.g., 1600, 1400 -> 1.4k if >= 10000)."""
    if val >= 10000:
        return f"{val / 1000:.1f}k".replace(".0k", "k")
    return str(val)

def catmull_rom_to_bezier(points):
    """Convert a sequence of (x, y) points into smooth cubic Bezier path commands."""
    if not points:
        return ""
    if len(points) == 1:
        return f"M {points[0][0]:.2f} {points[0][1]:.2f}"
    if len(points) == 2:
        return f"M {points[0][0]:.2f} {points[0][1]:.2f} L {points[1][0]:.2f} {points[1][1]:.2f}"
    
    d = f"M {points[0][0]:.2f} {points[0][1]:.2f}"
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else p2
        
        cp1x = p1[0] + (p2[0] - p0[0]) / 6.0
        cp1y = p1[1] + (p2[1] - p0[1]) / 6.0
        cp2x = p2[0] - (p3[0] - p1[0]) / 6.0
        cp2y = p2[1] - (p3[1] - p1[1]) / 6.0
        
        d += f" C {cp1x:.2f} {cp1y:.2f}, {cp2x:.2f} {cp2y:.2f}, {p2[0]:.2f} {p2[1]:.2f}"
    return d

def generate_monochrome_svg(yearly_data, daily_data, start_year, end_year):
    """
    Generate the animated monochrome activity graph matching the exact visual style,
    shade, and quality of the reference image.
    """
    width = 1030
    height = 400
    left = 68
    right = 980
    top = 95
    bottom = 345
    chart_w = right - left
    chart_h = bottom - top
    
    total_commits = sum(yearly_data.get(y, 0) for y in range(start_year, end_year + 1))
    
    start_date = date(start_year, 1, 1)
    now = datetime.now()
    end_date = date(end_year, now.month if end_year == now.year else 12, now.day if end_year == now.year else 31)
    total_days = max(1, (end_date - start_date).days)
    
    # Calculate cumulative timeline points
    sorted_days = sorted(daily_data.keys())
    cum_sum = 0
    day_cum = {}
    for d in sorted_days:
        cum_sum += daily_data[d]
        day_cum[d] = cum_sum
        
    from datetime import timedelta
    sample_step_days = max(10, total_days // 100)
    sample_points = []
    
    cur_days = 0
    while cur_days <= total_days:
        cur_dt = start_date + timedelta(days=cur_days)
        d_str = cur_dt.strftime("%Y-%m-%d")
        
        candidates = [c for d, c in day_cum.items() if d <= d_str]
        val = candidates[-1] if candidates else 0
        x = left + (cur_days / total_days) * chart_w
        sample_points.append((x, val, cur_dt))
        cur_days += sample_step_days
        
    final_x = right
    sample_points.append((final_x, total_commits, end_date))
    
    # Y-scale: clean multiples like in reference (1600, 1200, 800, 400, 0)
    max_val = max(total_commits, 100)
    if max_val <= 1600:
        y_scale_max = 1600
        num_ticks = 4
    else:
        magnitude = 10 ** math.floor(math.log10(max_val))
        step = math.ceil(max_val / 4 / (magnitude / 2)) * (magnitude / 2)
        y_scale_max = step * 4
        num_ticks = 4
        
    # Convert samples to screen coordinates
    screen_pts = []
    for x, val, _ in sample_points:
        y = bottom - (val / y_scale_max) * chart_h
        screen_pts.append((x, y))
        
    # Filter close points
    filtered_pts = []
    for pt in screen_pts:
        if not filtered_pts or (pt[0] - filtered_pts[-1][0] >= 4):
            filtered_pts.append(pt)
    if screen_pts and filtered_pts[-1] != screen_pts[-1]:
        filtered_pts.append(screen_pts[-1])
        
    line_path = catmull_rom_to_bezier(filtered_pts)
    first_pt = filtered_pts[0]
    last_pt = filtered_pts[-1]
    area_path = f"{line_path} L {last_pt[0]:.2f} {bottom} L {first_pt[0]:.2f} {bottom} Z"
    
    # Y-axis gridlines (horizontal dotted lines with values on the left)
    y_grid_lines = []
    for i in range(num_ticks + 1):
        tick_val = int(i * (y_scale_max / num_ticks))
        y_pos = bottom - (i / num_ticks) * chart_h
        dash = ' stroke-dasharray="3 3"' if i > 0 else ''
        stroke_col = "#18181c" if i > 0 else "#1f1f25"
        y_grid_lines.append(
            f'<line x1="{left}" y1="{y_pos:.1f}" x2="{right}" y2="{y_pos:.1f}" stroke="{stroke_col}" stroke-width="1"{dash} />\n'
            f'  <text x="{left - 12}" y="{y_pos + 3.5:.1f}" text-anchor="end" font-size="11" fill="#71717a" '
            f'font-family="\'Inter\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif">{tick_val}</text>'
        )
    y_grid_str = "\n  ".join(y_grid_lines)
    
    # X-axis year markers (clean, pure year numbers automatically extending with new years)
    years = list(range(start_year, end_year + 1))
    num_years = len(years)
    x_labels = []
    
    for idx, yr in enumerate(years):
        if idx == 0:
            x_pos = left
            anchor = "start"
        elif idx == num_years - 1:
            x_pos = right
            anchor = "end"
        else:
            x_pos = left + (idx / (num_years - 1)) * chart_w
            anchor = "middle"
            
        x_labels.append(
            f'<text x="{x_pos:.1f}" y="375" text-anchor="{anchor}" font-size="11" fill="#71717a" '
            f'font-family="\'Inter\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif">{yr}</text>'
        )
    x_labels_str = "\n  ".join(x_labels)
    
    last_x, last_y = last_pt
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Total Activity">
  <defs>
    <!-- Monochrome Gradient Area Fill -->
    <linearGradient id="monochromeFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.22" />
      <stop offset="60%" stop-color="#ffffff" stop-opacity="0.04" />
      <stop offset="100%" stop-color="#08080a" stop-opacity="0.0" />
    </linearGradient>

    <!-- Subtle White Ambient Glow -->
    <filter id="subtleGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#ffffff" flood-opacity="0.2" />
    </filter>

    <!-- Smooth CSS Animations -->
    <style>
      @keyframes drawLine {{
        0% {{
          stroke-dashoffset: 4000;
        }}
        100% {{
          stroke-dashoffset: 0;
        }}
      }}

      @keyframes fadeInArea {{
        0% {{
          opacity: 0;
        }}
        100% {{
          opacity: 1;
        }}
      }}

      @keyframes pulseDot {{
        0%, 100% {{
          r: 4px;
          opacity: 1;
        }}
        50% {{
          r: 7px;
          opacity: 0.45;
        }}
      }}

      .chart-line {{
        stroke-dasharray: 4000;
        stroke-dashoffset: 4000;
        animation: drawLine 2.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      }}

      .chart-area {{
        opacity: 0;
        animation: fadeInArea 2.6s ease-out 0.3s forwards;
      }}

      .pulse-core {{
        animation: pulseDot 2.5s ease-in-out infinite;
      }}
    </style>
  </defs>

  <!-- Monochrome Card Background -->
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="16" fill="#08080a" stroke="#18181c" stroke-width="1" />

  <!-- Y-Axis Gridlines & Labels -->
  {y_grid_str}

  <!-- X-Axis Year Labels -->
  {x_labels_str}

  <!-- Animated Monochrome Area Fill -->
  <path class="chart-area" d="{area_path}" fill="url(#monochromeFill)" />

  <!-- Animated White Line Curve -->
  <path class="chart-line" d="{line_path}" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" filter="url(#subtleGlow)" />

  <!-- Animated End Point -->
  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="8" fill="rgba(255, 255, 255, 0.15)" />
  <circle class="pulse-core" cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="#ffffff" stroke="#08080a" stroke-width="1.5" />

  <!-- Header: Total Activity & Subtitle -->
  <text x="{left}" y="42" font-size="16" font-weight="600" fill="#f4f4f5" font-family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">Total Activity</text>
  <text x="{left}" y="62" font-size="13" fill="#71717a" font-family="'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif">Commit activity analysis ({total_commits:,} commits across {start_year} – {end_year})</text>

  <!-- Top Right Monochrome Controls: Filter & Manage -->
  <g transform="translate({right - 145}, 25)">
    <rect width="65" height="28" rx="6" fill="#131316" stroke="#222228" stroke-width="1" />
    <text x="32.5" y="18" text-anchor="middle" font-size="12" fill="#a1a1aa" font-family="'Inter', sans-serif">Filter</text>

    <rect x="75" width="70" height="28" rx="6" fill="#131316" stroke="#222228" stroke-width="1" />
    <text x="110" y="18" text-anchor="middle" font-size="12" fill="#a1a1aa" font-family="'Inter', sans-serif">Manage</text>
  </g>
</svg>
"""
    return svg

def generate_monochrome_yearly_svg(yearly_data, start_year, end_year):
    """Generate the animated monochrome Annual Commit Showcase graph."""
    width = 1030
    height = 400
    left = 68
    right = 980
    top = 95
    bottom = 330
    chart_w = right - left
    chart_h = bottom - top
    
    years = list(range(start_year, end_year + 1))
    max_val = max([yearly_data.get(y, 0) for y in years] + [10])
    y_scale_max = math.ceil(max_val / 200) * 200 if max_val > 200 else 200
    if y_scale_max < max_val:
        y_scale_max = math.ceil(max_val / 100) * 100
        
    num_years = len(years)
    col_width = min(75, (chart_w / num_years) * 0.52)
    
    # Y-axis grid
    y_grid = []
    num_ticks = 4
    for i in range(num_ticks + 1):
        tick_val = int(i * (y_scale_max / num_ticks))
        y_pos = bottom - (i / num_ticks) * chart_h
        dash = ' stroke-dasharray="3 3"' if i > 0 else ''
        stroke_col = "#18181c" if i > 0 else "#1f1f25"
        y_grid.append(
            f'<line x1="{left}" y1="{y_pos:.1f}" x2="{right}" y2="{y_pos:.1f}" stroke="{stroke_col}" stroke-width="1"{dash} />\n'
            f'  <text x="{left - 12}" y="{y_pos + 3.5:.1f}" text-anchor="end" font-size="11" fill="#71717a" '
            f'font-family="\'Inter\', sans-serif">{tick_val}</text>'
        )
    y_grid_str = "\n  ".join(y_grid)
    
    # Monochrome Bars
    bars = []
    for idx, yr in enumerate(years):
        c = yearly_data.get(yr, 0)
        h = max(4, (c / y_scale_max) * chart_h) if c > 0 else 3
        cx = left + (idx + 0.5) * (chart_w / num_years)
        x = cx - col_width / 2
        y = bottom - h
        
        bar_elem = f"""
    <!-- Year {yr} -->
    <rect x="{x:.1f}" y="{y:.1f}" width="{col_width:.1f}" height="{h:.1f}" rx="6" fill="url(#barMono)" stroke="#3f3f46" stroke-width="1" />
    <text x="{cx:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-size="12" font-weight="600" fill="#f4f4f5" font-family="'Inter', sans-serif">{c}</text>
    <text x="{cx:.1f}" y="{bottom + 22:.1f}" text-anchor="middle" font-size="12" font-weight="500" fill="#a1a1aa" font-family="'Inter', sans-serif">{yr}</text>
    <text x="{cx:.1f}" y="{bottom + 38:.1f}" text-anchor="middle" font-size="10" fill="#52525b" font-family="'Inter', sans-serif">commits</text>
        """
        bars.append(bar_elem)
        
    bars_str = "\n".join(bars)
    total_commits = sum(yearly_data.get(y, 0) for y in years)
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Yearly Commit Showcase">
  <defs>
    <linearGradient id="barMono" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.85" />
      <stop offset="100%" stop-color="#27272a" stop-opacity="0.4" />
    </linearGradient>
  </defs>

  <!-- Monochrome Card Background -->
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="16" fill="#08080a" stroke="#18181c" stroke-width="1" />

  <!-- Y-Axis Grid -->
  {y_grid_str}

  <!-- Header -->
  <text x="{left}" y="42" font-size="16" font-weight="600" fill="#f4f4f5" font-family="'Inter', sans-serif">Annual Commit Showcase</text>
  <text x="{left}" y="62" font-size="13" fill="#71717a" font-family="'Inter', sans-serif">Yearly commit distribution ({total_commits:,} total contributions across {start_year} – {end_year})</text>

  <!-- Top Right Controls -->
  <g transform="translate({right - 145}, 25)">
    <rect width="65" height="28" rx="6" fill="#131316" stroke="#222228" stroke-width="1" />
    <text x="32.5" y="18" text-anchor="middle" font-size="12" fill="#a1a1aa" font-family="'Inter', sans-serif">Filter</text>

    <rect x="75" width="70" height="28" rx="6" fill="#131316" stroke="#222228" stroke-width="1" />
    <text x="110" y="18" text-anchor="middle" font-size="12" fill="#a1a1aa" font-family="'Inter', sans-serif">Manage</text>
  </g>

  <!-- Bars Content -->
  {bars_str}
</svg>
"""
    return svg

def main():
    parser = argparse.ArgumentParser(description="Generate real-time monochrome animated GitHub activity graph SVGs")
    parser.add_argument("--username", default="YashDoesCode", help="GitHub username")
    parser.add_argument("--start-year", type=int, default=2021, help="Start year of presence")
    parser.add_argument("--end-year", type=int, default=datetime.now().year, help="End year")
    parser.add_argument("--output-dir", default="./assets", help="Directory to save generated SVGs")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"), help="GitHub Personal Access Token")
    
    args = parser.parse_args()
    
    current_year = datetime.now().year
    end_year = max(args.end_year, current_year)
    start_year = args.start_year
    
    print(f"[+] Generating monochrome animated activity charts for @{args.username}")
    print(f"[+] Horizon: {start_year} to {end_year} (Auto-rolls over to future years)")
    
    yearly_data = None
    daily_data = None
    
    if args.token:
        print("[+] Attempting GitHub GraphQL API with token...")
        yearly_data, daily_data = fetch_graphql_contributions(args.username, args.token, start_year, end_year)
        
    if not yearly_data or sum(yearly_data.values()) == 0:
        print("[+] Fetching data via GitHub Public Contributions engine...")
        yearly_data, daily_data = fetch_public_contributions(args.username, start_year, end_year)
        
    print(f"[+] Collected yearly metrics: {yearly_data}")
    print(f"[+] Total commits: {sum(yearly_data.values())}")
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 1. Monochrome Animated Activity Graph
    mono_svg = generate_monochrome_svg(yearly_data, daily_data, start_year, end_year)
    cum_path = os.path.join(args.output_dir, "activity-graph.svg")
    with open(cum_path, "w", encoding="utf-8") as f:
        f.write(mono_svg)
    print(f"[✔] Wrote: {cum_path}")
    
    # 2. Monochrome Annual Breakdown Graph
    yearly_svg = generate_monochrome_yearly_svg(yearly_data, start_year, end_year)
    yearly_path = os.path.join(args.output_dir, "activity-graph-yearly.svg")
    with open(yearly_path, "w", encoding="utf-8") as f:
        f.write(yearly_svg)
    print(f"[✔] Wrote: {yearly_path}")
    
    # Write metadata JSON
    meta_path = os.path.join(args.output_dir, "activity-metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "username": args.username,
            "start_year": start_year,
            "end_year": end_year,
            "theme": "monochrome",
            "animated": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "yearly_contributions": yearly_data,
            "total_contributions": sum(yearly_data.values())
        }, f, indent=2)
    print(f"[✔] Wrote: {meta_path}")
    print("[+] All monochrome graphs successfully generated!")

if __name__ == "__main__":
    main()
