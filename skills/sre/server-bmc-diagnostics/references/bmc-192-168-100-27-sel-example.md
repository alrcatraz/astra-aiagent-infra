# BMC SEL Reference — star-Rack-Server (192.168.100.27)

Captured 2026-06-09 via `ipmitool -I lanplus` through SUSET01 jump host.

## System

| Field | Value |
|:------|:------|
| Model | OEM Rack Server |
| BMC Firmware | 1.03.0005 |
| BIOS | T1ADG06.00 |
| Serial | 80102086T265021510 |
| GPU | 4× RTX PRO 6000 Blackwell (392 GB VRAM) |
| Driver | 575.64.05 |
| CUDA | 12.8.61 |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-31-generic |
| Network | OS IP 192.168.100.26, BMC IP 192.168.100.27 |

## Access Command

```bash
# Via SUSET01 jump host (ipmitool installed 2026-06-09)
# Decrypt credentials from GPG first:
source <(grep 'GPG_Key_Alrcatraz' ~/.hermes/.env)
echo "$GPG_Key_Alrcatraz" | gpg --batch --no-tty --passphrase-fd 0 \
  --pinentry-mode loopback --decrypt ~/Documents/credentials/work-credentials.yaml.gpg \
  2>/dev/null | grep 'rack_server_bmc'

# Then read SEL:
ssh suset01 "ipmitool -I lanplus -H 192.168.100.27 -U <user> -P '<pass>' sel list"
```

> **Note:** `--pinentry-mode loopback` is REQUIRED on GPG 2.5+ for headless operation. Without it, `gpg-agent` blocks indefinitely waiting for GUI pinentry.

## SEL Content Summary

**Total entries:** 500 (single pass, not yet wrapped)

### Key Events

| Time | Event | Notes |
|:-----|:------|:------|
| 14/05/26 21:49 | Log area reset/cleared | SEL was cleared on 14 May |
| 09/06/26 04:10-08:33 | **Memory #0x36 Correctable ECC** × ~40 entries | Every ~5.5 min sustained — **DIMM contact issue**, resolved by reseating |
| 09/06/26 22:32-00:01 | **Temperature alarms** × 300+ entries | GPU burn test. 3 sensors hit Non-recoverable |

### Temperature Event Summary

**Sensors affected:**

| Sensor | Max Level | Time Window |
|:-------|:----------|:------------|
| **#0x6a** (GPU adjacent) | Non-recoverable 🔴 | 22:32 → 00:01 |
| **#0xc2** (GPU) | Critical ⚠️ | 22:33 → 23:46 |
| **#0xc3** (GPU) | Non-recoverable 🔴 | 22:33 → 23:59 |
| **#0xc8** (GPU) | Non-recoverable 🔴 | 22:32 → 23:49 |
| **#0xc9** (GPU) | Critical ⚠️ | 22:33 → 23:40 |

**Duration:** ~1.5 hours (gpu_burn test)
**Recovery:** 10/06/26 00:01 — all sensors back to normal

### Resolution

- **Temperature alarm:** Normal for 4× GPU stress in single chassis. Not a hardware defect.
- **Memory ECC:** Corrected by reseating the DIMM. Errors stopped.
