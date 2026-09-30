---
name: credential-store-management
description: "Load BEFORE any task that authenticates to a device/service — reading, saving, or rotating passwords, tokens, keys. Store-agnostic three-layer protocol (bootstrap env → SSOT vault → consumers) with pluggable backends; lookup order, field discipline, save protocol, symptom triggers (403, auth fail)."
version: 2.0.0+alrcatraz.0.0.0
author: alrcatraz

platforms: [linux, synology-dsm]

metadata:
  hermes:
    tags: [credentials, passwords, authentication, ssh, keepass, gpg, secrets]

triggers:
  - "GPG credential"
  - "Keepass query"
  - "Permission denied (publickey)"
  - "SSH login for [machine]"
  - "authentication failed"
  - "bootstrap credentials"
  - "check credential"
  - "credential lookup"
  - "device credentials"
  - "find password for [machine/service]"
  - "find password for device"
  - "get token for [service]"
  - "git push 403"
  - "how to log into"
  - "look up credentials"
  - "need sudo password"
  - "need the password for"
  - "save this password"
  - "store this token"
  - "sudo access required"
  - "sudo 失败"
  - "凭据存一下"
  - "密钥归档"
  - "查凭据"
  - "记住这个密码"

tools:
  - terminal
  - keepassxc-cli
  - gpg
---

# Credential Store Management

## 硬规则（先于一切）

**任何需要向设备/服务认证的任务——读取、保存、轮换凭据——动手前先加载本技能，
无论你打算用什么方式拿凭据。** 包括：SSH 登录、git push 403、sudo 失败、API token
获取、「这个密码帮我存一下」。memory 里的速查条目不能替代本技能的完整规程。

## Principle

**Never invent, guess, or generate credentials.** Every machine and service has its
credentials in one of the known stores. Not found → ask the user; never fabricate.

## Architecture: three layers, pluggable backends

Layers are functional roles, not specific files. Different users run different backends
per layer — some skip a layer entirely (e.g. they memorise web passwords and keep only an
encrypted vault for machines; some use only a password manager). **Discover which backend
is live before assuming the paths below.**

```
Layer 1 — BOOTSTRAP (unlocks everything else)
  Role: master passphrases ONLY — vault master password, GPG key passphrase,
  local sudo fallback. Never device/service secrets.
  Example backend: ~/.hermes/.env, bare KEY=value lines
  (NO export prefix — grep '^KEY='; an '^export KEY=' grep silently returns empty)

Layer 2 — PRIMARY CREDENTIAL STORE (SSOT)
  Role: ALL device + service secrets.
  Example backends: KeePassXC DB (kdbx), GPG-encrypted YAML, pass(1), sops/age.
  Whatever is live here is the single write target for new credentials.

Layer 3 — CONSUMERS
  Runtime configs (.env per service, git credential helpers) READ from Layer 2 on
  demand; they never duplicate secrets.
```

### Lookup Order

```
1.  Layer-2 SSOT                      ← always first
2.  Fallback archives (frozen copies) ← read-only; divergence → SSOT wins, report it
3.  Layer-1 bootstrap                 ← only used to unlock the above
4.  Ask the user                      ← NEVER fabricate
```

## Field discipline (what goes where in a vault entry)

| Data | Field |
|:-----|:------|
| True account+password login (web panel, SSH user) | UserName + Password (+ URL; Additional URLs for browser integration) |
| API tokens, PATs, secret keys, bearer tokens | **custom attributes** — never the Password field |
| Identity documents, PEMs, structured config | **attachments** |
| Usage context, endpoints, semantics, caveats | **notes** |

A vault whose Password field holds a non-password (token) is a schema smell — merge and
re-file as attributes. Likewise, scattered per-key entries for one service should be
merged into a single service entry with each key as a named attribute.

## Layout conventions (KeePassXC backend)

Machine-readable subtree under a dedicated group (e.g. `Sync/Fleet/`), separated from
the user's personal groups so headless sync can scope itself:

- `Devices/<domain>/` — one entry per device, title `<ABBR> <hostname>`. Login lives in
  UserName/Password; connection paths (ordered by network preference), ports, OS, status
  live in custom attributes; URL = primary DNS name.
- `Agents/` — one entry per agent identity: DID/identity docs as attachments, gateway/API
  keys as attributes, scope notes. **Keys follow the agent, not the runtime program.**
- `Services/<class>/` — infrastructure services, merged per the field-discipline rule.
- SSH keys follow the **system entry** of the machine that runs them — there is never a
  central key entry; see `references/ssh-key-domain-model.md` (fleet/kin/external
  three-domain model, attributes-vs-attachments placement, passphrase policy, fleet
  `~/.ssh/config` managed block convention).

Human-domain entries (website logins the user created) live in the user's own groups
(`Passwords`, `Passwords with Passkeys`, …). **Augment in place** (attributes / notes /
attachments); never duplicate, never relocate into the machine subtree. Category dirs
that exist purely to organize hold no entries.

If multiple clients share the vault through a sync container: keep the container scoped
to the machine subtree, give containers their own master passwords when warranted, and
make pull the default direction with push explicitly opted-in and path-scoped.

## 保存凭据（写路径规程）

新获得的凭据**必须回写 Layer-2 SSOT**，不许只留在会话里：

1. 按布局约定选落位（设备 / Agents / Services / 人类域就地增补），按字段纪律选栏位；
2. **写完立即验证**：重新打开库读回该值比对，再触发同步（Fleet-scoped push）；
3. **git remote 免密** → repo-local `credential.helper` resolving from the vault
   （见 `references/fleet-git-credential-helper.md`）；**绝不把密码内联进 remote URL**
   （会落进 `.git/config` 明文）；
4. Frozen fallback archives are **not write targets**; on value divergence, the SSOT
   wins — report it rather than editing the archive.

## Reading recipes (KeePassXC backend)

```bash
KP_PASS=$(grep '^KEEPASS_PASSWORD=' ~/.hermes/.env | cut -d= -f2- | sed "s/^'//;s/'$//")

echo "$KP_PASS" | keepassxc-cli search <DB.kdbx> "<keyword>"
echo "$KP_PASS" | keepassxc-cli show -s <DB.kdbx> "<entry-path>"
```

Prefer **pykeepass** for bulk/programmatic work — CLI parsing drops custom properties and
attachments. Helper: `scripts/keepass-query.sh`.
Headless edit recipe: run with `~/.hermes/hermes-agent/venv/bin/python`
(kernel default python lacks pykeepass) → `kp.find_entries(title=..., first=True)` →
assign `e.password` → `kp.save()`; then REOPEN the db, read back, compare, and live-test
the credential (e.g. ssh echo ok) before declaring done. `get_entries_by_title` does not
exist — it is `find_entries(title=)`; the Entry attribute is `e.username`, not
`userName` (AttributeError).

GPG-YAML backend (archive or primary, depending on deployment):

```bash
GPG_PASS=$(grep '^<GPG_KEY_VAR>=' ~/.hermes/.env | cut -d= -f2- | sed "s/^'//;s/'$//")
printf '%s' "$GPG_PASS" | gpg --batch --no-tty --pinentry-mode loopback --passphrase-fd 0 \
  --decrypt <file>.yaml.gpg 2>/dev/null
```

Editing such a file: decrypt to temp → edit → re-encrypt with **plaintext as a FILE
argument** together with `--passphrase-fd 0`; never `cat file | gpg --passphrase-fd 0`
(stdin collision mangles the passphrase → corrupt ciphertext). Always re-decrypt and
verify round-trip before deleting backups. Details: `references/gpg-credential-edit-workflow.md`.

## Practical Workflow: Device Sudo Access

1. Resolve the device entry in the SSOT; its Password field is the login/sudo password.
   Device keys are lowercase-no-spaces hostnames.
2. Execute via the **only pattern that survives Hermes terminal's security layer** —
   standalone temp script, never pipe-into-shell-construct:

```bash
cat > /tmp/sudo-job.sh << 'SCRIPT'
systemctl restart <unit>
SCRIPT
chmod +x /tmp/sudo-job.sh
echo "$DEVICE_PASS" | sudo -S /tmp/sudo-job.sh
rm -f /tmp/sudo-job.sh
```

   ❌ `echo "$PASS" | sudo -S tee/sh -c ...` → `sudo_auth_failed` even with the right
   password. `SUDO_ASKPASS` is also blocked (terminal forces `-S`). On remote hosts wrap
   inner commands in `sh -c '...'` inside the script to survive SSH quoting.

## KeePassXC CLI 写入/读取陷阱（keepassxc-cli 2.7.x，实测于 <host-01>）

1. **`add -p` 必须显式带 `-p`**：不带 `-p` 时 stdin 第二行被当噪音丢弃、条目密码落成空——这就是历史多条 9 位截断条目（Garage nix-ro/nix-rw、Gitea PAT）的成因。正确写法：`printf '%s\n%s\n' "$DB_PASS" "$ENTRY_PW" | keepassxc-cli add <kdbx> "<绝对路径>" -u <user> -p --url ... --notes ...`。
2. **读回核验用 `show -a Password`**（输出裸值）；普通 `show` 打 `***`，`show -s` 在本版本反而打空。写后必做 len+等值比对，别信 add 的 "Successfully added"。
3. **路径语义**：同名残留（含 Recycle Bin 里刚 rm 的）会让绝对路径 add 报 "Could not create entry"；先 rm 再 add，或临时改名腾位。
4. **脚本化重铸凭据时，服务端是真相源**：create/rotate 的输出必须当场捕获落库；中途失败的脚本会留下幽灵 AK（本会话 GK0ddacf… 事故：半成品 rotation 脚本自删旧 key 后新 key 未生效，KeePass/AWS profile 全指向不存在的 AK）。改完凭据后跑一次真实签名请求（如 `nix store info --store s3://…`）验证，勿以 CLI 读回为准。
5. 清理残留：批量试错后 `ls "/Recycle Bin"` 清点并告知后续维护者。

## Pitfalls

1. **Bootstrap passphrase is the master key** — if exposed, rotate it AND re-encrypt
   every store it unlocks. Keep real secrets out of skills, memory, and git; reference
   vault entries by title/path and resolve values at runtime.
2. **Sudo passwords differ per device** — resolve each from its SSOT entry; never assume
   the local fallback applies remotely.
3. **CLI `add -g` GENERATES a random password** and discards the intended value; after
   any scripted write, verify values by hash against the source.
4. **Two-database operations need two passwords** — merge/sync between a main DB and a
   sync container may prompt twice; keepassxc-cli prompt-order bugs silently corrupt
   merges (prefer pykeepass, which takes them as arguments).
5. **pykeepass gotchas**: `kp.entries` can miss freshly-added rows — iterate
   `group.entries` via `find_groups(...)`; `Entry.path` is a LIST of strings, not a path
   string; `add_binary()` returns the binary id int directly; `Group.groups` does not
   exist (use `.subgroups`).
6. **Recycle-bin ghosts** — old duplicates sitting in the Recycle Bin still appear in
   some traversals and can resurrect through bidirectional merges; filter by path and
   verify convergence (dry-run shows pull=0 push=0) after any consolidation.
7. **Never restate a secret's value in a new store when an existing bootstrap variable
   already holds it.** If the user names a passphrase that equals an already-registered
   credential ("the classic password"), resolve it from its registered source (e.g.
   `.env` `SUDO_PASSWORD`) via variable reference — do not echo, log, or copy the literal
   into commands, files, or replies; process listings and shell history leak it.

## References

- `references/ssh-key-domain-model.md` — SSH fleet/kin/external key domains, vault placement, config block
- `references/env-variable-extraction.md` — Reading .env variables safely
- `references/session-token-extraction.md` — Token/cookie extraction from browsers
- `references/gpg-credential-edit-workflow.md` — GPG YAML edit cycle (archive/legacy backend)
- `references/fleet-git-credential-helper.md` — Non-interactive git auth from the vault
- `scripts/keepass-query.sh` — KeePass lookup helper
