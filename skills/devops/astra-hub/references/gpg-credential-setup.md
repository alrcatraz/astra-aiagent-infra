# GPG Credential Setup (Example)

> Applicable for first-time credential storage setup on a new machine
> or new Hermes instance.

## Prerequisites

- GPG installed on the target machine
- Existing GPG key pair (for encryption)
- Encryption passphrase securely stored (e.g. in `.env`)

## Credential File Architecture

Credentials are managed in separate files by category, all encrypted with the same GPG key:

| Group | File Naming | Content |
|:------|:------------|:--------|
| 🔵 Personal | `personal-credentials.yaml.gpg` | Own devices (servers, workstations, NAS, VPS) |
| 🟠 Work | `work-credentials.yaml.gpg` | Client / work servers and devices |
| 🟢 Other | `other-credentials.yaml.gpg` | Friends, family, shared devices |
| ⚪ Temporary | Not persisted | One-time access, discard after use |

## YAML Schema Reference

```yaml
devices:
  <identifier>:
    hostname: "<hostname>"
    os:
      name: "<distribution>"
    description: "<purpose>"
    tags:
      - <group>
      - <device_type>
    network:
      main_ip: "<primary_ip>"
      overlay:
        tunnel_a: "<ip>"
        tunnel_b: "<ip>"
    connection:
      paths:
        - priority: 1
          type: "direct"
          via: []
        - priority: 2
          type: "jump"
          via:
            - host: "<jump_host>"
              user: "<username>"
              ip: "<ip>"
    access:
      methods:
        - type: ssh_key
          key_path: "~/.ssh/id_xxx"
        - type: password
          value: "<password>"
    accounts:
      - username: "<username>"
        is_admin: true
        access: sudo
    services:
      - name: "<service>"
        type: web_ui
        accounts:
          - username: "<username>"
            password: "<password>"
```

## Encrypt / Decrypt Examples

### Encrypt a New File

```bash
passphrase="<your-gpg-passphrase>"
cat /tmp/my-credentials.yaml | gpg --batch --yes --symmetric \
  --passphrase "$passphrase" --cipher-algo AES256 \
  --output ~/credentials/personal-credentials.yaml.gpg
rm /tmp/my-credentials.yaml
```

### Decrypt to Verify

```bash
passphrase="<your-gpg-passphrase>"
echo "$passphrase" | gpg --batch --no-tty --passphrase-fd 0 \
  --pinentry-mode loopback \
  --decrypt ~/credentials/personal-credentials.yaml.gpg 2>/dev/null
```

## Security Points

- Store GPG passphrase in `.env` environment variable, never in memory or skill text
- SSH keys are preferred over passwords; fall back to passwords only when keys are unavailable
- Temporary credentials are discarded immediately after use, never persisted
- Store only file references in memory/skills, never actual values
- Group management (personal / work / other / temporary) reduces the blast radius of a leak
