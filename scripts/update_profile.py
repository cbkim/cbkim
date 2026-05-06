"""
Update Profile README

Fetches the user's GitHub data (pinned repos, recent activity, language mix)
and renders a fresh README.md from a Jinja2 template.

Designed to run inside GitHub Actions with a Personal Access Token (GH_PAT)
that has at minimum: read:user, public_repo. No credit card needed to create one.

Outputs:
  - README.md  (the profile readme, committed back to the repo)
  - state/last_run.json  (audit trail of what the last run saw)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from jinja2 import Environment, FileSystemLoader

# --- Config from environment ---------------------------------------------------

GH_TOKEN = os.environ.get("GH_TOKEN", "").strip()
GH_USERNAME = os.environ.get("GH_USERNAME", "").strip()
ACTIVITY_DAYS = int(os.environ.get("ACTIVITY_DAYS", "7"))

if not GH_TOKEN:
    sys.exit("ERROR: GH_TOKEN not set. Add a Personal Access Token as the GH_PAT secret.")
if not GH_USERNAME:
    sys.exit("ERROR: GH_USERNAME not set. Add it as a repo variable.")

GRAPHQL_URL = "https://api.github.com/graphql"
REST_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
TIMEOUT = 30


# --- API helpers --------------------------------------------------------------

def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a GraphQL query and raise on errors."""
    r = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    payload = r.json()
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def rest_get(path: str, **params: Any) -> Any:
    """Run a REST GET against the GitHub API."""
    r = requests.get(f"{REST_URL}{path}", headers=HEADERS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# --- Data fetchers ------------------------------------------------------------

def fetch_user_overview(username: str) -> dict[str, Any]:
    """Pull profile fields + pinned repos in a single GraphQL call."""
    query = """
    query($login: String!) {
      user(login: $login) {
        name
        bio
        login
        followers { totalCount }
        following { totalCount }
        repositories(privacy: PUBLIC, ownerAffiliations: OWNER, isFork: false) {
          totalCount
        }
        pinnedItems(first: 6, types: [REPOSITORY]) {
          nodes {
            ... on Repository {
              name
              description
              url
              primaryLanguage { name color }
              stargazerCount
              forkCount
            }
          }
        }
      }
    }
    """
    return graphql(query, {"login": username})["user"]


def fetch_recent_activity(username: str, days: int) -> dict[str, Any]:
    """Summarise the user's public events over the last `days` days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    events = rest_get(f"/users/{username}/events/public", per_page=100)

    recent = []
    for e in events:
        created = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        if created >= since:
            recent.append(e)

    summary = {
        "commits": 0,
        "prs_opened": 0,
        "issues_opened": 0,
        "repos_created": 0,
        "repos_starred": 0,
        "active_repos": set(),
        "window_days": days,
    }

    for e in recent:
        repo = e.get("repo", {}).get("name")
        etype = e["type"]
        payload = e.get("payload", {})

        if etype == "PushEvent":
            summary["commits"] += len(payload.get("commits", []))
            if repo:
                summary["active_repos"].add(repo)
        elif etype == "PullRequestEvent" and payload.get("action") == "opened":
            summary["prs_opened"] += 1
            if repo:
                summary["active_repos"].add(repo)
        elif etype == "IssuesEvent" and payload.get("action") == "opened":
            summary["issues_opened"] += 1
            if repo:
                summary["active_repos"].add(repo)
        elif etype == "CreateEvent" and payload.get("ref_type") == "repository":
            summary["repos_created"] += 1
        elif etype == "WatchEvent":
            summary["repos_starred"] += 1

    summary["active_repos"] = sorted(summary["active_repos"])
    summary["any_activity"] = (
        summary["commits"] + summary["prs_opened"] + summary["issues_opened"]
        + summary["repos_created"] + summary["repos_starred"]
    ) > 0
    return summary


def fetch_top_languages(username: str, top_n: int = 5) -> list[dict[str, Any]]:
    """Aggregate language byte-counts across the user's owned, non-fork repos."""
    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                     orderBy: {field: PUSHED_AT, direction: DESC}) {
          nodes {
            languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node { name color }
              }
            }
          }
        }
      }
    }
    """
    data = graphql(query, {"login": username})["user"]
    totals: dict[str, int] = {}
    colors: dict[str, str | None] = {}

    for repo in data["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"].get("color")

    if not totals:
        return []

    total_size = sum(totals.values())
    sorted_langs = sorted(totals.items(), key=lambda kv: -kv[1])[:top_n]
    return [
        {
            "name": name,
            "pct": round(size / total_size * 100, 1),
            "color": colors.get(name),
        }
        for name, size in sorted_langs
    ]


# --- Rendering ----------------------------------------------------------------

def render_readme(context: dict[str, Any]) -> str:
    # NOTE: trim_blocks/lstrip_blocks are deliberately OFF — they collapse
    # the blank lines we need between markdown list items.
    env = Environment(
        loader=FileSystemLoader("templates"),
        keep_trailing_newline=True,
    )
    template = env.get_template("README.md.j2")
    return template.render(**context)


# --- Main ---------------------------------------------------------------------

def main() -> None:
    print(f"Fetching GitHub data for @{GH_USERNAME}...")
    user = fetch_user_overview(GH_USERNAME)
    activity = fetch_recent_activity(GH_USERNAME, days=ACTIVITY_DAYS)
    languages = fetch_top_languages(GH_USERNAME)

    now = datetime.now(timezone.utc)
    context = {
        "user": user,
        "activity": activity,
        "languages": languages,
        "updated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
    }

    readme = render_readme(context)
    Path("README.md").write_text(readme, encoding="utf-8")
    print(f"Wrote README.md ({len(readme)} chars)")

    state = {
        "last_run": now.isoformat(),
        "username": GH_USERNAME,
        "window_days": ACTIVITY_DAYS,
        "summary": {
            "commits": activity["commits"],
            "prs_opened": activity["prs_opened"],
            "issues_opened": activity["issues_opened"],
            "active_repos": activity["active_repos"],
            "pinned_count": len(user["pinnedItems"]["nodes"]),
            "top_language": languages[0]["name"] if languages else None,
        },
    }
    Path("state").mkdir(exist_ok=True)
    Path("state/last_run.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("Wrote state/last_run.json")


if __name__ == "__main__":
    main()
