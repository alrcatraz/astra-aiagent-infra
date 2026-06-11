# Design Principles

Consistent principles that apply across all components of the astra-aiagent-infra ecosystem.

---

## 1. Independence

Each component has its own repository, its own version number, and its own release cadence.
`astra-aiagent-infra` acts as an index and governance layer — not a centralized code manager.

## 2. Composability

Components communicate through standard interfaces (MCP stdio transport, Hermes skill scanning mechanism, CLI pipelines) with no hard coupling.

## 3. Self-Describing

Every component is fully documented in `registry.yaml`. Anyone reading the registry can determine at a glance whether a component fits their needs.

## 4. Cross-Platform First

Documentation and tools prioritize Linux (RHEL-family / Debian-family / SUSE-family), with secondary consideration for macOS / NixOS.
Code itself targets standard Python and Shell wherever possible, avoiding distribution-specific features.

## 5. Security by Default

- Credentials are never hardcoded or committed to repositories
- SSH key authentication is preferred over passwords
- Services bind to dedicated loopback addresses (127.0.0.x)
- Always safeguard before changes; always scan for side effects after changes

## 6. Progressive Enhancement

Components can start as "good enough" and improve over time.
Don't wait for every feature to be finished before shipping — done beats perfect, iteration beats perfection.
