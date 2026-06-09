# 组件生命周期

组件在 astra-aiagent-infra 生态中的演进阶段。

---

## 阶段

```
┌────────────┐     ┌──────────┐     ┌──────────┐     ┌────────────┐
│  Plan      │ ──→ │  Active  │ ──→ │  Stable  │ ──→ │ Deprecated │
│  (规划中)  │     │  (活动)  │     │  (稳定)  │     │  (已废弃)  │
└────────────┘     └──────────┘     └──────────┘     └────────────┘
```

### Plan — 规划中
- 有明确构思，尚未开始实现
- `registry.yaml` 中 `status: planned`
- 可能没有对应仓库

### Active — 活动
- 正在积极开发/维护
- `registry.yaml` 中 `status: active`
- 独立仓库已就绪（或 `location` 指向本仓库内路径待提取）

### Stable — 稳定
- 功能成熟，处于维护模式（修 bug 不加功能）
- `registry.yaml` 中 `status: stable`

### Deprecated — 已废弃
- 不再维护，建议用户迁移到替代组件
- `registry.yaml` 中 `status: deprecated`
- 清理：从注册表移除、清理服务清单、移除健康检查

---

## 状态迁移

| 变更 | 操作 |
|:-----|:-----|
| 构思成熟，准备开工 | `planned` → `active` |
| 功能完成，运行稳定 | `active` → `stable` |
| 有替代方案，要退役 | `stable` → `deprecated` → 移除 |
| 废弃后有人接棒 | 保留 `deprecated` 标注并指向替代组件 |
