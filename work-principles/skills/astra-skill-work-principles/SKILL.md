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
                    │                       │ 🪧 skill-ecosystem 提醒
                    │                       │ 🪧 credential 提醒
                    └──────────┬───────────┘
                               │ task done
                    ┌──────────▼───────────┐
                    │   closing             │
                    │   Closure Gate        │ 🔒 检查点非死胡同
                    │                       │ 📋 7 步 checklist 注入
                    │                       │ → done/plan/task_started/casual 可退
                    └──────────────────────┘
```

### Gate strength levels

| Level | Behaviour | Applied to |
|:------|:----------|:-----------|
| 🔒 Hard lock | Tool blocked until phase/release condition met | Modify Gate, Closure Gate, Research Gate (mutation-only — "reach, don't enter") |
| 👥 Social | Not code-blocked — user approval required | Proposal Gate (wait for "可以"/"开干") — **the primary gate of the whole flow** |
| 🪧 Reminder | Context injected, no blocking | Executing phase reminders |
| 📋 Checklist | Complete checklist injected, must acknowledge | Closure checklist |

**Design principle (reaffirmed 2026-09-18):** code locks are a last resort.
The research gate blocks only *state-changing* tools while a plan is pending;
any investigation tool or read-only command passes freely. The old whitelist
model frisked every call and produced dead-ends whose only exit was falsely
claiming `[HARNESS: plan]`.

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
| `[HARNESS: task_started]` | This is a real task | Enter task_started + activate Research Gate. If mid-work (executing/modifying/planning…), the current phase is **suspended** (branch-task support) and resumed after closure. |
| `[HARNESS: plan]` | Research done, here is my plan | Enter planning + clear Research Gate. Mid-work plan also suspends the current phase. |
| `[HARNESS: casual]` | Just chatting | Reset to no_task, drop suspended stack |
| `[HARNESS: done]` | Task complete | Enter closing (checkpoint). A second `done` **confirms closure**: resume the suspended task (if any) or archive to no_task. |

**CLOSING is a checkpoint, not a dead end.** After running the closure
checklist, all four markers are legal exits:
- `[HARNESS: done]` → confirm closure → resume suspended task / archive
- `[HARNESS: plan]` → continue to next planning phase
- `[HARNESS: task_started]` → start a new task
- `[HARNESS: casual]` → back to idle

**Branch tasks**: a `task_started`/`plan` marker arriving mid-work (e.g.
while executing) pushes the current phase onto a `suspended` stack; the
next `done` confirmation pops it and resumes the main task. `casual`
drops the stack.

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
| `skill_manage(create/edit/patch)` | `skill-ecosystem` |
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

## Progress reporting cadence (hard rule)

用户两次纠正（2026-08「是你一次次停下来」与 2026-09「你一直不和我报告进展」）合并为一条纪律：

- **执行中每 3–4 个工具调用，必须输出一句进度旁白**（刚做完什么 + 接下来做什么），即使该轮仍在调用工具。纯工具沉默超过 4 个连续调用 = 违规。
- 卡点/失败要**当轮主动说**，不要攒到收尾；被审批拦截的命令立刻讲清在等什么。
- 但**不要为汇报而停下**——旁白之后继续干活，持续到完成或真正的决策点才停等用户。
- 用户问「怎么样了 / 这是什么意思」时，当轮先答人话汇报再继续其它动作。

## Related Skills

| Skill | Purpose | Interaction |
|:------|:--------|:------------|
| `pre-action-research` | Research and investigation | Research Gate suggests loading it |
| `change-safeguard` | Pre-change backup checklist | Modify Gate suggests loading it |
| `work-closure-check` | Closure checklist (7 steps) | Closure Gate injects its content |
| `credential-store-management` | GPG/Keepass credential access | Tool-triggered auto-load |
| `skill-ecosystem` | Frontmatter validation | Tool-triggered auto-load |
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
