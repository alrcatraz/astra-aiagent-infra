# SSHFS Remote Development Setup

> Fallback when VS Code Remote SSH `agent host` hangs on "Waiting for server log..."

## Symptom: VS Code 1.123.x Agent Host Hang

VS Code 1.123.x uses a new `agent host` architecture for Remote SSH. When broken:
- Status bar: "Opening Remote..." → "Waiting for server log..." (repeating rapidly)
- `strace` reveals: **futex deadlock** + tight `mmap`/`munmap` thrash loop
- Server binary runs but never binds a port or outputs ready signal
- Same bug across multiple patch releases (1.123.0, 1.123.1, 1.123.2)

**Diagnosis:**
```bash
# Run agent host with strace to catch the hang
~/.vscode-server/code-<commit> agent host \
  --cli-data-dir ~/.vscode-server/cli \
  --server-data-dir ~/.vscode-server \
  --without-connection-token --host 127.0.0.1 --port 0 &
strace -f -o /tmp/vscode-strace.log <pid>
# Look for: futex(..., FUTEX_WAIT_PRIVATE, ..., NULL) ← never returns
```

## SSHFS Setup (openSUSE)

### Prerequisites

- SSH key auth configured between machines
- Remote host available via SSH alias (e.g. `homecentre01-easytier`)
- Sudo password stored in GPG credentials (`personal-*.gpg`)

### Install & Mount

```bash
# Install (one-time)
sudo zypper install sshfs

# Create mount point (one-time)
mkdir -p ~/Projects/<mount-name>

# Mount
sshfs <remote-alias>:/remote/path ~/Projects/<mount-name>

# Verify
ls ~/Projects/<mount-name>
```

### Sudo via Askpass (when sudo -S is blocked)

Use `SUDO_ASKPASS` to pipe passwords securely without `sudo -S`:

```bash
# Get password from GPG creds
gpg --batch --decrypt --pinentry-mode loopback --passphrase "<gpg-pass>" \
  ~/Documents/credentials/personal-credentials.yaml.gpg 2>/dev/null \
  | grep suset01 -A5 | grep password | cut -d'"' -f2 > /tmp/pass

# Create askpass script
echo "cat /tmp/pass" | ssh <host> 'cat > /tmp/askpass && chmod +x /tmp/askpass'

# Use sudo -A
ssh <host> 'SUDO_ASKPASS=/tmp/askpass sudo -A zypper install sshfs'

# Cleanup
ssh <host> 'rm -f /tmp/askpass /tmp/pass'
```

### Unmount

```bash
fusermount3 -u ~/Projects/<mount-name>
```

### VS Code Font Chain for CJK

When using SSHFS with local VS Code on openSUSE:

```
'D2CodingLigature Nerd Font Mono','Maple Mono Normal NF CN','Noto Sans SC','Droid Sans Mono','monospace'
```

- **Maple Mono Normal NF CN** = JetBrains-like narrower variant with CJK support
- Hinted > unhinted for font metric stability on Linux
- Install to `~/.local/share/fonts/` (no sudo needed)
- Full VS Code restart required after font install (not just Reload Window)
- `MapleMonoNormal-NF-CN-unhinted.zip` from GitHub releases

### Alternatives if SSHFS isn't enough

| Method | Use Case | Setup Time |
|--------|----------|------------|
| **code-server** | Full VS Code in browser | ~5 min |
| **JetBrains Gateway + Rider** | Full IDE, different protocol | Configure once |
| **Downgrade VS Code** | If old Remote SSH works | Varies |
