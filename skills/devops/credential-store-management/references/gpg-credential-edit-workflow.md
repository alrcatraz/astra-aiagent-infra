# GPG Credential File — Add/Edit Workflow

## Prerequisites

- GPG passphrase from `~/.hermes/.env`:
  ```bash
  grep '^export GPG_Key_Alrcatraz=' ~/.hermes/.env | cut -d= -f3- | sed "s/^'//;s/'$//"
  ```
- The `.gpg` file path (e.g. `~/Documents/credentials/personal-credentials.yaml.gpg`)
- The index README at `~/Documents/credentials/README.md` — update this too

## Workflow

### Step 1: Decrypt

```bash
GPG_PASS=$(grep '^export GPG_Key_Alrcatraz=' ~/.hermes/.env | cut -d= -f3- | sed "s/^'//;s/'$//")
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
      main_ip: 192.168.1.100
    access:
      methods:
        - type: password
          value: 'secret123'
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

```bash
cat /tmp/creds-decrypted.yaml | gpg --batch --no-tty --yes \
  --passphrase "$GPG_PASS" --pinentry-mode loopback \
  --symmetric --cipher-algo AES256 \
  -o ~/Documents/credentials/personal-credentials.yaml.gpg
```

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
- **Password quoting**: If the password contains special characters (`@`, `$`, `!`), quote it in YAML: `value: 'secret123'`
- **SSH key note**: After deploying an SSH key, update the entry's note to reflect that the password is fallback-only.
- **Always re-encrypt immediately**: Do not leave the decrypted file on disk longer than needed.
