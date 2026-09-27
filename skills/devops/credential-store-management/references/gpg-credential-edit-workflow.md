# GPG Credential File — Add/Edit Workflow

Procedure for maintaining a GPG-encrypted YAML credential file (symmetric AES256).
Applies when GPG-YAML is the live Layer-2 store, or as fallback maintenance on a frozen
archive. **Core hazard: passphrase/stdin collision during re-encryption** — see Step 3.
Always cp-backup first and verify by decrypting back before deleting anything.

## Prerequisites

- GPG passphrase from `~/.hermes/.env`:
  ```bash
  grep '^GPG_Key=' ~/.hermes/.env | cut -d= -f2- | sed "s/^'//;s/'$//"
  ```
- The `.gpg` file path (e.g. `~/Documents/credentials/personal-credentials.yaml.gpg`)
- The index README at `~/Documents/credentials/README.md` — update this too

## Workflow

### Step 1: Decrypt

```bash
GPG_PASS=$(grep '^GPG_Key=' ~/.hermes/.env | cut -d= -f2- | sed "s/^'//;s/'$//")
echo "$GPG_PASS" | gpg --batch --no-tty --passphrase-fd 0 --pinentry-mode loopback \
  --decrypt ~/Documents/credentials/personal-credentials.yaml.gpg 2>/dev/null > /tmp/creds-decrypted.yaml
```

### Step 2: Edit the YAML

Use Python (dict insertion) or `yq` to add or modify the entry. Example — insert a new device:

```python
import sys

with open('/tmp/creds-decrypted.yaml') as f:
    lines = f.readlines()

# Find insertion point (before a specific device)
insert_before = None
for i, line in enumerate(lines):
    if line.rstrip() == '  some-device:':
        insert_before = i
        break

new_entry = """  new-device:
    hostname: New-Device-Name
    os:
      name: SomeOS 1.0
    description: What this machine does
    tags:
      - personal
      - server
    network:
      main_ip: <lan-ip>
    access:
      methods:
        - type: password
          value: '<dummy-password>'
          note: fallback when SSH key unavailable
    accounts:
      - username: myuser
        is_admin: true
        access: sudo
        note: SSH key deployed ✅
"""
lines = lines[:insert_before] + [new_entry] + lines[insert_before:]

with open('/tmp/creds-decrypted.yaml', 'w') as f:
    f.writelines(lines)
```

### Step 3: Re-encrypt

**⚠️ Passphrase-feed hazard:** never `cat file | gpg --passphrase-fd 0 ...` — when stdin
carries both passphrase and plaintext the pipe races and mangles the passphrase bytes,
producing "Bad session key" ciphertext. Correct form: **plaintext as a FILE argument,
fd 0 exclusively for the passphrase**:

```bash
printf '%s' "$GPG_PASS" | gpg --batch --no-tty --yes --pinentry-mode loopback \
  --passphrase-fd 0 --symmetric --cipher-algo AES256 \
  -o ~/Documents/credentials/personal-credentials.yaml.gpg \
  -- /tmp/creds-decrypted.yaml     # 明文走文件参数，fd0 只喂口令——勿用 cat|gpg（会产出坏密文）
```

The most robust form is Python subprocess controlling both streams explicitly:

```python
subprocess.run(['gpg','--batch','--no-tty','--yes','--pinentry-mode','loopback',
                '--passphrase-fd','0','--symmetric','--cipher-algo','AES256',
                '-o',TARGET,'--',PLAINFILE], input=passphrase.encode())
```

**After encrypting, immediately decrypt back and byte-compare against the plaintext
before deleting backups or temp files.**

### Step 4: Clean up

```bash
rm -f /tmp/creds-decrypted.yaml
```

### Step 5: Update index README

Edit `~/Documents/credentials/README.md` to add the new device in the device index table.

### Step 6: Verify

```bash
echo "$GPG_PASS" | gpg --batch --no-tty --passphrase-fd 0 --pinentry-mode loopback \
  --decrypt ~/Documents/credentials/personal-credentials.yaml.gpg 2>/dev/null \
  | grep -A5 "new-device:"
```

## Notes

- **Working directory**: Write the decrypted file to `/tmp/` — it's on tmpfs and cleared on reboot.
- **Password quoting**: If the password contains special characters (`@`, `$`, `!`), quote it in YAML: `value: '<dummy-password>'`
- **SSH key note**: After deploying an SSH key, update the entry's note to reflect that the password is fallback-only.
- **Always re-encrypt immediately**: Do not leave the decrypted file on disk longer than needed.
