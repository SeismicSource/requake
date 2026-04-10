#!/usr/bin/env bash
# Copyright (c) 2021-2026 Claudio Satriano <satriano@ipgp.fr>
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/make_release.sh VERSION [--dry-run]

VERSION input:
    - You can pass "0.7" or "v0.7" (both are accepted)
    - Recommended input is "0.7"
    - The created git tag is always "vVERSION" (example: "v0.7")

Create a release commit and annotated git tag following this repository workflow:
1) Move CHANGELOG "unreleased" entries to "vVERSION - YYYY-MM-DD"
2) Commit CHANGELOG as "Release vVERSION"
3) Create annotated tag "vVERSION"

Options:
  --dry-run  Validate and print the actions without changing files
  -h, --help Show this help

Note:
    Run help as "scripts/make_release.sh -h" (not just "-h").

Examples:
    scripts/make_release.sh 0.7
    scripts/make_release.sh v0.7
    scripts/make_release.sh 0.7.1
    scripts/make_release.sh v0.7 --dry-run
EOF
}

die() {
    echo "Error: $*" >&2
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -eq 0 ]]; then
    usage
    exit 0
fi

VERSION="$1"
shift

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $arg"
            ;;
    esac
done

VERSION="${VERSION#v}"
[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+){1,2}$ ]] || die "Invalid version '$VERSION'. Expected N.N or N.N.N (optional 'v' prefix is allowed)"

require_cmd git
require_cmd awk
require_cmd mktemp

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Not inside a git repository"
cd "$REPO_ROOT"

CHANGELOG="CHANGELOG.md"
[[ -f "$CHANGELOG" ]] || die "Missing $CHANGELOG"

if ! git diff-index --quiet HEAD --; then
    die "Working tree is not clean. Commit or stash changes before releasing."
fi

git fetch --tags --quiet

TAG="v$VERSION"
if git show-ref --tags --verify --quiet "refs/tags/$TAG"; then
    die "Tag $TAG already exists"
fi

if ! grep -q '^## unreleased$' "$CHANGELOG"; then
    die "Could not find '## unreleased' in $CHANGELOG"
fi

RELEASE_DATE="$(date +%Y-%m-%d)"
COMMIT_MSG="Release $TAG"

echo "Release configuration"
echo "  version: $VERSION"
echo "  tag: $TAG"
echo "  date: $RELEASE_DATE"
echo "  dry-run: $DRY_RUN"

if $DRY_RUN; then
    echo
    echo "Dry run checks passed. Planned actions:"
    echo "  1) Update $CHANGELOG headings"
    echo "  2) git add $CHANGELOG"
    echo "  3) git commit -m \"$COMMIT_MSG\""
    echo "  4) git tag -a $TAG -m \"$COMMIT_MSG\""
    BRANCH="$(git rev-parse --abbrev-ref HEAD)"
    echo "  5) git push origin $BRANCH $TAG"
    echo
    echo "Undo (if not pushed):"
    echo "  git tag -d $TAG"
    echo "  git reset --hard HEAD~1"
    exit 0
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

awk -v ver="$VERSION" -v d="$RELEASE_DATE" '
BEGIN { done=0 }
{
    if (!done && $0 == "## unreleased") {
        print "## unreleased"
        print ""
        print "## v" ver " - " d
        done=1
    } else {
        print $0
    }
}
END {
    if (!done) {
        exit 2
    }
}
' "$CHANGELOG" > "$TMP_FILE" || die "Failed to update $CHANGELOG"

mv "$TMP_FILE" "$CHANGELOG"
trap - EXIT

git add "$CHANGELOG"
git commit -m "$COMMIT_MSG"
git tag -a "$TAG" -m "$COMMIT_MSG"

echo
echo "Release commit and tag created locally."
echo "Push manually with:"
echo "  git push origin $(git rev-parse --abbrev-ref HEAD) $TAG"
echo
echo "Undo (if not pushed):"
echo "  git tag -d $TAG"
echo "  git reset --hard HEAD~1"
