# Session Token Extraction from Web Service Databases

Some web services store active login sessions in their database. When
the REST API rejects your credentials (wrong password, expired hash),
an active session in the DB can be used directly to access the API.

## General Approach

1. **Identify the session store.** Look for SQLite databases in the
   service's data directory. Common session table names: `sessions`,
   `tower_sessions`, `user_sessions`, `auth_tokens`.

2. **Find active sessions.** List sessions with future expiry dates.

3. **Determine cookie format.** Services using `tower-sessions` (Rust)
   sign cookies with an HMAC. The cookie format is:
   `id=<base64_hmac_signature>=<session_id>`

   Without the signing key, the cookie is invalid. In this case you
   need alternate auth (register a new account, find credentials).

4. **Use the session.** If you can construct a valid cookie, send it
   with API requests via the `Cookie` or `Authorization` header.

## Query Examples

```bash
# List all active sessions
sqlite3 /path/to/service.db "SELECT id, expiry_date FROM tower_sessions"

# Check session data length (login sessions are ~173 bytes)
sqlite3 /path/to/service.db "SELECT id, length(data) FROM tower_sessions"

# Examine raw data
sqlite3 /path/to/service.db "SELECT hex(data) FROM tower_sessions WHERE id='<session_id>'"
```

## Pitfalls

- **Restart invalidates sessions.** If the service was restarted after
  the session was created, the session signing key may have changed.
- **Cookie HMAC is server-secret.** Without the signing key, you can't
  forge a valid cookie from a raw session ID.
- **KeePass export shows the full DB.** `keepassxc-cli export` outputs
  XML with protected values encrypted. Use `keepassxc-cli show -s` for
  plaintext passwords.
