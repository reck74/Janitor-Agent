#!/usr/bin/env bash
# janitor-upstream-target.sh — pick the upstream release a `chore(sync)` should merge.
#
# Usage: scripts/janitor-upstream-target.sh [--tags-ref PREFIX] [--branch REF]
#
#   --tags-ref  ref namespace holding the upstream tags (default
#               refs/upstream-tags, where the sync workflow and MERGE_GUIDE.md
#               fetch them). Never refs/tags in the fork: its own v* release
#               tags (v1.0.0) would compete with upstream's.
#   --branch    ref the release must already be merged into (default origin/main).
#
# Candidates are stable semver tags only: exactly vMAJOR.MINOR.PATCH. That
# drops rc.*, abandoned-rc.*, -rc.N pre-releases and +canary/+channel builds.
# The retired date tags (v2026.9.24, v2026.5.29.2, ...) are excluded
# explicitly: a version sort would rank v2026.x above every v0.x release.
# Candidates are ordered numerically per component (v0.23.10 > v0.23.2).
#
# Prints the newest stable tag when its commit is NOT yet an ancestor of
# --branch, and prints nothing when it already is (nothing to sync). Exits 1,
# with a message on stderr, when the namespace holds no stable semver tag at
# all — a silent "nothing to do" is how a tag-scheme change went unnoticed.
# Works on refs already present locally; it never touches the network.

set -euo pipefail

TAGS_REF="refs/upstream-tags"
BRANCH="origin/main"
while [ $# -gt 0 ]; do
    case "$1" in
        --tags-ref) TAGS_REF="${2:?--tags-ref needs a ref prefix}"; shift 2 ;;
        --branch) BRANCH="${2:?--branch needs a ref}"; shift 2 ;;
        -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
TAGS_REF="${TAGS_REF%/}"

newest="$(
    git for-each-ref --format='%(refname)' "${TAGS_REF}/" \
        | sed -n "s|^${TAGS_REF}/||p" \
        | grep -E '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' \
        | grep -vE '^v20[0-9]{2}\.' \
        | sed 's/^v//' \
        | sort -t. -k1,1n -k2,2n -k3,3n \
        | tail -n 1
)" || true

if [ -z "$newest" ]; then
    echo "No stable vMAJOR.MINOR.PATCH tag under ${TAGS_REF}/ — fetch upstream tags first, or the upstream tag scheme changed." >&2
    exit 1
fi

TAG="v${newest}"
SHA="$(git rev-parse --verify --quiet "${TAGS_REF}/${TAG}^{commit}")"
if git merge-base --is-ancestor "$SHA" "$BRANCH"; then
    echo "${BRANCH} already contains ${TAG} (${SHA})." >&2
    exit 0
fi
echo "$TAG"
