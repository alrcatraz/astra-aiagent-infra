# Reference Protocol

How cross-layer facts are referenced — never copied — across the astra ecosystem.

---

## Purpose

The astra ecosystem stores each fact exactly once, in the layer that owns it.
When a component needs a fact owned by another layer, it stores a **typed
reference** instead of duplicating the value. This keeps a single source of
truth truly single, and makes component replacement a resolution change rather
than a data migration.

**Anti-pattern:** duplicating machine addresses, model fallback chains, or
secrets into a registry entry. Duplication drifts: one update in the owning
layer leaves stale copies everywhere. Validated against
`astra-agent-constellation` (2026-08-04) after a review flagged the same fact
stored in three places (agent registry / SRE devices.yaml / credential store).

## Reference Types

| Reference | Format | Resolves against | Example |
|:----------|:-------|:-----------------|:--------|
| `device-ref` | device ID | device/connection layer (credential store `connection.paths`, multi-path priority: LAN / SD-WAN / multi-hop) | `host: <HOST-1>` |
| `tier-ref` | tier name | model config layer (L2) — primary model + fallback chain live there, not in the referencing component | `model: standard` |
| `chan-ref` | channel ID | channel registration (e.g. guardian's independent bot account) | `channel: <CHAN-1>` |
| `agent-ref` | agent name | another entry in the same registry (mutual-guardianship closure) | `owner: guardian-1` |
| `doc-ref` | document anchor | documentation (deployment definition, recovery procedure) | `deploy_def: docs/07-adoption.md#phase-1` |

## Rules

1. **Ownership** — A component stores only its own lifecycle facts (e.g. an
   agent registry stores name, role, version, health check, restart). Facts
   owned by another layer are referenced by typed ID, never embedded.
2. **Validation** — Validation gates (e.g. `registry-check.py`) MUST reject
   unresolvable `agent-ref`s (owner points at a ghost), reject self-ownership,
   and enforce placeholder format (`<HOST-N>`, `<CHAN-N>`) in public copies.
3. **Ecosystem compatibility** — Swapping a component (GPG → Vault,
   astra-sre → own monitoring, KeePassXC → Bitwarden) changes only the
   resolution target, never the referencing file. The registry is an *index*,
   not a *warehouse*.
4. **Secrets stay in L5** — Credentials never move into the knowledge base
   (L4). The KB is wide-read (all agents retrieve); credentials are narrow-read
   (per-entry decryption). Plaintext in the KB violates the L5 MUST NOT;
   encryption inside the KB is a second credential store in disguise.
5. **Human and machine layers are parallel** — KeePassXC (human layer) and
   GPG-encrypted YAML (machine layer) are separate stores serving different
   consumers. They are not candidates for migration into each other, nor into
   the KB. Device addresses resolve through `connection.paths` in the machine
   layer; the human layer is out of band.

## Two-Source Model: Source of Truth vs Execution View

A fact has **one source of truth** (where it is owned and edited) but may have
**execution views** (derived, machine-consumable copies). Views exist because
`no_agent` scripts cannot resolve references: they cannot run GPG decryption or
LLM resolution on every tick. The rule that keeps views from drifting:

- **Source of truth (credential store)** — `connection.paths`, addresses, and
  secrets live here. Edited by humans / LLM agents. This is the layer that
  `device-ref` resolves against.
- **Execution view (e.g. `astra-sre/config/devices.yaml`)** — plaintext copy
  consumed by scheduled `no_agent` scripts (`health-scan.py`). It MUST carry a
  header comment declaring it DERIVED from the credential store, so a reader
  knows it is a cache, not a source. Re-sync it after credential-store changes
  (or treat drift as a known, accepted cost for read-only scan inputs).
- **Reference (agent registry)** — `device-ref` pointers, never the values.

## Consumers

| Component | Where the protocol applies |
|:----------|:---------------------------|
| `astra-agent-constellation` | Agent registry schema (`templates/agent-registry/registry.yaml.example`) and its validation gate (`scripts/registry-check.py`) |
| `credential-store-management` | `device-ref` resolution against `connection.paths` (multi-path priority) |
| `astra-sre` | `devices.yaml` — execution view of the credential store for `no_agent` scans (DERIVED, see Two-Source Model above) |

## Document Status

This document is the authoritative source for the reference protocol.
Component documentation (e.g. the agent registry chapter of
`astra-agent-constellation`) may summarise it and link here, but must not
fork the field semantics.

**2026-08-04** — Added Two-Source Model (source of truth vs execution view):
`astra-sre/config/devices.yaml` clarified as a DERIVED execution view of the
credential store for `no_agent` scans, resolving a contradiction where the
same fact had two claimed sources.
