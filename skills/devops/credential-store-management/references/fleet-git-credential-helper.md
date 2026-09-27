# Non-interactive Git Auth from the Vault

Pattern: a git `credential.helper` that resolves the secret from the Layer-2 vault at
auth time, so no password ever lands in `.git/config` or remote URLs. Register it as the
PRIMARY helper and any GUI manager (GCM) last, so headless flows never fall through to an
interactive prompt.

## KeePassXC-backed helper

```bash
#!/usr/bin/env bash
# git-credential-keepass.sh — usage: credential.helper = !/path/to/git-credential-keepass.sh
DB="$HOME/Documents/KeePassXC/Combined.kdbx"
KP_PASS=$(grep '^KEEPASS_PASSWORD=' "$HOME/.hermes/.env" | cut -d= -f2- | sed "s/^'//;s/'$//")

operation=$1
host=""
while IFS== read -r k v; do
  case "$k" in host) host="$v";; esac
done

case "$host" in
  # map git hosts → vault entry titles (extend per forge):
  forge.example.org) ENTRY="/Sync/Passwords/Gitea - Example" ;;
  *) exit 0 ;;   # unhandled host → let other helpers try
esac

show=$(printf '%s\n' "$KP_PASS" | keepassxc-cli show -s "$DB" "$ENTRY" 2>/dev/null)
user=$(printf '%s\n' "$show" | sed -n '/^UserName: /p' | cut -d' ' -f2-)
pass=$(printf '%s\n' "$show" | sed -n '/^Password: /p' | cut -d' ' -f2-)

[ "$operation" = get ] && printf 'username=%s\npassword=%s\n' "$user" "$pass"
exit 0
```

```bash
git config --global credential.helper "!$HOME/.hermes/scripts/git-credential-keepass.sh"
git config --global --add credential.helper manager   # GUI fallback stays last
```

## pass(1)-backed variant

Same protocol, different store: bridge to entries at `git/https/<host>/<username>` via
`pass show`. Choose whichever matches your live Layer-2 backend.

## Pitfalls

- **Pinned-runtime GUI managers break on rolling distros** (e.g. GCM's dotnet tool pinned
  to net8.0 while Tumbleweed ships .NET 10): every HTTPS op prints a .NET install error
  and hangs on interactive prompt. Do NOT chase the runtime — route credentials
  vault-first so the broken helper is never consulted for these hosts.
- **gpg-agent cache TTL**: if the vault chain touches gpg (pass(1), GPG-YAML stores),
  raise `default-cache-ttl` (e.g. 86400) on unattended machines, else cron/agent pushes
  die on a cold cache.
- **Helper script drift**: after patching the canonical copy, redeploy to machines that
  copied it earlier (per-machine copies under `~/.hermes-scripts/` etc.).
- **Never inline passwords into remote URLs** — they persist in `.git/config` plaintext
  and leak into logs.
