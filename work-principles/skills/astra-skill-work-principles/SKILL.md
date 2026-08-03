---
name: work-principles
description: >
  Agentic Harness — phase-based gates and tool-triggered auto-loading.
  Replaces the old execution-framework routing with a plug-based approach.
  This skill provides the architectural overview; enforcement is handled
  by the plugin hooks.
category: devops
version: 3.0.0
metadata:
  hermes:
    tags: [work-principles, harness, discipline, phase-gate, agentic-harness]
triggers:
  - "agentic harness"
  - "discipline phase gate"
  - "work principles"
  - "phase gate blocked"
  - "HARNESS marker"
  - "tool triggered skill loading"
---

# work-principles — Agentic Harness

> **This is the core of the astra agentic harness.**  Behavioural constraint
> is no longer driven by prompts or routing tables — it is enforced at the
> plugin level via five phase-specific gates.

## Architecture

```
                    ┌──────────────────────┐
                    │   [HARNESS:] markers  │
                    │  agent self-classifies │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   task_started        │
                    │   Research Gate       │ 🔒 调研工具 + 只读终端
                    └──────────┬───────────┘
                               │ [HARNESS: plan]
                    ┌──────────▼───────────┐
                    │   planning            │
                    │   Proposal Gate       │ 👥 写 todo + 等批准
                    └──────────┬───────────┘
                               │ user approves
                    ┌──────────▼───────────┐
                    │   executing           │
                    │   Discipline Reminder │ 🪧 提醒注入 (无硬锁)
                    └──────────┬───────────┘
                               │ need write
                    ┌──────────▼───────────┐
                    │   modifying           │
                    │   Modify Gate         │ 🔒 change-safeguard
                    │                       │ 🪧 skill-creator 提醒
                    │                       │ 🪧 credential 提醒
                    └──────────┬───────────┘
                               │ task done
                    ┌──────────▼───────────┐
                    │   closing             │
                    │   Closure Gate        │ 🔒 仅 [HARNESS: done] 可退
                    │                       │ 📋 7 步 checklist 注入
                    └──────────────────────┘
```

### Gate strength levels

| Level | Behaviour | Applied to |
|:------|:----------|:-----------|
| 🔒 Hard lock | Tool blocked until phase/release condition met | Research Gate, Modify Gate, Closure Gate |
| 👥 Social | Not code-blocked — user approval required | Proposal Gate (wait for "可以"/"开干") |
| 🪧 Reminder | Context injected, no blocking | Executing phase reminders |
| 📋 Checklist | Complete checklist injected, must acknowledge | Closure checklist |

### [HARNESS:] marker system

Agent includes these in **text responses** to trigger phase transitions.
Markers are detected exclusively from the assistant's own final response
(`post_llm_call` hook) — **never** from tool outputs (file reads, search
results, etc.), so reading plugin source or history containing the marker
text cannot cause false transitions.

**CRITICAL — marker must be in a pure-text turn, alone.**
`post_llm_call` fires only at turn end with `final_response` = the final
text of a turn with NO tool calls (Hermes `conversation_loop` keeps looping
while the model emits tool_calls; intermediate text inside a tool-calling
turn is NOT the final response and is never scanned). Therefore:

- ❌ Wrong: `[HARNESS: plan]` + `write_file` in the same message — the marker
  lives in an intermediate tool-calling turn, is never detected, and the
  Research Gate stays locked (agent then misreads it as "gate broken").
- ✅ Correct: send `[HARNESS: plan]` as a **standalone text-only message**
  (no tool calls). Hermes finalises the turn, `post_llm_call` detects the
  marker → phase planning + Research Gate cleared. Then write in the next turn.

Same applies to `[HARNESS: task_started]`, `[HARNESS: casual]`,
`[HARNESS: done]` — all must be pure-text turns.

| Marker | Meaning | Phase transition |
|:-------|:--------|:----------------|
| `[HARNESS: task_started]` | This is a real task | Enter task_started + activate Research Gate |
| `[HARNESS: plan]` | Research done, here is my plan | Enter planning + clear Research Gate |
| `[HARNESS: casual]` | Just chatting | Reset to no_task |
| `[HARNESS: done]` | Closure complete | Enter closing (only way to exit closing) |

In CLOSING phase, only `[HARNESS: done]` is accepted — other markers are
rejected and trigger a bypass warning.

### Session isolation

Every hook receives `session_id=agent.session_id` from Hermes and threads
it through all state operations.  State files are per-session
(`state_{session_id}.json`); the process-global `HERMES_SESSION_ID` env
var is only a fallback for session-less callers (e.g. cron) and is never
used for isolation.

### Tool-triggered auto-skill loading

| Agent uses... | Auto-loads... |
|:--------------|:--------------|
| `browser_navigate` / `browser_click` | `camofox-browser` |
| `skill_manage(create/edit/patch)` | `skill-creator` |
| terminal(gpg/password-store/keepass) | `credential-store-management` |
| SSH command | Auto-transition to `accessing_device` + credential reminder |

### Read-only terminal command whitelist

During research (Research Gate active) or closing (Closure Gate active),
only read-only terminal commands are allowed:

```
cat, ls, head, tail, grep, find, stat, df, du, ps, which,
systemctl status, journalctl, docker ps, podman ps,
curl -I, wget --spider, dig, nslookup, ip addr,
git status, git log, git diff, nvidia-smi, ...
```

Additionally, `git/docker/podman/systemctl` subcommands are filtered:
`git push/commit/merge/reset` are blocked; `git status/log/diff` are
allowed.

## Related Skills

| Skill | Purpose | Interaction |
|:------|:--------|:------------|
| `pre-action-research` | Research and investigation | Research Gate suggests loading it |
| `change-safeguard` | Pre-change backup checklist | Modify Gate suggests loading it |
| `work-closure-check` | Closure checklist (7 steps) | Closure Gate injects its content |
| `credential-store-management` | GPG/Keepass credential access | Tool-triggered auto-load |
| `skill-creator` | Frontmatter validation | Tool-triggered auto-load |
| `camofox-browser` | VNC/anti-detection browser | Tool-triggered auto-load |
| `execution-framework` | Manual recommendation tool | Optional, no longer required |

## What Changed

- **Execution-framework routing removed** — The `acknowledge_execution_framework`
  tool, the `recommend_steps.json` injection, and the SOUL.md §0.2 self-call
  instruction are all gone.
- **SOUL.md simplified to identity-only** — No workflow, no routing, no
  recommend.py instruction.  Pure identity (Honest, Skill-first, 安全第一).
- **recommend.py downgraded to manual** — Optional keyword-based debugging
  tool, not part of the harness.
