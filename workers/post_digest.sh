#!/bin/bash
# Post weekly digest as a GitHub issue comment.
#
# Uses the lacuene-exp API's /api/digest endpoint to generate markdown,
# then posts it to the tracking issue using the GitHub API.
#
# Requires:
#   GITHUB_TOKEN env var (with repo scope)
#   API must be running (gunicorn on localhost:5100)
#
# Usage:
#   ./workers/post_digest.sh                          # Post to default issue
#   DIGEST_ISSUE=5 ./workers/post_digest.sh           # Custom issue number
#   DRY_RUN=1 ./workers/post_digest.sh                # Print digest, don't post

set -euo pipefail

REPO="mtthdn/lacuene"
ISSUE="${DIGEST_ISSUE:-5}"
API_URL="${LACUENE_API_URL:-http://localhost:5100}"

# Generate digest from the live API
DIGEST=$(curl -sf "${API_URL}/api/digest?format=md" 2>/dev/null) || {
    echo "ERROR: Could not fetch digest from ${API_URL}/api/digest" >&2
    echo "Is the API running? Check: systemctl status lacuene-api" >&2
    exit 1
}

if [ -z "$DIGEST" ]; then
    echo "ERROR: Empty digest response" >&2
    exit 1
fi

# Dry run mode — just print
if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "$DIGEST"
    exit 0
fi

# Post to GitHub
if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "ERROR: GITHUB_TOKEN not set" >&2
    echo "Create a token at https://github.com/settings/tokens with 'repo' scope" >&2
    echo "Then: echo 'GITHUB_TOKEN=ghp_...' >> /etc/environment" >&2
    exit 1
fi

# Escape markdown for JSON payload
BODY=$(python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" <<< "$DIGEST")

HTTP_CODE=$(curl -s -o /tmp/gh_response.json -w "%{http_code}" \
    -X POST \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github.v3+json" \
    -d "{\"body\": ${BODY}}" \
    "https://api.github.com/repos/${REPO}/issues/${ISSUE}/comments")

if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    COMMENT_URL=$(python3 -c "import json; print(json.load(open('/tmp/gh_response.json')).get('html_url',''))")
    echo "Digest posted to ${REPO}#${ISSUE}: ${COMMENT_URL}"
else
    echo "ERROR: GitHub API returned HTTP ${HTTP_CODE}" >&2
    cat /tmp/gh_response.json >&2
    exit 1
fi
