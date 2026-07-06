# Plugin Enforcement Architecture

> Origin session: 2026-07-05 — work-principles enforcement redesign
> Problem: Skills are on-demand (system prompt relevance matching), so a
> "load me for every task" skill is fundamentally unenforceable.

## The Problem

The system prompt says:

> *"Before replying, scan the skills below. If one clearly matches your task,
> load it with skill_view(name) and follow its instructions."*

This is **relevance matching** — not mandatory loading. A meta-skill like
`work-principles` that applies to *every* task is never the top match for any
*specific* task. Result: the agent doesn't load it unless explicitly told to.

## The Solution: Plugin Hooks

Hermes plugins support lifecycle hooks that fire on **every** LLM turn,
regardless of what the agent decides to load or not load. The enforcement
chain is:

```
work-principles plugin

  Location: plugin/ within the work-principles skill directory
  Symlink:  ~/.hermes/plugins/work-principles → plugin/
  Plugin name in plugin.yaml: work-principles

  Hooks:
  ├─ on_session_start:    initialises phase = no_task
  ├─ pre_llm_call:        injects phase context into EVERY user message
  │   └─ Returns {"context": "...phase reminder..."} unless phase is
  │      no_task/executing (steady states — silent)
  ├─ pre_tool_call:       BLOCKS out-of-phase tool use
  │   ├─ write_file/patch   → blocked unless phase in {modifying, planning, closing}
  │   └─ terminal(ssh/...)  → blocked unless phase in {accessing_device, planning, modifying, closing}
  ├─ post_tool_call:      auto-detects phase transitions
  │   └─ write_file/patch during executing → auto-transition to modifying
  └─ discipline_set_phase: custom tool agent calls to declare transitions
      └─ schema: {phase: str, reason: str}
```

## Phase State Machine

### Steady States (no injection — agent works undisturbed)

| Phase | Meaning |
|:------|:--------|
| `no_task` | Idle, small talk, no active work |
| `executing` | Executing an approved plan, routine work |

### Transient States (inject phase-appropriate guidance)

| Phase | Meaning | Injection content |
|:------|:--------|:------------------|
| `task_started` | New task detected — need research | Research first, check docs, propose plan |
| `planning` | Research done — need to formulate plan | Consult preferences, show trade-offs, wait for approval |
| `closing` | Task complete — need wrap-up checks | Credential scan, skill update, decision record |

### Temporary States (leave main workflow, then return)

| Phase | Meaning | Injection content |
|:------|:--------|:------------------|
| `accessing_device` | Need credentials | Check GPG store, save new credentials, return to prior phase |
| `modifying` | About to change files | Back up first, verify each step, check identical patterns elsewhere |

**Key rule:** The agent calls `discipline_set_phase` to transition between
phases. The plugin only auto-detects `executing→modifying` (via `write_file`
or `patch` tool calls). All other transitions are agent-driven.

## Bundled Skills

The plugin ships 5 skills accessible as `work-principles:<name>`:

| Skill name | Namespaced path | Purpose |
|:-----------|:----------------|:--------|
| work-principles | `work-principles:work-principles` | Full work discipline playbook |
| pre-action-research | `work-principles:pre-action-research` | Pre-task research protocol |
| change-safeguard | `work-principles:change-safeguard` | Change backup & verification |
| work-closure-check | `work-principles:work-closure-check` | Task closure checklist |
| credential-store-management | `work-principles:credential-store-management` | GPG/KeePass credential access protocol |

Loaded via `skill_view("work-principles:<name>")` when the agent needs detailed
procedure for the current phase.

## Design Boundaries

1. **Plugin lives inside the work-principles skill** — it is not a separate
   component. The plugin code is at `work-principles/plugin/` and exposed via
   a symlink in `~/.hermes/plugins/`. This keeps the enforcement mechanism
   bundled with the discipline playbook.

2. **Plugin does not make decisions** — it only tracks phase and injects
   reminders / blocks out-of-phase tools. The agent judges which phase it's in
   and calls `discipline_set_phase` accordingly.

3. **Auto-detection is minimal** — only `write_file`/`patch` during
   `executing` auto-triggers `modifying`. Credential access is too
   ambiguous to auto-detect reliably — agent must declare it.

4. **`no_task` and `executing` are silent** — these are the "doing work"
   phases where injection would be noise. Injection only fires when the
   agent explicitly wants guidance (transient/temp phases).

5. **State persists across `/new`** — state.json lives in
   `~/.hermes/persistent/`, which Hermes auto-restores across session
   resets. Phase resets to `no_task` on `on_session_start`.

## SOUL.md vs Skills vs Plugins — Architecture Rule

| Layer | Purpose | Always in context? |
|:------|:--------|:------------------|
| **SOUL.md** | Identity, persona, communication style | ✅ Layer 1 |
| **Memory** | Small factual facts about environment | ✅ Layer 5 |
| **User profile** | Who the user is, preferences | ✅ Layer 6 |
| **Skills** | Procedural how-to, loaded on demand | ❌ Relevance matching |
| **Plugins** | Enforcement via hooks (always-on) | ✅ Hook-level |

**Rule:** Procedures and workflow enforcement NEVER go in SOUL.md. SOUL.md is
for "how you speak" not "how you work." Workflows belong in skills (reference)
and plugins (enforcement). If the user says "don't put that in SOUL.md,"
they are citing Hermes' architecture — respect it.
