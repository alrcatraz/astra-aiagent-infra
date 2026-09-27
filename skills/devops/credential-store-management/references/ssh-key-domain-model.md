# SSH Key Domain Model (fleet / kin / external)

## Layout discipline

**There is no central "SSH Keys" entry.** SSH credentials live inside the KeePassXC
**system entry** of the machine that runs them, next to its login, access paths, and
ports: needing to connect anywhere = find that system's entry, read everything there.
One physical machine running N OSes has N entries, each carrying the machine's full
key set (deliberate duplication — restoring any OS needs no topology lookup).

- Private keys → **attachments** (named `id_ed25519_<domain>`); multi-line PEM must
  survive byte-exact for disk restore.
- Public keys + fingerprints → **custom attributes** (`ssh_<domain>_pub`, single line,
  paste-able into authorized_keys).
- Passphrases (when a domain uses them) → custom attribute, never the Password field.

## Three trust domains

| Domain | Key model | Passphrase | Reason |
|:-------|:----------|:-----------|:-------|
| `fleet` | one global key shared by all owned machines | **none** | unattended SSH handshakes (e.g. desktop app → agent) are a hard dependency; authorized_keys everywhere under our control |
| `kin` | one global key | none | environments of trusted persons; low, self-maintainable blast radius |
| `external` | **per-physical-machine keys** | bcrypt passphrase, stored in the entry | hostile territory (rented GPUs, shared lab servers): a compromise is revoked single-entry, no blast radius |

Public-key comments follow `<domain>-<machine>` so any authorized_keys line
self-documents its domain and origin.

Why shared keys are acceptable for fleet/kin but not external: with an encrypted
synced vault, all stored secrets share one trust boundary already (same reasoning as
accepting SD-WAN transport); the extra revocation granularity only pays off where the
*peer* is untrusted — and per-peer keys multiply O(N) authorized_keys maintenance.

## Fleet config block convention

Every fleet machine carries an identical managed block in `~/.ssh/config`
(`# >>> astra fleet ssh block … >>>`), pinning for each peer alias:

```
Host <abbr> <hostname> <hostname>.<internal-domain>
    HostName <overlay-or-LAN name reachable FROM THIS machine>
    User <user> ; Port <port>
    IdentityFile ~/.ssh/id_ed25519_fleet
    IdentitiesOnly yes
```

- `IdentitiesOnly yes` is mandatory — without it ssh offers every loaded identity and
  untrusted peers get a free allowlist probe.
- HostName is per-box: passive LAN members (e.g. a NAS off the SD-WAN) must use the LAN
  IP; DSM lacks `ssh-keyscan`, seed its known_hosts from a machine that has it.
- dropbear (OpenWrt) has no client config story — it is append-only in the other
  direction: raw public key lines in `/etc/dropbear/authorized_keys`.

## Key rotation / hygiene notes

- Reusing an existing working key as the fleet key is fine; what was wrong before was
  **undocumented drift** (the same private key copied to another machine under the old
  name, no entry, no audit). Explicit per-domain sharing, registered in the vault, is a
  design; silent copying is an accident.
- Quantum stance: identity keys stay ed25519 (compatibility with dropbear/NAS/Windows
  sshd is the binding constraint). Post-quantum protection comes for free from the
  hybrid KEX (`mlkem768x25519`) negotiated by modern OpenSSH at session setup — no
  identity migration needed. Revisit PQC signatures only when the fleet's heterogeneous
  servers all support them.
- A headless job needing passphrase-protected `external` access should get its own
  dedicated no-passphrase key, not a weakened daily key.
- Order of operations for any migration touching these entries: land keys + authorize
  (append-only) → vault ingest + hash-verify round-trip → verify connectivity matrix →
  only then delete legacy names.
- pykeepass 4.x attachment API: `kp.add_binary(data)` returns a binary id;
  `entry.add_attachment(id, filename=...)` (filename positional-required, the stored
  name); `add_binary` accepts no filename kwarg.
