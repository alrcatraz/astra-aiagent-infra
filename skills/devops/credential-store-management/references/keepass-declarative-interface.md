# KeePassXC ↔ declarative-systems interface (surveyed 2026-09)

How fleet credentials in `Combined.kdbx` may cross into declared system configs
(Guix config.scm / Nix flake) without breaking either store's rules. This is the
boundary map; it was produced by read-only pykeepass survey — no values were
exported or copied.

## The vault's own red line (learned from its history, not invented here)

The **Password field has a truncation bug class**: keepassxc-cli 2.7.x `add`
without explicit `-p` silently stores an EMPTY password, and historical entries
were found truncated to 9 chars. Therefore:

- **Never put any credential value in Password for machine-readable consumers**
  (the fleet subtree already follows this: tokens/keys are custom attributes;
  Password holds only human-typed login secrets).
- Declarative configs must resolve values from **custom attributes**, never
  assume Password.

## Value classification within one device entry (<host-01>, Personal domain)

Same entry mixes three trust classes — this is the core fact for config design:

| Class | Examples | May appear in a declaration? |
|:------|:---------|:-----------------------------|
| Public topology | URL (`*.internal.example`), LanIP, OverlayIPs, SSHPort, Paths, Status, OS | yes — but see drift rule |
| Key material (public halves) | `ssh_fleet_pub`, `ssh_kin_pub`, `ssh_external_pub`, fp attrs | yes freely |
| Secrets | Password (sudo/login), `ssh_external_passphrase`, all `*Token*/*Key*/*Secret*` attrs, attachment `id_ed25519_*` (private keys!) | **NEVER** |

Note: **attachments hold private keys**. Anything derived from the vault that
lands in `/gnu/store` or `/nix/store` becomes world-readable — so even
"non-secret-looking" fields deserve a second look before embedding.

## Interface patterns, ranked

### Pattern A — reference-by-path + runtime resolver (fleet standard)

Declaration stores only `("vault" "Sync/Fleet/Devices/Personal/<host>")` as a
string plus the attribute name; a helper resolves the value at run time outside
the store. Precedent already live: `references/fleet-git-credential-helper.md`
(git credential.helper resolving from the vault). Same shape generalises to
services needing a token: pass them a *command* that invokes the resolver, not a
value.

Guix specifics:
- use `password-file` / `--credentials-from-command` style options over literal
  password fields wherever both exist (mirrors Guix manual guidance);
- the resolver itself (a script reading .env bootstrap + querying kdbx) can be
  declared; its output path lives under `/run/secrets` (tmpfs), never `/etc` or
  the store.

### Pattern B — build-time injection into store objects (rejected)

Resolving a secret during `guix system reconfigure` and letting it serialize into
config.scm-derived files makes it a store object: world-readable, GC-retained,
and copied into every generation snapshot. Rejected outright.

### Pattern C — embed public topology in declarations (allowed, with drift rule)

Hostnames/IPs/ports CAN be written into config.scm/flake when functionally
required (e.g. substitute server URLs, deploy targets). But the vault is SSOT for
connection paths, so embedded copies must carry a machine-checkable marker
(comment convention like `;; ssot: Sync/Fleet/...`) and a drift-audit step in CI
or the deploy script compares marked values against the vault entry. Without the
audit, prefer deriving at eval time via Pattern A's resolver for non-secret
fields too — Scheme/Nix can call the same helper.

## Per-entry schema cheat-sheet (as surveyed)

```
Devices/<domain>/<ABBR> <hostname>
  UserName/Password   human login (SSH/sudo); agents resolve via ssh keys instead
  URL                 primary DNS name
  Notes               JSON connection-paths block (priority-ordered)
  attrs               LanIP OverlayIPs Paths SSHPort Status OS RelatedDevice
                      ssh_{fleet,kin,external}_pub  ssh_external_fp/passphrase/status
                      ssh_key_model
  attachments         id_ed25519_<domain>  (PRIVATE key material)
Agents/<name>         identity docs as attachments; API keys as attrs
Services/<class>/<svc>  AK/SK pairs as attrs (AccessKeyId_ro etc.), no Password
```

Domain note: `Devices/` root duplicates <host-01>/NAS/WRT as flat entries while the
same titles exist under `Personal/`+`Infra/` subgroups — two records, one truth.
The Devices-root copies carry only ssh_external_* attrs (deployment status
tracking); the domain subgroups carry full connectivity. When resolving for a
declaration, target the **domain subgroup entry**, not the root twin.

## pykeepass survey recipes (read-only)

```python
kp = PyKeePass(db, password=<resolved from ~/.hermes/.env KEEPASS_PASSWORD>)
g = kp.find_groups(path=["Sync","Fleet","Devices","Personal"], first=True)
e = kp.find_entries(title="<host-01> <host-01>", first=True)
v = e.custom_properties["ssh_fleet_pub"]      # attr access
att = e.attachments                            # dict: name -> BinaryAttachment
p = "/".join(e.path)                            # path IS list[str] — do NOT do x.name
```

Gotchas hit during this survey (already in SKILL.md pitfalls, restated here for
this file's context): `Entry.path` is a list of strings; `e.attachments` is a
dict keyed by attachment name; iterating it yields names, not ids.
