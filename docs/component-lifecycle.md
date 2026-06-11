# Component Lifecycle

The evolution stages of components within the astra-aiagent-infra ecosystem.

---

## Stages

```
┌────────────┐     ┌──────────┐     ┌──────────┐     ┌────────────┐
│  Plan      │ ──→ │  Active  │ ──→ │  Stable  │ ──→ │ Deprecated │
└────────────┘     └──────────┘     └──────────┘     └────────────┘
```

### Plan
- Clear concept exists, implementation has not started
- `status: planned` in `registry.yaml`
- May not have a corresponding repository yet

### Active
- Under active development or maintenance
- `status: active` in `registry.yaml`
- Standalone repository is ready (or `location` points to an in-repo path pending extraction)

### Stable
- Feature-complete, in maintenance mode (bug fixes only, no new features)
- `status: stable` in `registry.yaml`

### Deprecated
- No longer maintained; users are advised to migrate to a replacement
- `status: deprecated` in `registry.yaml`
- Cleanup: remove from registry, purge from service inventory, remove health checks

---

## State Transitions

| Transition | Action |
|:-----------|:-------|
| Concept mature, ready to build | `planned` → `active` |
| Feature-complete, running stable | `active` → `stable` |
| Replacement exists, retiring | `stable` → `deprecated` → removal |
| Someone picks up a deprecated component | Keep `deprecated` annotation with pointer to successor |
