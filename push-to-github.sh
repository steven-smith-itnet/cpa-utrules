#!/usr/bin/env bash
#
# push-to-github.sh
# -----------------
# Fully automated push of this directory to your GitHub account using the
# GitHub CLI (gh). Assumes you are ALREADY authenticated (`gh auth login`).
#
# It is idempotent -- safe to run repeatedly:
#   * initializes git if needed
#   * ensures a .gitignore (so __pycache__ etc. are not committed)
#   * creates the GitHub repo (private) if it does not already exist
#   * makes sure 'origin' points at your repo
#   * commits any changes and pushes
#
# Usage (from the cpa-utrules directory):
#   ./push-to-github.sh                 # commit + push (default private)
#   ./push-to-github.sh "my message"    # custom commit message
#
set -euo pipefail

# ---- Config -----------------------------------------------------------------
REPO_NAME="cpa-utrules"          # GitHub repository name
VISIBILITY="private"             # private | public
BRANCH="main"                    # branch to push
COMMIT_MSG="${1:-Update CPA Utah rules study app ($(date +%Y-%m-%d\ %H:%M))}"

# ---- Helpers ----------------------------------------------------------------
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ---- Preconditions ----------------------------------------------------------
command -v git >/dev/null 2>&1 || die "git is not installed."
command -v gh  >/dev/null 2>&1 || die "GitHub CLI (gh) is not installed."
gh auth status >/dev/null 2>&1 || die "Not authenticated. Run: gh auth login"

GH_USER="$(gh api user --jq .login)"
[ -n "$GH_USER" ] || die "Could not determine your GitHub username from gh."
REPO_SLUG="${GH_USER}/${REPO_NAME}"
say "Authenticated as: ${GH_USER}"
say "Target repository: ${REPO_SLUG} (${VISIBILITY})"

# ---- Git init (if needed) ---------------------------------------------------
if [ ! -d .git ]; then
  say "Initializing new git repository..."
  git init -q
fi

# Ensure we are on the desired branch name.
git checkout -q -B "$BRANCH"

# ---- Ensure a .gitignore ----------------------------------------------------
if [ ! -f .gitignore ]; then
  say "Creating .gitignore..."
  cat > .gitignore <<'EOF'
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/

# OS / editor cruft
.DS_Store
Thumbs.db
EOF
fi

# ---- Ensure the GitHub repo exists ------------------------------------------
if gh repo view "$REPO_SLUG" >/dev/null 2>&1; then
  say "GitHub repo already exists."
else
  say "Creating ${VISIBILITY} GitHub repo ${REPO_SLUG}..."
  gh repo create "$REPO_SLUG" "--${VISIBILITY}" --disable-wiki
fi

# ---- Ensure 'origin' points at the repo -------------------------------------
REMOTE_URL="https://github.com/${REPO_SLUG}.git"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi
say "origin -> $(git remote get-url origin)"

# ---- Commit any changes -----------------------------------------------------
git add -A
if git diff --cached --quiet; then
  say "No new changes to commit."
else
  say "Committing: ${COMMIT_MSG}"
  git commit -q -m "$COMMIT_MSG"
fi

# ---- Push -------------------------------------------------------------------
say "Pushing to ${REPO_SLUG} (${BRANCH})..."
git push -u origin "$BRANCH"

say "Done. View it at: https://github.com/${REPO_SLUG}"
