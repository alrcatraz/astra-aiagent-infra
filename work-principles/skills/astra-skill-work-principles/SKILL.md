---
name: work-principles
description: >-
  Reference playbook for the work principles declared in SOUL.md.
  Enforcement is handled by the work-principles plugin (hooks + phase
  state machine). This skill provides the detailed how-to and checklist
  for each discipline area. Bundled skills: skill_view("work-principles:<name>").
category: devops
version: 2.0.0
---

# work-principles — Work Discipline Coordination Layer

> Detailed playbook for the work principles declared in SOUL.md (identity layer,
> always in context). This skill provides the how-to: commands, checklists, and
> pitfalls. Related standalone skills (each keeps its own SKILL.md):
> `pre-action-research`, `work-closure-check`, `deploy-register`,
> `change-safeguard`, `execution-framework`.

## Astra Component Development

### Dual-Copy Repo Pattern

Every Astra ecosystem component exists in two copies:

| Copy | Path | Purpose |
|:-----|:-----|:--------|
| **Dev copy** | `~/Projects/astra/<repo>/` | Git working tree — push to GitHub. MUST be sanitised (no personal info, local paths, API keys). |
| **Private copy** | `~/.astra/repos/<repo>/` | Clone from GitHub (or from dev copy pre-push). Hermes soft-links load from here. |

**Setup flow for a new component:**
1. Create repo at `~/Projects/astra/<repo>/` (dev copy)
2. Create GitHub repo and push (or defer if no token configured)
3. Clone into `~/.astra/repos/<repo>/` (private copy)
4. Point Hermes symlink at the private copy
5. Register in `registry.yaml` under `astra-aiagent-infra/`

**Important:** Work-in-progress files that exist only locally (`work-principles/`, uncommitted refactors) — copy from dev to private copy manually and update symlinks. Do not leave Hermes loading from dev copies in `~/Projects/`.

### Plugin Override Pattern

Replacing a built-in Hermes tool requires:
1. `ctx.register_tool(name="<tool_name>", override=True)` in the plugin
2. `ctx.dispatch_tool()` injected via closure for calling other tools from handlers
3. `hermes plugins enable <name> --allow-tool-override` — the override flag is mandatory
4. Plugin takes effect on next session (`/new` or restart)

Reference implementation: `astra-web-extract-markitdown` — overrides `web_extract` to dispatch through `mcp_markitdown_convert_to_markdown`.

### Component Audit Checklist

Before registering a new component (or auditing existing ones), verify against the [Module Development Guide](../docs/module-development-guide.md):

| Check | What to look for |
|:------|:-----------------|
| Badge bar | `badgen.net` or `img.shields.io` in README top section |
| Bilingual | Chinese translation after `---` divider in README |
| SKILL frontmatter | `name:`, `description:`, `version:`, `author:`, `platforms:` |
| LICENSE | MIT (or CC-BY-SA 4.0 for docs-only) |
| AGENTS.md | Present if module has CLI/API/MCP tools |
| routing.yaml | Present if skill needs auto-suggestion from execution-framework |
| registry entry | In `astra-aiagent-infra/registry.yaml` with correct type/version/status |
| Hub index | Listed in both public and private copies of `astra-hub/SKILL.md` |
| Version consistency | Registry version matches SKILL.md frontmatter |

## Cross-Cutting Principles

### 1. Approval Discipline

- **Propose first, then execute.** Diagnosis and action must never be merged into one step.
- **Explicit approval required.** "可以", "开干", "好" — approvals. Questions, corrections, or feedback are **not** implicit approval.
- **Old approval does not carry over.** When a plan changes, re-propose and wait for re-approval.
- **Documentation changes are not exempt.** README typos, badge URLs, wording — same rule.

### 2. Verify Before Reporting

Do not report "done" based on what you intended to do. Report based on what you **verified** happened.

- After every write/create/copy: read the file back
- After every delete: confirm `ls: cannot access`
- After testing a Hermes plugin: `grep plugin ~/.hermes/logs/agent.log` for errors
- After setting up a network mount: verify the mount and the target path
- **MoA references are suggestions, not facts.** Parallel-agent output claiming "file written" or "step completed" must be verified against real disk/tool state before you inherit it into your own report.
- **Partial progress ≠ done.** Say "X/Y substeps complete, Z pending" — never summarize partial work as "done ✓".
- **Verify claims against authoritative sources, not memory.** Before stating that content exists/doesn't exist in a specific location, consult the actual source: tutorial docs, config file, `ls` output, `cat` output. Memory is unreliable — especially for content destinations (\"where does X belong\") and repo names. **If the tutorial/source code shows a different picture than your memory, the source wins.**
  - Environment baselines → check `change-safeguard` skill (not pre-action-research)
  - Repo names → check actual GitHub listing, not casual labels
  - Content belonging → check the authoritative doc/registry, not your recollection

Recovery pattern when corrected twice on the same class of error:
1. Stop executing
2. Take a verification snapshot
3. List what is proven-done, pending, and uncertain
4. Ask for confirmation

### 3. No Unsolicited Artifacts

Do not create files, directories, symlinks, or other artifacts during an approved execution step unless they were part of the approved plan.

If execution reveals a need for something unplanned:
1. Pause the current step
2. State the new need and proposed approach
3. Wait for approval
4. Only then create the artifact

### 4. Destructive Minimalism — Prefer State Preservation Over Rebuild

**Before destroying and recreating anything (container, config, service), exhaust all non-destructive options first.**

When a container or service is in a crash-loop or broken state:
1. **Diagnose first** — read logs, inspect env vars, check mounted volumes, verify the node identity is preserved
2. **Minimal fix first** — environment variable correction, device/volume flag addition, network config change
3. **Understand root cause** — the crash loop may be a symptom of an upstream issue (firewall, proxy, DNS, misconfiguration)
4. **Preserve identity** — containers with persistent volumes (ZT identity, etc.) should never be destroyed without explicitly confirming the volume will be re-mounted to the new container
5. **Fresh container = last resort** — if you must recreate, mount the EXISTING persistent volume, do not generate a new node

This principle is especially important for:
- **ZeroTier/SD-WAN nodes** — identity (`identity.secret`) must be preserved or you must re-authorize on the controller
- **Docker containers with state** — databases, service configs, auth tokens
- **Network devices** — SSH keys, routing configs, firewall rules

Signal the user proposed a non-destructive path where you were about to do something destructive: stop, acknowledge, and adopt the better approach.

## Enforcement Architecture — Plugin Layer

> **Critical design lesson (2026-07-05):** Skills are **on-demand** — the system prompt's
> relevance matching does NOT force-load meta-skills. Relying on skill-loading for
> enforcement is fundamentally wrong. Enforcement requires **hook-level** interception
> that runs every LLM turn regardless of what the agent "remembers" to do.

The `work-principles` Hermes plugin (at `plugin/` within this skill directory,
symlinked to `~/.hermes/plugins/work-principles`) provides the enforcement
layer. This skill provides the detailed reference. They are complementary:

```
work-principles plugin (hooks — always-on enforcement)
  ├─ pre_llm_call  → injects phase context into EVERY LLM turn
  ├─ post_tool_call → auto-detects phase transitions
  ├─ on_session_start → initialises phase to no_task
  └─ discipline_set_phase (custom tool) → agent declares transitions
       │
       ▼
Bundled skills (this, pre-action-research, change-safeguard, work-closure-check)
  └─ loaded via skill_view("work-principles:<name>") when agent needs detail
```

**Phase state machine:**

| Phase | Type | Injection | Description |
|:------|:-----|:----------|:------------|
| `no_task` | Steady | ❌ Silent | Idle / small talk |
| `task_started` | Transient | ✅ | Research, check docs, propose plan |
| `planning` | Transient | ✅ | Consult preferences, show trade-offs, wait for approval |
| `accessing_device` | Temp | ✅ | Check GPG credential store. Return to prior phase after. |
| `executing` | Steady | ❌ Silent | Executing approved plan |
| `modifying` | Temp | ✅ | Back up first, verify each step. Return to executing after. |
| `closing` | Transient | ✅ | Credential scan, skill update, decision record |

**Temp phases** leave the main workflow to handle a specific need, then return
to the prior steady phase. Agent calls `discipline_set_phase` to return;
`post_tool_call` auto-detects only `executing→modifying` (via `write_file`/`patch`).

Full design rationale in references/plugin-enforcement-architecture.md.

**This is NOT a catch-all umbrella.** The skills listed under Related Skills keep their own independent SKILL.md files in `~/.hermes/skills/devops/`. "Related" means they coordinate with work-principles at workflow level; it does not mean their content lives here.

## Pre-Flight: Session Context Anchoring

Before any action that targets or depends on a specific machine:

1. **Resolve current identity** — Run `hostname` to identify the machine.
   Cross-reference against known host ↔ IP ↔ overlay mappings
   (refer to `infrastructure-device-inventory` for full device table).
2. **Determine connection method** — Is this SSH, local terminal, tmux, or
   gateway? Use `env | grep -E '(SSH|TMUX|HERMES)'` and `ip -br addr`.
3. **Check credential availability** — Verify GPG credential store is
   accessible before asking the user for any password:
   ```bash
   ls ~/Documents/credentials/*.gpg 2>/dev/null
   ```
   (Full protocol in `credential-store-management` skill.)
4. **Context-anchor** — If the task references a specific device (NAS, router,
   VPS), confirm you are on the right machine or SSH to it first.
5. **Load domain skill** — If the task type has a governing skill
   (pre-action-research for investigation, change-safeguard for modifications,
   work-closure-check for wrap-up), load it now.

## Related Skills

These skills coordinate with work-principles at the workflow level.
Each lives as an independent SKILL.md under `~/.hermes/skills/devops/` — they
are NOT absorbed into this directory (that would require actual file migration
per `skill-structure-convention`'s consolidation workflow):

| Skill | Purpose |
|:------|:--------|
| `pre-action-research` | Information gathering — credentials, docs, indexes |
| `work-closure-check` | End-of-task checklist — credential scan, skill updates, storage |
| `deploy-register` | Service registration after deployment |
