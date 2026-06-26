#!/bin/bash
# KeePass query via keepassxc-cli (no Python dependency)
# Usage: echo 'master_password' | keepass-query.sh <keyword>
#
# Password source (priority):
#   1. stdin pipe (recommended, most secure)
#   2. KEYPASS_PW environment variable (when stdin unavailable)
#
# Examples:
#   echo 'password' | keepass-query.sh github
#   KEYPASS_PW='password' keepass-query.sh github

DB="${KEEPASS_DB:-$HOME/Documents/KeePassXC/Combined.kdbx}"
KEYWORD="$1"

if [ -z "$KEYWORD" ]; then
    echo "Usage: keepass-query.sh <keyword>" >&2
    exit 1
fi

# Read password from stdin or environment
if [ -t 0 ]; then
    # stdin is a terminal → use environment variable
    PW="${KEYPASS_PW}"
else
    # stdin has data → read first line
    read -r PW
fi

if [ -z "$PW" ]; then
    echo "ERROR: Password required via stdin pipe or KEYPASS_PW env var" >&2
    exit 1
fi

# Search for the entry
ENTRY_PATH=$(echo "$PW" | keepassxc-cli search "$DB" "$KEYWORD" 2>/dev/null | head -1)
if [ -z "$ENTRY_PATH" ]; then
    echo "{\"error\": \"No entry found for: $KEYWORD\"}"
    exit 1
fi

# Show full details
echo "$PW" | keepassxc-cli show -s "$DB" "$ENTRY_PATH" 2>/dev/null
