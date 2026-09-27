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
| `[HARNESS: task_started]` | This is a real task | Enter task_started + activate Research Gate (mutation-only). If mid-work (executing/modifying/planning…), the current phase is **suspended** (branch-task support) and resumed after closure. |
| `[HARNESS: plan]` | Research done, here is my plan | Enter planning + clear Research Gate. Mid-work plan also suspends the current phase. |
| `[HARNESS: casual]` | Just chatting | Reset to no_task, drop suspended stack |
| `[HARNESS: done]` | Task complete | Enter closing (checkpoint). A second `done` **confirms closure**: resume the suspended task (if any) or archive to no_task. |

**Marker turns must be cheap and never bare.** A marker-only turn carries at
most one short sentence plus the marker — and `[HARNESS: task_started]` in
particular belongs on the SAME turn the task is recognised, before that turn's
research calls let auto-detect lock the gate behind your back. Never end a
marker turn having done nothing else visible: two consecutive user-visible
stops at `task_started` reads as "the harness is broken" and burns a debugging
cycle on the agent's own cadence.

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

The shared classifier behind all gates:

```
cat, ls, head, tail, grep, find, stat, df, du, ps, which,
systemctl status, journalctl, docker ps, podman ps,
curl -I, wget --spider, dig, nslookup, ip addr,
git status, git log, git diff, nvidia-smi, ...
```

Additionally, `git/docker/podman/systemctl` subcommands are filtered:
`git push/commit/merge/reset` are blocked; `git status/log/diff` are allowed.

**Compound commands defeat the classifier — write them single-purpose during
gated phases.** Only the FIRST command of a chain/pipeline is inspected, so
`cd dir && git status` or `cmd | head -40` classify as mutating and get
blocked. Use `git -C <dir> status` instead of cd-chains, and read_file /
search_files / execute_code (stdlib-only analysis) instead of shell pipelines.

**Known false-block shapes (audit 2026-09-23, still unfixed in hooks.py):**
`curl` GET is treated as mutating unless it uses `-I/--head`; `sleep N` is
not on the whitelist; `VAR=$(grep …)` env-prefix assignments are stripped but
the following command is then re-checked from scratch (`gpg --decrypt` still
judged mutating); wrapper scripts like `bash /tmp/x.sh '<url>'` always fail
classification. During research-pending, prefer web_search/web_extract over
curl GET, and submit `[HARNESS: plan]` early if you will touch files or skills.

### Remote-access gate

`ssh host 'tail log'`, scp pull and rsync pull pass in modifying/planning/
closing without declaring `accessing_device` — the remote command half is
judged by the same read-only classifier. Anything WRITING to a remote device
(scp/rsync push, remote rm/mkdir, bare interactive ssh) still requires the
explicit phase. When extending this logic keep paired positive AND negative
test cases per command shape — allow-list drift is silent.

## Proposal Gate 的「方案正文」标准（2026-09-23 用户两次纠正）

Proposal Gate 👥 不只是"等一句可以"——待批物必须是**方案正文本身**，不是摘要或预告：

- 用户说「给我看方案/计划」时 = 把将要落盘的完整内容（文档全文、diff 清单、逐项表格）直接贴在回复里审阅；只报"我打算写个 XX 模型"不算方案。
- 审批未过前不得进入下一步（包括建文件、commit、改技能）。口头讨论定案 ≠ 入库许可；"行，继续"批准的是**当时展示的那一版**，中途扩写的内容须重新过目。
- 抽象/泛化类方案先确认适用范围再动笔（例：塔模型本意=所有项目通用，写成"仅 fork"会被打回——范围偏差本身就是方案缺陷）。

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

- **Research gate → "reach, don't enter" (2026-09-18)** — While a plan is
  pending only *state-changing* tools are blocked (`write_file`, `patch`,
  `skill_manage`, mutating terminal commands, `delegate_task`, browser
  mutations…); every investigation tool and read-only command passes freely.
  The old whitelist frisked each call and dead-ended legitimate research until
  the only exit was falsely claiming `[HARNESS: plan]`. The user's approval at
  planning is the primary gate; code locks are the last resort.
- **Gate relaxations from audit data (2026-09-18)** — `accessing_device` now
  permits local file writes (was the largest false-block source); read-only
  remote inspection passes in work phases; `execute_code` allowed in closing
  for checklist stats. Implementation lives in
  `~/.astra/repos/astra-aiagent-infra/work-principles/plugin/discipline/hooks.py`
  with paired positive/negative cases in `plugin/tests/test_harness_integration.py`
  — run that suite after ANY hooks.py change
  (`python3 tests/test_harness_integration.py`).
- **Execution-framework routing removed** — The `acknowledge_execution_framework`
  tool, the `recommend_steps.json` injection, and the SOUL.md §0.2 self-call
  instruction are all gone.
- **SOUL.md simplified to identity-only** — No workflow, no routing, no
  recommend.py instruction.  Pure identity (Honest, Skill-first, 安全第一).
- **recommend.py downgraded to manual** — Optional keyword-based debugging
  tool, not part of the harness.
