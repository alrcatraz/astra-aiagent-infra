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

**Every machine has exactly ONE entry, under its domain subtree** (`Devices/Personal/`,
`Devices/Infra/`, `Devices/Dad/`). There is no separate flat `Devices/<host>` level, and
no category directory holding same-title entries as the domain subgroups: that split is
the failure mode, not the convention. A machine's external-key deployment status belongs
**in** its entry alongside its other keys, never in a parallel twin — so if root-level
same-title entries reappear, treat them as ghosts (pitfall 10) and resolve everything from
the domain entry.
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

### 写后验证的完整断言集（缺一不可）

「条目数对了」远不够——一次足以毁掉全部附件的写入也会让条目数保持不变。任何脚本化写库
后在**全新进程**中断言这一组，任一不达标即视为写入失败并回滚：

| 断言 | 防的是 |
|:--|:--|
| 条目数 == 预期 | 误删 / 未落盘 |
| `(附件总数, 非空附件数, 非空总字节)` 三者都 ≥ 写入前 | XML 往返类整库附件清零（陷阱 7） |
| 无同名附件重复（每 `filename` 恰好 1 条） | `add_attachment` 追加语义造成的双份（陷阱 13） |
| 目标 attribute 全量 == 权威源（服务端 / 创建时落盘值） | 只改对了一半、值截断、世代过期 |
| 目标 attribute == 另一库同名条目（双库场景） | 两库不同步 |
| 无明文泄漏（私钥内容不得出现在条目 XML 里） | `add_attachment` 误传 data 而非 id |

在**副本**上先跑通再覆盖生产库；覆盖前保留一份可开的历史备份，并在结尾重新打开该备份确认
条目数等于写入前的值——一个打不开的备份等于没有备份。

## Sync topology & semantics (headless KeeShare for <host-01>)

The sync container (`Combined_Sync.kdbx`, on the NAS) is the **first landing point
for changes made on other devices**; the local db is NOT under a sync root. So:
**run the sync first, then read** — a credential "missing" locally may already exist
container-side (pitfall 12).

`~/.hermes/scripts/keepass-sync.sh` (cron every 120m) is a thin wrapper over
`private/scripts/keepass-sync.py`, which implements a headless KeeShare-equivalent:

- **Match by UUID, not (group, title)** — location-independent, the KeeShare way.
  **But UUID alone is not sufficient identity: it must survive a veto layer plus a
  weighted calibration before a merge or delete is allowed.** KeePass's own
  `<DeletedObjects>` list stores a deleted UUID *permanently*, so a UUID-only
  implementation deletes or overwrites any entry later re-introduced under it —
  upstream KeeShare has multiple data-loss reports from exactly this. Layered check:
  1. **Veto fields (must all match, no voting):** attachment set as
     `(filename, sha256)`; `password` sha256 when both non-empty; `username` when both
     non-empty. A different signing key or a different secret is a *different
     credential*, not an edited one.
  2. **Weighted vote (only if vetoes pass):** `username` 2, `url` 1.5, `title` 1,
     `notes` 1, `password` 1 — only fields non-empty on BOTH sides enter the
     denominator.
  3. **Verdicts at a 0.60 threshold:** `≥0.60` = SAME (merge normally, LWW by `mtime`);
     `(0, 0.60)` = **SUSPECT — do not touch, report the field-level diff for the user to
     adjudicate**; `0` = **UUID REUSE** (different credentials share a UUID) — forbid
     merge AND forbid delete, report as corruption.

  Worked calibration, so the threshold stays auditable: renamed + rotated secret →
  username 2 + url 1.5 + notes 1 = 4.5/5.5 = **82%** → merge; renamed + rotated + moved
  host → 2/5.5 = **36%** → SUSPECT. The point of the middle band is that a big edit
  under a matching UUID must stop for a human, never auto-LWW.
- **Merge in time order (LWW by `mtime`)**; the loser's state is appended to the
  winner's history (`Entry.save_history`), never discarded. Save history on the
  *target* entry before mutating it (pitfall 15).
- **Deletions need tombstones; a tombstone is not automatically a broadcast.** Store it
  in the native KDBX `<DeletedObjects>` list (pykeepass exposes the tree via `kp.tree`;
  there is no `deleted_objects` property). Default: **local suppression only** — the
  entry is not pulled back, the container copy is left as an archive. Pushing the
  deletion container-ward is a separate explicit opt-in, scoped to named UUIDs, never a
  blanket broadcast. A blanket broadcast is what causes the upstream data-loss reports:
  the next device merges the deletion and destroys an unrelated entry that happens to
  carry the same UUID.
- **Exclude `Recycle Bin/**` from every index** (entries, title index, UUID index).
  Recycled entries keep live UUIDs and are otherwise resurrected or merged into — the
  measured case had 63 recycle corpses participating in matching.
- **Deletion reports, never auto-executes.** Default output lists delete-candidates;
  `--apply-deletes` is the agent's explicit decision. Rationale: this runs unattended
  where an irreversible delete has no one to stop it, and interactively where the
  agent has the context to decide — the script surfaces facts, the agent decides. An
  entry created in the current run must never also appear as a delete candidate in it.
- **Asymmetric scope, deliberately**: pull covers the whole container payload; push
  is scoped to `Sync/**` (the whole KeeShare payload), both directions ON by default
  and applied as ONE transaction — this script is this box's KeeShare, so a split
  pull/push (or a scope mismatch) can never converge. The phone-shared container still
  must never receive machine-domain (L0) entries, which live outside `Sync/`.
- **Same-title / different-UUID pairs are ONE entry with a forked identity, never two
  entries.** Unify them with **relink** — set the local entry's `uuid` to the container's
  UUID (or vice versa) so both sides match 1:1 — and never by deleting either copy:
  both copies are real (often one copy carries an attachment the other lacks, e.g. a
  signing key), and deleting silently drops credentials from one db. Decide which
  identity wins first, then relink, then re-verify by reopening both dbs in a fresh
  process. If content actually differs (different keys/URLs), stop and surface it for
  the user to adjudicate — do not LWW it away.

**Delete candidates must be scoped to the shared subtree.** The container holds only
the `Sync/` payload while the local db holds the whole `Alrcatraz/` tree (including
`Recycle Bin/`, `Local/`), so "absent from container" is NOT a delete signal outside
`Sync/` — treating it as one offers to wipe the local recycle bin.

Reading the PAT/token a user just saved on another device: **never print its value** —
have the script read it from the container and feed it to the consumer in-process.

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
6. **`show` 的输出长度在 agent 通道里不可信——验证值必须走 XML 导出。** Hermes 的
   凭据脱敏层会改写 `show`/`show --all -s` 打印出的值（实测：正确 26 字符的 AK 显示为
   36、64 字符的 SK 显示为 40），据此判定"条目损坏"会得出完全错误的结论，并诱使你
   "修复"一个本来完好的条目。判定值是否正确只认一条路：`keepassxc-cli export DB >
   /tmp/x.xml` 后用正则从 XML 取 `<Value>`，再与权威源（服务端 `--show-secret`、创建时
   落盘的 kv 文件）做**等值**比较。写入后的读回校验同理，不能以 `show` 输出为准。
7. **绝不要用 `keepassxc-cli` 的 XML 往返来改条目——它会静默摧毁全部附件。**
   `keepassxc-cli 2.7.x` 的 `edit` 不支持自定义 attribute，于是容易想到
   `export DB > x.xml` → 编辑 XML → `import`。**这条路会毁库**：`export` 不导出 Binary
   池（XML 里没有 `<Binaries>` 节点），但条目级的 `<Value Ref="…">` 引用全部保留；
   `import` 于是把每个附件重建为 **0 字节的悬空引用**，而 `rc=0` 照样报成功。实测：
   30 条附件中 20 条有内容（8,558 B）经一次往返全部归零、池 12→2 个空槽；这类脚本的
   自检通常只查 attribute 值和条目数，所以报"成功"。

   **给条目加/改 attribute 只用 pykeepass**（`Entry.set_custom_property(k, v)` +
   `kp.save()`），它在 API 层写 XML、不触碰 Binary 池。

   **任何脚本化写库之后，必须在全新进程里断言附件未回退**，而不只是看条目数：
   ```python
   # (附件总数, 非空附件数, 非空总字节) 三者都不得低于写入前
   n = nz = tot = 0
   for e in kp.entries:
       for a in (e.attachments or []):
           d = bytes(a.data or b'')
           n += 1
           if d: nz += 1; tot += len(d)
   ```
   只看"条目数对不对"会漏掉这个整库级损坏。

## Pitfalls

1. **Bootstrap passphrase is the master key** — if exposed, rotate it AND re-encrypt
   every store it unlocks. Keep real secrets out of skills, memory, and git; reference
   vault entries by title/path and resolve values at runtime.

2. **Consolidating duplicated entries: settle WHICH copy is live before deleting anything.**
   When an entry exists in two places with the same title and *different* secret values,
   file layout is not evidence of seniority — a tidy-looking structural copy can hold the
   live key while the "canonical" place holds a superseded generation. Concretely: derive
   each private key with `ssh-keygen -y [-P <pass>] -f <tmp>` (temp file 0600, unlink after;
   pass `stdin=DEVNULL` and `SSH_ASKPASS=/bin/false` or it blocks forever on the passphrase
   prompt) and compare its `ssh-keygen -lf` fingerprint against (a) the entry's own `*_pub`
   attribute and (b) the target host's live `~/.ssh/authorized_keys`. **Attribute-vs-attribute
   comparison cannot distinguish key generations.** Where entry and live host disagree, the
   host wins; the vault entry is then migrated, not deleted.

   Order that survives the operation: backup the kdbx (copy + verify sha256) → run a
   **pre-flight gate that ABORTS** unless every source entry is fully self-consistent
   (private key derives to the same fingerprint as its own `*_pub` and `*_fp` attrs) →
   migrate attributes + attachment into the surviving entry → reopen the db and re-verify
   by derivation, not by attribute equality → only then remove the duplicate (hard delete,
   see pitfall 9) → sync and confirm convergence. Never delete a duplicate in the same pass
   that discovers it: you cannot tell a stale copy from the last copy until the keys are
   derived.

3. **One entry per system, self-sufficient.** The user's standing rule: a single entry
   holds every fact about that system, so one lookup answers everything (login, all key
   domains, connection paths, deployment status). Two entries sharing a title is a schema
   violation however the duplicates differ — fix it rather than documenting it as a quirk.
   When auditing, look for same-title entries across *any* groups: an empty category
   directory with same-title entries directly under it is the signature of exactly this
   split.

4. **Migrate attribute blocks whole.** When copying a related set of attributes into a
   target entry, verify the *set* arrived complete — a partially migrated block (public key
   + fingerprint present, deployment status missing) reads as valid on inspection but
   breaks every consumer expecting the full set. Compare key *sets*, not just the values
   you happened to check.

5. **Sudo passwords differ per device** — resolve each from its SSOT entry; never assume
   the local fallback applies remotely.
6. **CLI `add -g` GENERATES a random password** and discards the intended value; after
   any scripted write, verify values by hash against the source.
7. **Two-database operations need two passwords** — merge/sync between a main DB and a
   sync container may prompt twice; keepassxc-cli prompt-order bugs silently corrupt
   merges (prefer pykeepass, which takes them as arguments).
8. **pykeepass gotchas**: `kp.entries` can miss freshly-added rows — iterate
   `group.entries` via `find_groups(...)`; `Entry.path` is a LIST of strings, not a path
   string; `add_binary()` returns the binary **id int** (see pitfall 13 for the mandatory
   second step); `Group.groups` does not exist (use `.subgroups`).
9. **Recycle-bin ghosts** — old duplicates sitting in the Recycle Bin still appear in
   some traversals and can resurrect through bidirectional merges. **Delete duplicates
   with a hard delete, never `trash_entry`** — a recycled entry is resurrected by the next
   merge, so the "delete" silently undoes itself.
10. **Sync is computed before it is applied — ghost re-pull poisoning.** When a sync
   script builds its pull list, then pulls, then prunes container-side ghosts, a
   container-only duplicate gets **pulled back locally** every run while the prune
   deletes it container-side: local stays polluted and the cycle repeats. Symptoms:
   `pull=N` on every identical run, push oscillating, duplicates reappearing after
   deletion. Fix: classify suspected ghosts *before* building the pull list — a scoped
   container entry whose leaf title already exists locally under a **different** group is
   a ghost and must never be pulled. Prove a sync fix with **three consecutive**
   `pull=0 push=0` runs, not one; a single clean run is exactly what this bug produces.
11. **Sync returning `exit 0` with `pull=0` is not proof of convergence.** When the
   local db is stale (mtime older than container) and the container has entries the
   local copy lacks, a sync script that reports `pull=0 push=0` has **failed silently**
   — the pull list computation returned empty even though the delta is non-zero.
   Always verify convergence by opening both dbs and comparing entry counts and
   target entry presence, not by trusting exit code alone. If the delta is real and
   the script reports 0, the script's pull-list logic has a bug — do not declare
   sync complete.
12. **PATs and tokens in human-domain entries live in the sync container first.**
   When a credential was just added on another device, the local db copy (typically
   `~/Documents/KeePassXC/Combined.kdbx`, **not** under a sync root) will not have it
   until a successful pull from the sync container. Check the container directly
   (read-only via pykeepass with the container's own password) to confirm the entry
   exists before concluding it is missing.
13. **pykeepass attachment pitfalls:**
   - **The attachment API is TWO steps in 4.2.0, and the obvious call leaks the secret as
     plaintext.** The signature is `Entry.add_attachment(id, filename)` where `id` is an
     **integer** index into the binary pool — NOT the data. Calling
     `add_attachment(sec_bytes, "key.sec")` stores the data string verbatim into the
     entry's `<Binary><Value Ref="...">` attribute, so the private key becomes readable in
     the kdbx XML and every later read raises `ValueError: invalid literal for int()`.
     Correct sequence:
     ```python
     bid = kp.add_binary(sec_bytes)          # -> int; add_binary(data, compressed=True, protected=True)
     entry.add_attachment(bid, "key.sec")    # reference by id
     ```
     Verify by reopening and asserting **both** `att.data == expected_bytes` **and** no
     plaintext marker survives in the entry XML (`"private-key" not in entry._element.xml`)
     — a length check alone does not prove `Ref` holds an integer. To repair an entry
     already poisoned, strip every `<Binary>` child of the entry element, `kp.save()`,
     reopen, then re-add with the two-step sequence above.
   - `Entry.delete_attachment(att)` works. `PyKeePass.remove_attachment` does **not** exist.
   - **`add_attachment` APPENDS; it never replaces a same-named attachment.** Repairing an
     entry that already carries a 0-byte `<name>` by adding content under the same
     filename leaves the entry holding BOTH (`[('key.sec',0), ('key.sec',192)]`), and a
     verifier reading `attachments[0]` then reports the stale one and rejects a correct
     repair. Delete every attachment whose filename matches first, then add once —
     and make verification aggregate by filename (`len([a for a in e.attachments if
     a.filename == f]) == 1`) rather than indexing.
   - **`add_binary` must be called on the database, not the entry** — `kp.add_binary(data)`
     then `entry.add_attachment(bid, name)`. Reading `att.data` back always returns bytes;
     wrap in `bytes(...)` before hashing so `sha256` does not receive `bytearray`.
   - The native shape is `<Entry><Binary><Key>name</Key><Value Ref="2"/></Binary>` — the
     `<Binary>` nodes are **direct children of `<Entry>`**. `kp.binaries` is a **list** in
     4.2.0, indexed by the int in `Ref`. A `<Binary>` placed inside an `<Attachments>`
     container is invisible to `Entry.attachments` even though the XML looks plausible —
     when attachments "disappear", print `[c.tag for c in entry._element]`.
   - To duplicate an attachment between entries, **deep-copy the XML node** onto the
     target `<Entry>`, keeping its `Ref` so it points at the same binary. Do not re-add
     data you just read back — see the first bullet above for why that lands the raw
     private key in the XML.
   - `kp.trash_entry(e)` routes through the recycle bin (see pitfall 9).
14. **Never restate a secret's value in a new store when an existing bootstrap variable
   already holds it.** If the user names a passphrase that equals an already-registered
   credential ("the classic password"), resolve it from its registered source (e.g.
   `.env` `SUDO_PASSWORD`) via variable reference — do not echo, log, or copy the literal
   into commands, files, or replies; process listings and shell history leak it.
15. **`Entry.save_history()` must run on the target entry, before the overwrite.** It
   deep-archives `self._element`; calling it on a detached clone raises `'NoneType'
   object has no attribute '_encode_time'`, the history write is skipped, and the losing
   side's state is silently destroyed while the merge appears to succeed. If the history
   call throws, treat the merge as unsafe — surface it rather than proceeding. Order is
   `le.save_history()` → then mutate fields.
16. **UUID match does not lift the per-group title-uniqueness constraint.** Two dbs can
   hold the same title under different UUIDs; `add_entry` then raises
   `An entry "<title>" already exists in "<group>"` and aborts the run mid-batch. Index
   local entries by `(group_path, title)` before adding and LWW-merge on a hit instead of
   duplicating. Handle it on BOTH sides — a twin-fallback added only to the pull side
   still blows up on push (`An entry ... already exists`) the moment a matching sibling
   exists container-side.
17. **Never "unify" same-title twins by deleting one copy — relink the UUID instead.**
   Deleting the local copy to "keep the container identity" removes the credential from
   the local db while the container copy keeps its own UUID, so the local entry's
   fields/attachments are simply gone (<host-01>/<nas-host>/<router-host> SSH private keys were lost this way
   and only recovered from a pre-write backup). The correct move is
   `e.uuid = UUID(container_uuid)` + `kp.save()`, which preserves every field, attachment
   and the history of the local entry while making the two sides match 1:1. Always take
   a backup copy first and re-open the db in a NEW process to verify — an in-process
   verify reuses the same object graph and reports false success (a `plan` dict keyed
   by `id(entry)` is likewise invalidated by pykeepass re-wrapping entries per
   iteration: key by `str(uuid)` instead).
   ⚠️ **Exception — schema-violating duplicates get hard-deleted, not relinked.**
   One entry per system is the rule; when a second entry with a *different title*
   duplicates the same system's role (a stray `SomeTool (PAT …)` beside the canonical
   `SomeTool - <system>` entry), relinking would merge two roles into one identity.
   Fold any unique attributes into the keeper entry first, then remove every copy
   including recycle-bin corpses — `find_entries(title=…, first=False)` returns
   live AND binned entries in one pass; `parent._element.remove(e._element)` for
   each (hard delete, never `trash_entry`). Verify in a fresh process: the duplicate
   count is 0 AND the keeper still carries the full attribute set. Corpses left
   behind resurrect on the next sync (pitfall 9) and multiply.
18. **"Content identical" must include attachments and attribute *values*, not counts.**
   Two entries with equal username/password/url and the same attribute-key set can still
   differ in what matters — one carries a signing private key the other lacks. Compare
   `tuple(sorted(a.filename for a in e.attachments))` and the full custom-properties
   items, and when they differ, report the field-level diff to the user instead of
   auto-merging; the entry missing an attachment is usually the incomplete one, not the
   stale one.
19. **Same-`mtime` on many unrelated entries is a fingerprint of a bulk merge, not of
   independent edits.** Several entries all carrying the same timestamp means a single
   sync/KeeShare import wrote them together — do not treat each as a fresh human edit
   (or use it as LWW evidence of recency) without checking whether the timestamps are
   identical.

20. **An entry's Password may be EMPTY while a naive XML read prints a plausible value.**
   An empty protected value renders as the self-closing tag `<Value
   ProtectInMemory="True"/>`; a regex of the form
   `<Key>Password</Key><Value[^>]*>(.*?)</Value>` then captures content lying AFTER
   that tag (a later element's body) and reports a fake nonzero length. Detect
   emptiness from the tag itself: the element matches `<Value[^>]*/>` (self-closing)
   or `><` (empty pair). A self-closing protected value is the signature of pitfall 1
   (`add` without `-p`) or of a sync container that never carried the value. The XML
   round-trip remains the value-check path (KeePassXC CLI section) — this pitfall is
   about reading that XML correctly; never infer credential validity from `show`
   output alone, live-test the endpoint.

21. **Existence checks must match the attribute that carries the credential, never a
   fuzzy title substring.** A PAT lives in a *custom attribute* of a service entry
   (`Gitea - <nas-host>` → `<pat-attribute>`). Searching by
   `'Gitea <gitea-host>' in e.title` returns **zero** while the credential sits intact, because
   that string belongs to old schema-violating duplicates, not the canonical entry. The
   resulting "the credential is gone" alarm is self-inflicted. Correct probe: iterate
   entries and test `custom_properties` keys for the exact attribute name, then live-test
   the endpoint. Cross-check BOTH dbs before declaring anything missing (pitfall 12).

22. **`Entry.path` has NO leading slash — `startswith('/Sync/')` matches nothing.** It is
   a list of group names; join it (`'/'.join(e.path)`) and compare against `'Sync/'`,
   `'Recycle Bin/'`. Measured consequence: a scope audit reported `Sync/** = 0` when the
   true count was 673, which reads as "the database structure changed" and sends you
   diagnosing a nonexistent incident. Same class of bug as pitfall 8's list-vs-string
   confusion — always sanity-check a zero result against an expected non-zero baseline
   before believing it.

23. **A service's keys belong in ONE entry as named attributes — scattered per-key
   entries are a schema violation to be merged, and the merge target is the entry whose
   attributes already match the live service.** The correct shape for an object store is
   a single service entry holding `AccessKeyId_<role>` / `SecretAccessKey_<role>` pairs
   plus endpoint/bucket, never one entry per key with the secret in the Password field.
   Two failure modes ride together here:
   - **Naming vs role drift.** Attribute suffixes drift out of sync with the names the
     service actually uses (`_rw` holding the key the server calls `nix-rw`; `_ro`
     holding a generation the server has never heard of while the true read-only key
     lives only in a scattered entry). Do not trust the suffix — map each attribute
     value to the **server's** key list by exact comparison and rename/extend from that.
   - **A stale-but-right-length value looks fine.** An attribute can hold a value that
     is the correct *shape* but a dead *generation*; only an exact comparison against
     the authority distinguishes them. Derive the truth from the service itself
     (`<tool> key list` + `key info --show-secret`), and cross-check against a live
     consumer's config (e.g. an `~/.aws/credentials` profile or a kv file on a machine
     that actually authenticates) — a consumer disagreeing with the vault means the
     vault entry is stale.

   Order that survives the operation: **inventory both dbs and the server into one
   table (location → value hash) → fix values/attributes → delete scatter → verify in a
   fresh process that every attribute equals server truth AND equals the other db's
   copy → check no consumer reads the entries by title before deleting them.** Deleting
   a scattered entry can break a consumer that reads it by path; grep the fleet for both
   the entry title and the attribute names first. Attributes are usually the stable
   interface (`read`/`write` by attribute name in automation) even when the entries
   carrying them are redundant — keep attribute names, correct their values.

24. **A shared kdbx on a network share can be rewritten by an unseen writer ~15–25 s
   after your write — verify against the server, and treat a revert as an external
   actor, not a bug in your code.** On CIFS/SMB the client cache is not the evidence:
   compare the sha256 on the *server* path after the write and again a minute later. A
   file that matches at T+1s and differs by T+15s with no process holding it locally
   means another device or service owns a copy. Fingerprints worth capturing before
   concluding anything: the server-side `nlink` (a second link under a recycle/`#recycle`
   tree is Synology's atomic-write temp file), the size sequence across reverts (differing
   byte counts for the same logical content = a process re-serialising its own in-memory
   copy), and `lsof`/`fuser` on both the client and the server side. Do **not** respond by
   writing in a loop — repeated clobbering corrupts the store. Report the writer and stop.
   Ordering note: check the sync cron's schedule before writing `Sync/**` at all; a write
   landing inside the cron's window will be merged by it mid-flight.

## References

- `references/ssh-key-domain-model.md` — SSH fleet/kin/external key domains, vault placement, config block
- `references/env-variable-extraction.md` — Reading .env variables safely
- `references/session-token-extraction.md` — Token/cookie extraction from browsers
- `references/gpg-credential-edit-workflow.md` — GPG YAML edit cycle (archive/legacy backend)
- `references/fleet-git-credential-helper.md` — Non-interactive git auth from the vault
- `references/keepass-declarative-interface.md` — KeePassXC ↔ Guix/Nix boundary: value classes inside one entry, reference-by-path resolver (Pattern A, fleet standard), rejected build-time injection (B), topology-embedding drift rule (C), per-entry schema cheat-sheet, pykeepass read-only recipes
- `scripts/keepass-query.sh` — KeePass lookup helper
- `scripts/verify-kdbx-write.py` — **mandatory post-write assertion suite** (run it in a fresh process after ANY scripted kdbx write): entry count, the `(total, nonzero, bytes)` attachment triple, duplicate-filename detection, and baseline regression / wipe-fuse checks. Exits non-zero on damage; prints attribute values as length+hash only
