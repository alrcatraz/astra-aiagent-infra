# Credential Management Standard

## Principles

1. **Never in Repos** — Credentials must never enter Git. `registry.yaml` contains no sensitive information.
2. **Group Management** — Organize by category: personal / work / other / temporary. Encrypt each group separately.
3. **GPG Encryption** — Store credential files using `gpg --symmetric`: `*.yaml.gpg`
4. **No Plaintext on Disk** — Decrypt via `gpg -d` piped to consuming commands; never write plaintext to disk.

## References

Each component should document in its own README what credentials are needed and how to set the required environment variables.
