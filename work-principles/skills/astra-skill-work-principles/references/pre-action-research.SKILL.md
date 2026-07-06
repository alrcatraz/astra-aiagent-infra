---
name: pre-action-research
description: "Mandatory research and index lookup before taking action. When investigation, credentials, preferences, devices, services, or project information is involved, consult documentation, tutorials, and reference indexes before proceeding."
category: devops
version: 1.0.0
---

# pre-action-research

## Trigger Conditions

This skill is automatically loaded when the task involves:
- Investigation, research, analysis, planning, proposing a solution
- Credentials, preferences, devices, services, projects, indexes
- Any need to query, record, or update persistent information

Also triggered by: 排查、调查、研究、调研、分析、方案、计划、凭证、偏好、设备、服务、项目、索引、查询、记录

> **Routing:** Prefer loading `execution-framework` first; it will route here when the task involves research or planning.
- 任何需要查询、记录或更新持久化信息的事项

## Checklist

- [ ] **是否涉及需要查询的信息类型？**（凭证/偏好/设备/服务/项目/决策记录）
  - [ ] 是 → 查本地参考索引，确认存放规则和访问方式
  - [ ] 凭证相关 → 详见 `references/credential-yaml-schema.md`（分组、YAML 结构、加密方式）
      - **完整凭据查询协议、三层解密方法、sudo 注入等详见 `credential-store-management` skill**
  - [ ] **需要密码/sudo → 先查 GPG 凭据库，不要问用户要。** 解密：`gpg --batch --decrypt --pinentry-mode loopback --passphrase "$PW" ~/Documents/credentials/*.gpg`。凭据库里也没有 → 再去问用户。详见 `credential-store-management` skill 的完整三层协议。
- [ ] **是否有相关文档、官方资料或教程可以参考？**
  - [ ] 是 → 先查阅，分析后再提方案，不跳过调研直接动手
- [ ] **方案是否已形成并获得用户批准？**
  - [ ] 否 → 先提方案，等批准再执行
  - [ ] **特别警惕「修一个明显的问题」——知道要修什么 ≠ 知道怎么修。** 即使问题很明确（如 badge 报错、文案笔误、版本号过时），方案层面仍然有多个选择（删掉/替换/换服务商），需要先讨论再动手。**不要把「诊断结论」和「治疗方案」合并成一步。**
  - [ ] **批准要用用户明确的许可指令**（如"可以""好的""开干"），不能拿用户的提问/反馈当作隐含许可。

## Pitfalls

1. **不要跳过查索引直接凭记忆操作。** 记忆中的信息可能过时或不完整。先用索引确认最新规则。
2. **"新旧"不是跳过索引的理由。** 无论是读取已有的还是记录新的，第一步都是查索引确认规范。
3. **用户给出 GitHub `user/repo` 名时，直接 GitHub 访问，不要先搜本地文件系统。** 用户给的仓库名是确定的，本地找不到不等于不存在。先试 `git ls-remote` 或 API 检查可见性，再决定是否需要代理或凭据。
4. **"不知道密码就找用户要"是个坑。** 凭据优先走 GPG 加密文件或 KeePassXC：详见 `credential-store-management` skill 的三层查询协议。只有所有凭据库里确实没有时才问用户。
5. **偏好记录目标：Fact Store，不是 memory。** SOUL.md §5.1-5.2 规定：简短结构化偏好 → Fact Store（`user_pref` 类别）；完整参考文档 → `dynamic_ref` 知识库；地图索引 → 本地参考索引。`memory`（持久记忆）用于环境事实、项目约定和工具习惯，不是偏好的存放处。用户说出偏好 → 直接 `fact_store(action='add', category='user_pref')`，不要在 `memory` 里记偏好。
6. **不要因为改动小就跳过批准步骤。** badge 地址错误、文案措辞、README 格式、版本号这些看似"直接改更快"的改动，仍然要先提方案再等批准。用户精确的纠正：**"你在定方案阶段跳过我的许可了，这非常坏"**。正确流程：① 发现问题 → ② 提方案列选项给权衡 → ③ 等用户明确说"可以/好的/开干" → ④ 执行。禁止模式：诊断 + 动手合并成一步。

   **尤其警惕 README 和文档变更。** 技术代码改动大家天然会等批准，但文档排版、badge 去留、文案措辞这些容易自己觉得"明显该这么做"就顺手改了——反而正是用户容易有明确偏好的地方。**文档改动同样需要方案 + 批准。**
