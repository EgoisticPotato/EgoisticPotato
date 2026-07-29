import os
from pathlib import Path
import json
import urllib.request
# Load .env if present
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

# Local imports
import config


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GITHUB_API = "https://api.github.com/graphql"
TOKEN_ENV = "GITHUB_TOKEN"
OUTPUT_DIR = config.OUTPUT_DIR

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def _graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GraphQL query against the GitHub API.

    Returns the parsed JSON response (the ``data`` key). Raises RuntimeError on
    network or authentication errors.
    """
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(
            f"GitHub token not found. Set the {TOKEN_ENV} environment variable."
        )
    payload = {"query": query, "variables": variables or {}}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GITHUB_API,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        resp_data = json.load(resp)
    if "errors" in resp_data:
        raise RuntimeError(f"GraphQL errors: {resp_data['errors']}")
    return resp_data["data"]

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------
def fetch_contributions(username: str) -> dict:
    """Fetch contribution calendar and total contributions for the last year.
    Returns a dict with keys:
        - totalContributions (int)
        - weeks (list of weeks, each week is a list of 7 day dicts)
        - contributionsByDay (list of (date, count) tuples in chronological order)
    """
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
                color
              }
            }
          }
        }
      }
    }
    """
    data = _graphql(query, {"login": username})
    calendar = (
        data["user"]["contributionsCollection"]["contributionCalendar"]
    )
    weeks = calendar["weeks"]
    contributions_by_day = []
    for week in weeks:
        for day in week["contributionDays"]:
            contributions_by_day.append((day["date"], day["contributionCount"]))
    return {
        "totalContributions": calendar["totalContributions"],
        "weeks": weeks,
        "contributionsByDay": contributions_by_day,
    }

def fetch_languages(username: str, top_n: int = 5) -> list[tuple[str, int]]:
    """Fetch top languages across all public repositories for the user.
    Returns a list of (language_name, total_bytes) sorted descending.
    """
    query = """
    query($login: String!, $after: String) {
      user(login: $login) {
        repositories(first: 100, after: $after, privacy: PUBLIC, isFork: false) {
          pageInfo { hasNextPage endCursor }
          nodes {
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name } }
            }
          }
        }
      }
    }
    """
    after = None
    lang_totals: dict[str, int] = {}
    while True:
        vars = {"login": username, "after": after}
        data = _graphql(query, vars)
        repos = data["user"]["repositories"]
        for repo in repos["nodes"]:
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                size = edge["size"]
                lang_totals[name] = lang_totals.get(name, 0) + size
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]
    sorted_langs = sorted(lang_totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return sorted_langs

# ---------------------------------------------------------------------------
# SVG generation helpers (very lightweight, using config colours)
# ---------------------------------------------------------------------------
def _svg_header(width: int, height: int) -> str:
    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}px\" height=\"{height}px\" viewBox=\"0 0 {width} {height}\">\n"""

def _svg_footer() -> str:
    return "</svg>\n"

# ---------------------------------------------------------------------------
# Chart generators
# ---------------------------------------------------------------------------
def generate_stats_svg(total: int, recent_counts: list[int]) -> Path:
    """Create a simple stats card with total contributions and a sparkline.
    ``recent_counts`` should be a list of daily contributions for the last 30 days.
    """
    width, height = 300, 120
    spark_width = width - 40
    spark_height = 30
    max_val = max(recent_counts) if recent_counts and max(recent_counts) > 0 else 1
    points = []
    for i, v in enumerate(recent_counts):
        x = 20 + i * spark_width / max(1, len(recent_counts) - 1)
        y = 60 + (spark_height - (v / max_val) * spark_height)
        points.append(f"{x:.2f},{y:.2f}")
    sparkline = " ".join(points)
    svg = (
        _svg_header(width, height)
        + f"  <style>text {{ font-family: 'Inter', sans-serif; fill: {config.PORTRAIT_FILL_COLOR}; }}</style>\n"
        + f"  <text x=\"{width // 2}\" y=\"30\" font-size=\"20\" text-anchor=\"middle\">{total} contributions</text>\n"
        + f"  <polyline points=\"{sparkline}\" fill=\"none\" stroke=\"{config.PORTRAIT_CURSOR_COLOR}\" stroke-width=\"2\"/>\n"
        + _svg_footer()
    )
    out_path = OUTPUT_DIR / "stats.svg"
    out_path.write_text(svg, encoding="utf-8")
    return out_path

def generate_streak_svg(current: int, longest: int) -> Path:
    width, height = 200, 80
    svg = (
        _svg_header(width, height)
        + f"  <style>text {{ font-family: 'Inter', sans-serif; fill: {config.PORTRAIT_FILL_COLOR}; }}</style>\n"
        + f"  <text x=\"{width // 2}\" y=\"30\" font-size=\"18\" text-anchor=\"middle\">Current: {current}d</text>\n"
        + f"  <text x=\"{width // 2}\" y=\"60\" font-size=\"18\" text-anchor=\"middle\">Longest: {longest}d</text>\n"
        + _svg_footer()
    )
    out_path = OUTPUT_DIR / "streak.svg"
    out_path.write_text(svg, encoding="utf-8")
    return out_path

def generate_langs_svg(langs: list[tuple[str, int]]) -> Path:
    max_width = 300
    bar_height = 20
    padding = 5
    height = (bar_height + padding) * len(langs) + 20
    total = sum(size for _, size in langs) or 1
    svg_lines = [_svg_header(max_width, height)]
    svg_lines.append(
        f"  <style>text {{ font-family: 'Inter', sans-serif; fill: {config.PORTRAIT_FILL_COLOR}; font-size: 12px; }}</style>"
    )
    for idx, (name, size) in enumerate(langs):
        ratio = size / total
        bar_len = int(ratio * max_width)
        y = 20 + idx * (bar_height + padding)
        svg_lines.append(
            f"  <rect x=\"0\" y=\"{y}\" width=\"{bar_len}\" height=\"{bar_height}\" fill=\"{config.PORTRAIT_CURSOR_COLOR}\"/>"
        )
        svg_lines.append(
            f"  <text x=\"{bar_len + 5}\" y=\"{y + bar_height / 2 + 4}\">{name} ({size // 1024} KB)</text>"
        )
    svg_lines.append(_svg_footer())
    out_path = OUTPUT_DIR / "langs.svg"
    out_path.write_text("\n".join(svg_lines), encoding="utf-8")
    return out_path

def generate_year_svg(weeks: list) -> Path:
    cell_size = 12
    cell_gap = 2
    rows = 7
    cols = len(weeks)
    width = cols * (cell_size + cell_gap) + cell_gap
    height = rows * (cell_size + cell_gap) + cell_gap
    svg = [_svg_header(width, height)]
    svg.append(f"  <style>rect {{ stroke: none; }} </style>")
    for col_idx, week in enumerate(weeks):
        for day in week["contributionDays"]:
            row = day["weekday"]
            x = col_idx * (cell_size + cell_gap) + cell_gap
            y = row * (cell_size + cell_gap) + cell_gap
            fill = day["color"] if day["color"] else "#ebedf0"
            svg.append(
                f"  <rect x=\"{x}\" y=\"{y}\" width=\"{cell_size}\" height=\"{cell_size}\" fill=\"{fill}\"/>"
            )
    svg.append(_svg_footer())
    out_path = OUTPUT_DIR / "year.svg"
    out_path.write_text("\n".join(svg), encoding="utf-8")
    return out_path

# ---------------------------------------------------------------------------
# Streak calculation helpers
# ---------------------------------------------------------------------------
def _calculate_streaks(contributions_by_day: list[tuple[str, int]]) -> tuple[int, int]:
    longest = current = 0
    running = 0
    for _, count in contributions_by_day:
        if count > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0
    for _, count in reversed(contributions_by_day):
        if count > 0:
            current += 1
        else:
            break
    return current, longest

# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def main(username: str | None = None):
    if username is None:
        try:
            import subprocess
            username = subprocess.check_output(["git", "config", "user.name"], text=True).strip()
        except Exception:
            raise RuntimeError("GitHub username not provided and could not be inferred. Pass it to main().")
    print(f"Fetching data for GitHub user: {username}")
    contrib_data = fetch_contributions(username)
    total = contrib_data["totalContributions"]
    recent = [cnt for _, cnt in contrib_data["contributionsByDay"][-30:]]
    weeks = contrib_data["weeks"]
    current_streak, longest_streak = _calculate_streaks(contrib_data["contributionsByDay"])
    langs = fetch_languages(username)
    print("Generating SVGs …")
    generate_stats_svg(total, recent)
    generate_streak_svg(current_streak, longest_streak)
    generate_langs_svg(langs)
    generate_year_svg(weeks)
    print(f"All SVGs written to {OUTPUT_DIR}")

if __name__ == "__main__":
    main(os.getenv("GITHUB_USER"))
