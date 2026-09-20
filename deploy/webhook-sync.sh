#!/usr/bin/env bash
# webhook-sync.sh — keeps the GitHub webhook pointed at the current cloudflared
# quick-tunnel URL. Quick tunnels get a new URL on every restart; this loop
# detects the change and PATCHes the hook, then sends a ping to verify.
set -u

REPO="HoTWinGs06/pr-reviewer-sandbox"
HOOK_ID="682286601"
LOG="/home/hermes/.local/state/pr-reviewer-tunnel.log"
STATE="/home/hermes/.local/state/pr-reviewer-webhook-url"
ENVFILE="/home/hermes/projects/autonomous-pr-reviewer/.env"

# Extract only the variables we need; the .env contains ${...} references
# that would trip set -u if sourced wholesale.
GITHUB_TOKEN=$(grep -E '^GITHUB_TOKEN=' "$ENVFILE" | head -1 | cut -d= -f2-)
WEBHOOK_SECRET=$(grep -E '^WEBHOOK_SECRET=' "$ENVFILE" | head -1 | cut -d= -f2-)

if [ -z "$GITHUB_TOKEN" ] || [ -z "$WEBHOOK_SECRET" ]; then
    echo "ERROR: GITHUB_TOKEN or WEBHOOK_SECRET missing from $ENVFILE" >&2
    exit 1
fi

mkdir -p "$(dirname "$STATE")"
touch "$LOG"

log() { echo "[$(date '+%F %T')] $*"; }

while true; do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" 2>/dev/null | tail -1 || true)
    LAST=$(cat "$STATE" 2>/dev/null || true)

    if [ -n "$URL" ] && [ "$URL" != "$LAST" ]; then
        log "tunnel URL is $URL (was: ${LAST:-none}) — updating webhook"
        HTTP=$(curl -s -o /tmp/webhook-update.json -w "%{http_code}" \
            -X PATCH \
            -H "Authorization: Bearer $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/$REPO/hooks/$HOOK_ID" \
            -d "{\"config\":{\"url\":\"$URL/webhook\",\"content_type\":\"json\",\"secret\":\"$WEBHOOK_SECRET\"}}")
        if [ "$HTTP" = "200" ]; then
            echo "$URL" > "$STATE"
            # verify with a ping delivery
            PING=$(curl -s -o /tmp/webhook-ping.json -w "%{http_code}" \
                -X POST \
                -H "Authorization: Bearer $GITHUB_TOKEN" \
                -H "Accept: application/vnd.github+json" \
                "https://api.github.com/repos/$REPO/hooks/$HOOK_ID/pings")
            log "webhook updated (HTTP $HTTP), ping trigger HTTP $PING"
        else
            log "ERROR: webhook PATCH failed with HTTP $HTTP (will retry next loop)"
        fi
    fi
    sleep 60
done