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

## Generating passphrase-protected keys (external domain recipe)

- One-step generation only: `ssh-keygen -t ed25519 -a 16 -N "$PW" -C '<domain>-<hostname>' -f id_ed25519_<domain>`. Never split into generate-empty-then-change — the two-step leaves a window where an unlock test validates against the wrong state and silently produces keys whose passphrase nobody recorded.
- `-Z` selects the *cipher*, not the KDF: `-Z bcrypt` is invalid (`Invalid OpenSSH-format cipher`). bcrypt is the **default KDF** for modern OpenSSH private keys; verify it from the key blob instead of passing a flag: decode the base64 body and read the kdf-name field, or `head -2 <keyfile> | tail -1 | base64 -d | grep -o bcrypt`. Tune cost with `-a <rounds>` (16 = hardened).
- Remote generation: feed the passphrase as a **positional argument to `bash -s -- '<pw>'` and read it as `$1`**, then use `-N "$PW"` inside the script. Do NOT pipe it via stdin when the script itself arrives via heredoc — the heredoc owns stdin and `read` consumes the script's own first line instead (silently producing a key with the script text as its passphrase). Positional args are invisible to other users' process listings only on single-user hosts; accept that tradeoff here rather than inventing a channel.
- Older remote sshd/OpenSSH combinations may reject newer flags — probe `ssh -V` per host and keep commands inside the intersection of what fleet hosts support.
- Verify every generated key immediately, both directions: `ssh-keygen -y -P "$PW" -f <key>` must succeed (passphrase unlocks), and the same command with a wrong/empty passphrase must fail. A key that passes neither check was built from a mangled password in transit.

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
- Vault PoC orphans: early prototype entries created with `keepassxc-cli add -g` (random
  garbage password) can linger at a parent group root after the real entries were moved
  into subdirectories. Before deleting any duplicate, resolve truth against the frozen
  GPG archive (decrypt → sha256-compare each candidate's password field → the match
  wins); never assume which copy is stale from path or timestamps alone.
- pykeepass 4.x attachment API: `kp.add_binary(data)` returns a binary id;
  `entry.add_attachment(id, filename=...)` (filename positional-required, the stored
  name); `add_binary` accepts no filename kwarg.
- **Deletion semantics in vault-sync scripts**: `kp.delete_entry()` moves the entry to
  the recycle bin, and recycled Fleet corpses resurrect through bidirectional merges —
  hard-delete via `el._element.getparent().remove(el)` and purge matching recycle-bin
  titles in the same pass. Any sync that only compares entry *existence* misses
  in-place augmentation (attachments/attributes added to an already-pushed entry):
  compare content signatures (attachment-name set + custom-property-key set) and
  replace drifted container copies while carrying their UUID so KeeShare merge treats
  it as the same entry with history.
- Mount guard for CIFS-hosted backup pools: when the mount drops, the destination
  directory still exists as an empty local shadow and snapshot jobs write into `/home`
  silently. `mountpoint -q <path>` before writing, refuse loudly otherwise.
