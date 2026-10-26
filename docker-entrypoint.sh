#!/bin/sh
set -e

# Default BIZINTEL_COOKIE_SECURE to false if unset
if [ -z "$BIZINTEL_COOKIE_SECURE" ]; then
    export BIZINTEL_COOKIE_SECURE="false"
fi

# Ensure data directory exists
mkdir -p /app/data 2>/dev/null || true

# Session secret resolution:
# If unset, read from /app/data/.session_secret or generate one and persist it
if [ -z "$BIZINTEL_SESSION_SECRET" ]; then
    SECRET_FILE="/app/data/.session_secret"
    if [ -f "$SECRET_FILE" ] && [ -s "$SECRET_FILE" ]; then
        BIZINTEL_SESSION_SECRET=$(cat "$SECRET_FILE")
    else
        BIZINTEL_SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
        printf "%s" "$BIZINTEL_SESSION_SECRET" > "$SECRET_FILE" 2>/dev/null || true
        chmod 600 "$SECRET_FILE" 2>/dev/null || true
    fi
    export BIZINTEL_SESSION_SECRET
fi

exec uvicorn api.main:app --host 0.0.0.0 --port 8000 "$@"
