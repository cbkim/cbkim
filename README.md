# Meldnest Engagement Agent — Phase 1: Profile Auto-Updater

A self-contained GitHub Action that regenerates your GitHub profile README every
morning, summarising the last week of activity, your pinned projects, and your
recent language mix. **Zero cost, no credit card, no servers to maintain.**

This is phase 1 of a larger engagement agent. It's deliberately simple:
no LLM, no third-party services, just the GitHub API and a Jinja template.
Validate this works for you before adding generative content.

---

## What you get

After setup, your profile (the page at `https://github.com/<your-username>`) will
auto-refresh with sections like:

- **🏗️ Currently building** — your pinned repos with stars and primary language
- **📅 The last 7 days on GitHub** — commits, PRs, issues, repos you've been active in
- **💻 Recent tech mix** — top 5 languages weighted by bytes across your owned repos
- **📊 At a glance** — repo / follower / following counts
- A footer with a timestamp of the last run

The action runs daily at **06:00 EAT** (03:00 UTC). You can also trigger it
manually from the Actions tab any time.

---

## Setup (10 minutes)

### Step 1 — Create or open your profile repo

GitHub renders the README of a repo named exactly the same as your username on
your profile page. So if your username is `cbkim`, the repo must be named
`cbkim`.

If you don't have one yet:
1. Create a new public repo with the same name as your username
2. Tick "Add a README"

### Step 2 — Add these files to that repo

Copy the contents of this folder into the repo. The structure should look like:

```
<your-username>/
├── .github/workflows/profile-update.yml
├── scripts/update_profile.py
├── templates/README.md.j2
├── state/.gitkeep
├── requirements.txt
├── .gitignore
└── README.md   ← will be overwritten by the action; that's expected
```

### Step 3 — Create a Personal Access Token (no card needed)

1. Go to https://github.com/settings/tokens?type=beta (fine-grained tokens)
2. Click **Generate new token**
3. Name it: `profile-readme-updater`
4. Expiration: 1 year (max — you'll need to rotate annually)
5. Repository access: **Only select repositories** → pick your profile repo
6. Repository permissions:
   - **Contents**: Read and write
   - **Metadata**: Read-only (auto-selected)
7. Account permissions:
   - **Followers**: Read-only
8. Generate, copy the token (starts with `github_pat_...`)

> **Why a PAT instead of the default `GITHUB_TOKEN`?** The default token works
> for committing, but the GraphQL queries for follower counts and language
> aggregates are more reliable with a fine-grained PAT. PATs are free and
> require no payment method.

### Step 4 — Configure the repo's Actions environment

In your profile repo, go to **Settings → Secrets and variables → Actions**:

**Secrets tab** → New repository secret:
| Name | Value |
|---|---|
| `GH_PAT` | the token from Step 3 |

**Variables tab** → New repository variable:
| Name | Value |
|---|---|
| `GH_USERNAME` | your GitHub username (e.g. `cbkim`) |
| `ACTIVITY_DAYS` | `7` (optional — change to widen/narrow the activity window) |

### Step 5 — First run (manual)

1. Go to the **Actions** tab of your repo
2. Click **Update Profile README** in the left sidebar
3. If you see a banner saying workflows are disabled for forks, click to enable
4. Click **Run workflow** → **Run workflow**

Watch the run. If it succeeds, your README will be replaced with the generated
version in about 30 seconds. If it fails, check the logs — most failures are
either the token scope or the username variable.

### Step 6 — Confirm the schedule

That's it. The cron schedule (`0 3 * * *`) takes over from tomorrow morning.
You'll see a fresh commit on your profile repo every day from
`github-actions[bot]` with the message `chore: auto-update profile [skip ci]`.

---

## Customising the look

The entire visual output lives in `templates/README.md.j2`. Edit that file,
commit, and the next run will use the new template. Some easy wins:

- Replace the section headers (`🏗️ Currently building` etc.) with your own
- Add a header banner image (drop a PNG into the repo, reference it at the top)
- Add a "Currently exploring" static section above the dynamic ones
- Pull contribution streak data from `github-readme-stats` (an external service)
  by embedding an `<img>` tag

The template has access to:
- `user` — name, bio, login, follower/following counts, public repo count, pinned items
- `activity` — commit/PR/issue counts, list of active repos, the time window
- `languages` — top 5 languages with percentages and Git colours
- `updated_at` — the timestamp of this run

---

## Cost & quota check

| Resource | Used per run | Free quota |
|---|---|---|
| GitHub Actions minutes | ~0.5 min | 2,000/month (private) or unlimited (public) |
| GitHub API calls | ~3 | 5,000/hr authenticated |
| Storage | <1 KB/day | 500 MB free packages |

At one run per day, you'll use roughly **15 minutes/month** of Actions time and
~90 API calls. Both are negligible against the free quotas. If you make this
repo public, Actions minutes are unlimited regardless.

---

## Troubleshooting

**The workflow runs but README doesn't change.**
The script only commits when the rendered output differs from the existing
`README.md`. If you've made manual edits between runs, check that the bot's
commit isn't failing silently — open the Actions log and look at the "Commit &
push if changed" step.

**`Resource not accessible by personal access token`.**
Your PAT scope is too narrow. Re-create with **Contents: Read and write** on
the profile repo specifically.

**Cron isn't firing on time.**
GitHub Actions cron has up to ~15 minutes of jitter under load, and during
heavy usage windows can be longer. This is normal. If it stops firing entirely
for >24h, GitHub disables crons on inactive repos — push any commit to
re-enable.

**I want a different timezone.**
Cron in workflows is UTC. To run at 06:00 in a different timezone, adjust the
`'0 3 * * *'` line in `.github/workflows/profile-update.yml`.

---

## What's next (Phase 2 preview)

Once this has been running for a week and you're happy with the output, Phase 2
adds a Telegram drafts queue: a separate workflow that uses Gemini's free API
to draft platform-specific posts (LinkedIn long-form, X thread, GitHub gist)
from a curated list of topics, and pushes them to a Telegram bot for one-tap
approval before posting.

Don't add Phase 2 until Phase 1 has produced at least 7 successful daily
updates. The point of the phasing is to validate that you actually look at the
output before wiring up more machinery.
