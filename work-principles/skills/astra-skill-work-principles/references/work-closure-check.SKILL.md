---
name: work-closure-check
description: "Mandatory closure checklist when wrapping up a task: confirm success, clean temporary files, evaluate skill/documentation updates, verify information storage."
version: 1.1.0+local.1
author: alrcatraz
platforms: [linux]
---

# Work Closure Check

> Enforcement of the closure discipline. When a task transitions from execution to wrap-up, **this skill must be loaded first** to run the systematic checks before notifying the user to confirm success.

## Trigger Keywords

This skill is automatically loaded when the task involves:
- Wrapping up, finishing, summarising, cleaning up, ending
- Verifying, testing, delivering
- "Can you check if it's done", "confirm success"

Also triggered by: 收尾、完成、总结、清理、结束、验证完、测试完、交付、确认成功

> **Routing:** Prefer loading `execution-framework` first; it will route here when the task involves closure.

## Checklist (execute in order)

### ① Credential Leak Scan

**——Did this task involve any credentials (passwords, tokens, API keys, SSH private keys)?**

If yes → check the following locations for plaintext residuals:

| Location | Pass criterion | Violation action |
|:---------|:---------------|:-----------------|
| **Memory** (memory tool) | No passwords/tokens/private keys | Delete immediately, replace with `→secure store` reference |
| **Terminal output** (session history) | No credentials exposed in command arguments | If already exposed, inform the user of the risk |
| **Skill content** | No hardcoded credentials | Move to encrypted storage |
| **File residuals** (temp scripts, config backups) | No credential-containing temp files | Delete or sanitise sensitive fields |

**Core principle:** Credentials must never be stored in memory. All passwords/tokens live only in their designated encrypted storage; memory holds only references.

If none or cleaned → proceed.

### ② Skill Update Check

**——Does this session contain any notable problems, workflows, or techniques worth recording?**

Ask each:

> **对公开仓库的特别检查：** 如果本次任务涉及 `~/Projects/astra/<repo>` 或任何可能推送到 GitHub 的仓库，在考虑技能更新之前，先检查是否需要执行 **repo 脱敏和公私拆分**（参见 `oss-publication` skill）。具体信号：
> - 仓库中包含 `config/devices.yaml` 或类似设备清单
> - 仓库中有环境专属脚本（E2EE 诊断、VPS 恢复等）
> - 仓库引用了你的个人 Hermes skill 名
> - 离最近一次推送到 GitHub 已经过了一段时间
>
> 如果上述任意条为「是」，先处理脱敏和私有副本再继续。推送到 GitHub 后的干净仓库不应包含个人数据。

**——本次有没有值得记录的特定问题、workflow 或 technique？**

逐一问：

| 问题 | 如果"是" |
|:----|:---------|
| 是否解决了值得记录的特定问题？ | **存为新 skill** |
| 是否发现已有 skill 过时、有坑、缺步骤？ | **立即 patch** 该 skill |
| 是否发现一个 class-level 的模式值得抽象？ | 创建 class-level 的 umbrella skill |
| 是否有 session-specific 的细节值得存档？ | 在现有 skill 的 `references/` 下加参考文件 |
| 是否有 **Ecosystem Hooks** 需要处理？（见下方自动生成章节） | 运行 `astra-lifecycle-sync --check` 查看待办 |

**优先级规则：Skills first, memory second.**

在记录任何信息之前，按此顺序判断去向：

```
有具体命令/步骤/判断条件/验证方法？
  ├─ 是 → 已有相关 umbrella skill？ → patch 它
  │             └─ 没有？ → 创建 class-level skill
  └─ 否 → 是稳定事实/偏好/环境信息？
       └─ 是 → 存 memory
       └─ 否 → 不存（task progress、session 产物不记）
```

**快速判断：**
- "这是个可复用的排查/修复/配置流程" → **skill**（哪怕只有几行命令）
- "这是用户叫什么/项目用什么语言/某个 IP 是什么" → **memory**
- "我做了什么、做到哪一步了" → **都不存**（走 session_search 找回）

**命名原则：** 新 skill 必须是 class-level 名称，不能是具体 session 产物（`fix-something-today` ❌ → `fix-common-pattern` ✅）。

**Skill 结构原则（用户明确要求）：** 
- ✅ **Class-level umbrella skill** 一个丰富的 `SKILL.md` + `references/` 目录
- ❌ 不接受一长串扁平的、一次会话一个的窄 skill
- 发布新 skill 前先问：这个能抽象为 class-level 吗？还是一个 session 的产物？
- Session 特有的细节（错误日志、复现步骤、配置示例）应存入 `references/` 下，而非另建独立 skill

> 参考: SOUL.md §4.3, ecosystem lifecycle hooks (see [Ecosystem Hooks](#ecosystem-hooks) below)

### ③ 决策记录检查

——**本次有没有做了值得文档化的决策（"为什么选 A 不选 B"）？**

有 → 在相关的 skill 参考文档中记录（如有对应 Ecosystem Hook，检查下方自动生成章节）：

```markdown
## Decision Record (YYYY-MM-DD)
- **Context:** [problem description]
- **Options:** [A: approach / B: approach / C: approach]
- **Chosen:** [key trade-off]
- **Cost of rejected options:** [what was sacrificed]
```

> 例如: "用 IPMI SEL 而不是 Redfish EventLog — 因为 EventLog 可能空，SEL 才是硬件黑匣子"
>
> 参考: `references/dependency-convention.md` — astra 生态三层依赖标注约定（2026-06-18 确立）

### ④ Service/Device Registration Check

**——Was any new service, MCP, CLI tool, or device connected during this session?**

If yes → register accordingly:

| 对象 | 登记位置 |
|:----|:---------|
| 新服务 (MCP/CLI/HTTP) | 服务清单（本地参考索引 → 服务管理入口） |
| 新设备 (SSH可达) | 设备清单（本地参考索引 → 项目地图） |
| 新凭证分类 | 凭证存放规范（本地参考索引 → 凭证存放规范） |
| **Ecosystem-specific 部署** | 检查下方 Ecosystem Hooks 章节是否有对应 `deploy` 类型钩子 |

If none → proceed.

### ⑤ 信息存储检查

此阶段由 agent 根据自身可用工具动态执行。

**记录什么 → 记到哪里** → 完整决策树及层级说明见 `astra-hub` skill 的「🗂️ 信息存储层级」章节。
本地存储实例配置（KB 空间名、凭证路径等）见 `astra-hub/references/user-stores.md`。

> 快速摘要：流程→skill，配置→KB，偏好→Fact Store，环境事实→MEMORY，临时→不存。

**Agent 自查清单：**

- [ ] **盘点工具：** 当前会话有哪些可用的持久化工具？
  不一定有 `fact_store`，不一定有 `memory`，不一定有知识库 MCP。
  有什么就用什么，不预设任何一类必须存在。
- [ ] **应记未记？** 盘过工具后，对每个可用的工具，问自己有没有应该存但还没存的信息。
- [ ] **已记但错？** 记忆中的路径、IP、主机名是否已过期？
  偏好是否反映了用户最新的口头表达？
- **归属确认：** 流程/解法类信息有没有被误存到 memory 而不是 skill？
  （「怎么做」→ skill，「是谁/是什么」→ memory）
- [ ] **版本一致性：** 如果本次修改了 `registry.yaml` 中的版本号和对应本地仓库的
  `SKILL.md`/`pyproject.toml`，运行 `sync-routing.py --verify-versions` 
  捕获版本漂移。引用：`skills/execution-framework/scripts/sync-routing.py`
  ```bash
  cd <path-to-execution-framework>
  uv run scripts/sync-routing.py --verify-versions
  ```
  本次会话中 `astra-sre` 的 `pyproject.toml` 版号曾为 `0.1.0`（registry 刚设
  为 `1.0.0`），正是被此检查捕获的。
- [ ] **凭证确认：** 上述所有工具中是否有残留的明文密码或 token？
  凭证只能放在加密存储（GPG / KeePass / .env），不在任何 agent 持久化工具中。
- [ ] **Fact Store 去重：** 如果本次有访问 fact_store，检查同类条目是否有
  重复或高度相似。（常见模式：同一信息在不同时间被多次记录——
  本会话中发现 Pandoc 滤镜信息×4 条、ANGELIA 名称×2、智谱配置×2。
  用 `fact_store(action='list')` 或关键词搜索即可发现。）
- [ ] **Fact Store 临时/过期条目检查：** 扫描 fact_store 中是否有 TODO 样式的
  临时任务条目（如"Check memory for laptop credentials"、"API keys inventory
  check"），或引用了已被淘汰的路径/结构的条目——这些不属于持久知识，应删除。
- [ ] **Fact Store 分类核对：** 偏好/习惯类条目（中文名、沟通风格、工具链偏好）
  应有 `category=user_pref`，而非默认的 `general`。

```
Information produced
  │
  ├─ Type: preference / workflow / reference / environment fact / ephemeral state
  │
  ├─ Tool survey: what storage tools does this Hermes instance have?
  │   (agent enumerates available tools — no specific tool is presumed to exist)
  │
  └─ Placement decision:
      ├─ Reusable workflow / solution / lesson
      │   → skill (skill_manage), never into persistent memory
      ├─ Long-lived reference / decision record
      │   → knowledge-base-type tools preferred, local files as fallback
      ├─ Preference / corrected assumption / environment fact
      │   → external persistent memory preferred (avoids context bloat)
      │     fall back to memory when no external persistent storage is available
      └─ Ephemeral state / PR number / commit SHA / one-off output
          → store nowhere, retrieve via session_search
```

**Agent self-check list:**

- [ ] Enumerate all storage tools available to this session
  (agent lists them — no specific tool is presumed to exist)
- [ ] For each available tool, check for **information that should have been recorded** or **information that was recorded incorrectly**
- [ ] Confirm that workflow/solution information belongs in skills, not in any persistent memory
- [ ] Confirm no credential residuals (credentials belong in encrypted storage, not in any tool listed above)
- [ ] Confirm that **no TODO / task progress / commit SHA / ephemeral session state** was written to memory
  (These belong to `session_search` recovery, not persistent storage)
- [ ] Confirm that all persistent memory entries use **declarative sentences** (`user prefers concise responses` ✓),
  never **imperative sentences** (`must respond concisely` ✗)

### ⑥ Environment Baseline Comparison (if modification was involved)

**——If a baseline was recorded before the change, has every item been compared after the change?**

### ⑦ 提交整理（如果本次涉及版本控制仓库）

——**修改涉及 git 仓库，需要提交吗？**

如果是 astra 生态项目或任何准备推送的仓库，按此流程：

1. **先整理 commit 规划** — 列出仓库名、变更内容、拟用的 commit message
   - 格式: Conventional Commits，全小写 type+scope，body 写「为什么」
   - 语言: **英式英语**（British English: organise, standardise, colour...）
   - 逐条告知用户让确认，确认后再执行 `git commit`
2. **如果有多个关联仓库**（如 registry.yaml + 多个 skill 同时修改），优先将关联变更整理好
3. **确定推送地点** — 检查当前机器是否有 GitHub 凭据（SSH key 已注册、GPG 可解密 pass store、或 GCM 已登录）。**永远用 HomeCentre01 推送**，不在用户的个人设备（X1 Tablet 等）上直接 `git push`：
   - 如当前机器是 HomeCentre01 → 直接推
   - 如当前机器不是 HomeCentre01 → 通过 **git bundle** 将 commit 传输到 HomeCentre01 再推送
   - 参见 `work-closure-check/references/cross-machine-git-bundle.md`
4. **版本一致性**：如果本次修改了 `registry.yaml` 和对应仓库的版本号，务必在 commit 前运行：
   ```bash
   cd <path-to-execution-framework>
   uv run scripts/sync-routing.py --verify-versions
   ```
4. **authour 身份**：astra 项目使用 `Alrcatraz <alrcatraz@gmx.com>`，每个仓库应已设置
   `git config user.name` 和 `user.email`。如未设置，先设置再提交。
5. **pre-commit hook** 可能会阻拦（如 lifecycle 扫描未匹配的标记）。如果确认变更安全，可用 `--no-verify` 绕过。
6. **README 完整性**：如果本次准备推送新仓库到 GitHub，检查 README 是否包含许可证徽章、星数徽章、最后提交徽章和星图（plain `<img>` 形式，不是 `<a><picture>`）。本会话中 6 个仓库的星图最初因使用 `<a><picture>` 包裹显示为链接而非图片。详见 `work-closure-check/references/repo-publication-convention.md`。
7. **分支名对齐**：如果目标仓库是基于模板创建的，远端默认分支是 `main` 而非 `master`。推送前运行 `git ls-remote --symref origin HEAD` 确认后再推。本会话 5 个仓库曾因此产生双分支。详见 `work-closure-check/references/repo-publication-convention.md`。

> 参考: `work-closure-check/references/version-convention.md`
> 参考: `work-closure-check/references/repo-publication-convention.md` — README 徽章、星图嵌入、分支命名核对
> MVCE: 本会话中 `astra-sre` 的 `pyproject.toml` 遗留了 `0.1.0` 而 registry 标为 `1.0.0`，
> 被 `--verify-versions` 捕获后才修复。

## 标准收尾流程

## Standard Closure Procedure

After the checklist is complete, follow this order:

1. ✅ **Notify the user** — "Task complete, please confirm success"
2. ⏳ **Wait for confirmation** — Do **not** skip confirmation and clean up directly
3. 🧹 **After user confirms** — Clean up temporary files/scripts
4. 📝 **Full summary** — What was done, results, outstanding issues
5. 📚 **Final offer** — "Is there anything else I can help with?"

> **Important:** Even if all checklist items pass, the final notification to the user is still required. The user may spot issues you missed.

1. **不要跳过"等待确认"直接清理。** 用户可能想看一眼测试结果或临时文件内容。
2. **不要混淆「技能更新」和「存记忆」。** 技能是「怎么做」，记忆是「用户是谁/环境长什么样」。同一个 technique 不应该同时记在两个地方。
3. **「本次没涉及凭证」不等于「记忆里没有残留」。** 记忆可能从前几个 session 的凭证还留着——检查清单的①必须做，不能因为本次没涉及就跳过。
4. **「多问一句」不是选项，是必选。** 即使觉得"这次没什么特别的"，也要执行检查清单——你可能忽略了值记录的东西。
5. **收尾阶段的 skill 不要产生新的收尾。** 加载此 skill 执行检查 → 完成 ✅，不要检查完又触发自己再问一轮。

6. **「自动分析结论」不等于「用户确认成功」**。以下情况尤其危险：

| 工具/方法 | 风险 | 正确做法 |
|:---------|:----|:---------|
| **Vision model 分析截图** | 视觉模型可能遗漏像素级渲染瑕疵（CJK 字符重叠、锯齿、色差等） | 仅作为参考线索，**必须等用户亲自确认**后再宣布成功 |
| **`fc-match` 返回正确** | 只说明 fontconfig 层面匹配对了，不保证应用层（Skia/Pango）渲染正确 | 说明「fontconfig 匹配已修复，请重启应用看看效果」 |
| **日志无错误** | 日志没有错误不代表功能正常 | 必须做实际功能验证 |

**一律先说「请确认是否修复了」，不说「修好了」**。除非用户在同一个 screen/会话中亲眼见证了变化并口头确认。将自动分析结果呈现为 evidence 而非 verdict。

7. **本技能的检查清单是静态的，但生态钩子系统已可用。** 新的子系统（如 SRE、MCP 管理等）加入生态时，此清单不会自动扩展。解决方法：在 `~/.astra/repos/astra-aiagent-infra/registry.yaml` 中为新增子系统声明 `lifecycle.closure` 钩子，运行 `python3 lifecycle/astra-lifecycle-sync --update` 即可自动注入检查项到下方的 ## Ecosystem Hooks 区域。钩子加了却没显示 → 检查是否忘了跑同步，或误改了 public 副本（`~/Projects/astra/`）而非私有副本（`~/.astra/repos/`）。

8. **发布新的 astra 仓库时记得打 tag。** 用户偏好：对 git 管理项目使用语义化版本标签（`vMAJOR.MINOR.PATCH`），在里程碑发布时标记，不每个 commit 都打。详见 `github-repo-management` skill 的 Versioning & Tagging Convention 章节。

9. **批改版号后不验证 = 肯定有漂移。** 如果本次任务中你同时修改了 `registry.yaml`
   和多个本地仓库的 `SKILL.md`/`pyproject.toml` 版本号，**必须先跑版本验证再通知用户**：
   ```bash
   uv run scripts/sync-routing.py --verify-versions
   ```
   不这么做的话，一定会至少有一个仓库的版本和 registry 对不上（本会话中
   `astra-sre` 就是真实案例——`pyproject.toml` 是 `0.1.0`，registry 刚改为
   `1.0.0`，被验证脚本抓了个正着）。

## Ecosystem Hooks

<!-- LIFECYCLE_HOOKS_BEGIN -->
**Closure lifecycle hooks — auto-generated.** Do not edit manually.
Run `astra-lifecycle-sync --update` to refresh.

### From execution-framework
- [🟡] Verify version consistency across registry + local repos
  *(recommended, trigger: registry.yaml or SKILL.md modified)*
  ```bash
  cd $ASTRA_EF_DIR && uv run scripts/sync-routing.py --verify-versions
  ```

### From work-closure-check
- [🟡] 任务中发现了会变的参考数据（API 端点、端口、路径、限制等）？→ 写入 dynamic_ref KB
  *(recommended, trigger: discovered any reference data that may change over time)*
- [🟡] 修改了服务配置/端口/路径？→ 同步更新 hermes_config KB
  *(recommended, trigger: service config, port mapping, or path changed during task)*
- [🔴] 用户表达了新的偏好或纠正了你的假设？→ 写入 Fact Store (user_pref)
  *(required, trigger: user expressed a preference or corrected an assumption)*

### From astra-vcs-assist
- [🔴] Verify all sub-skill symlinks in Hermes discovery path are reachable
  *(required, trigger: sub-skill added, removed, or repo path changed)*
  ```bash
  for d in astra-vcs-assist-gpg-key astra-vcs-assist-git-init astra-vcs-assist-git-dev astra-vcs-assist-git-release astra-vcs-assist-git-sync; do test -L "$HOME/.hermes/skills/vcs/$d" -o -d "$HOME/.hermes/skills/vcs/$d" || echo "MISSING: $d"; done

  ```
- [🟡] Verify routing.yaml covers every sub-skill directory
  *(recommended, trigger: routing.yaml or sub-skill SKILL.md modified)*
  ```bash
  cd "$HOME/.astra/repos/astra-vcs-assist" && for d in git/skills/*/ gpg/*/; do skill=$(basename "$d"); grep -q "$skill" routing.yaml || echo "UNCOVERED: $skill"; done

  ```

### From astra-sre
- [🔴] Run health scan to verify device coverage after SRE changes
  *(required, trigger: devices.yaml or health-scan.py modified)*
  ```bash
  cd $ASTRA_SRE_DIR && python3 scripts/health-scan.py --json
  ```
- [🟡] Update sre_incidents knowledge base with post-mortem after any repair
  *(recommended, trigger: any SRE repair or incident occurred)*
  > Action: `kb_add(kb='sre_incidents', content=..., tags=...)`
- [🟡] Verify devices.yaml is in sync with infrastructure-device-inventory
  *(recommended, trigger: devices.yaml modified)*
  ```bash
  diff <(python3 scripts/health-scan.py --json) <(cat config/devices.yaml)
  ```

<!-- LIFECYCLE_HOOKS_END -->
