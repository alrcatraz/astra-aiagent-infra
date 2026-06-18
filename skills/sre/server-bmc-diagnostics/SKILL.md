---
name: server-bmc-diagnostics
description: "Server BMC (Baseboard Management Controller) diagnostics — IPMI, Redfish, and web GUI access patterns for reading hardware health data (SEL, sensors, event logs) from enterprise server management interfaces. Companion to server-health-audit (Linux-side checks) — this covers the hardware layer."
version: 1.1.0
author: ANGELIA
platforms: [linux]
related_skills:
  - server-health-audit
  - infrastructure-device-inventory
---

# Server BMC Diagnostics

Diagnostics for server hardware via its management controller (BMC/IPMI). Use this when you need to read hardware sensor data, event logs, or identify the cause of an alarm light on a physical server.

## Triggers

- Server alarm/fault/attention light is blinking
- Server has standby power but **won't POST or power on** (power button LED flashing)
- User asks to "check the BMC", "read the IPMI", or "look at hardware logs"
- Pre-delivery hardware health verification
- Unexplained server behavior that might be thermal, power, or memory related
- After `gpu_burn`, `stress-ng`, or other hardware stress tests that triggered thermal events

## Pre-Boot / Power-On Failure Diagnostics

Diagnosing servers that receive standby power (BMC alive, PSU LED on) but won't POST or boot. This is a separate class of problem from runtime diagnostics — you can't reach IPMI/Redfish because the main system never started.

### Power Button LED Pattern Interpretation

When the server won't power on, the power button LED (or motherboard-mounted status LED) is the first clue:

| LED Behavior | Likely Cause (General) | Vendor-Specific Notes |
|:-------------|:-----------------------|:----------------------|
| **Off entirely** | No standby power — PSU dead, power cord loose, breaker tripped, PSU not fully seated | — |
| **Solid green (standby) → stays solid green when power pressed** | Power button signal not reaching motherboard — button broken, front-panel header loose, BMC hung on a stale state | Try clearing CMOS, or power-cycle the entire server (disconnect AC for 30s) |
| **Solid green → **green flashing** when power pressed** (most common failure pattern) | **PSU or power delivery issue** — improperly seated PSU(s), insufficient power, PSU fault, loose CPU EPS 12V cable, or main 24-pin ATX not fully inserted | **Gigabyte/技嘉 server boards** (official troubleshooting): green blinking power LED = "Improperly seated or faulty power supply, loose or faulty power cord, power source issue" |
| **Solid green → turns off when power pressed** | Short-circuit protection triggered by a faulty component — commonly a shorted capacitor on the motherboard, a mis-seated CPU, or a PCIe riser card with a short | Remove all add-in cards, then try. If still dead, remove motherboard from chassis (standoff short). |
| **Solid green → all LEDs flash briefly then off** | PSU overcurrent protection (OCP) — a component draws more inrush current than the PSU can deliver | Disconnect all drives and PCIe devices first — if it POSTs, the culprit is among the peripherals |

**Key insight:** If the power LED transitions from solid (standby) to **flashing** when you press the power button, the BMC received the power-on signal and attempted the power-up sequence, but the main power rail (ATX PWR_OK / PS_PWRGD) never stabilized. This is almost always a power delivery path issue — PSU, cables, or CPU power delivery.

### Step-by-Step Diagnostic Procedure

Follow this **dependency order** (lowest level first):

1. **🔌 Check all PSU connections**
   - Reseat the PSU(s) fully — push in until the latch clicks
   - Verify the AC power cord is fully inserted at both ends
   - Test with a different wall outlet / PDU port
   - **For redundant PSUs:** try with only one PSU connected (swap which one)

2. **🔋 Check motherboard power cables**
   - Reseat the **24-pin ATX main power** connector — push firmly, it often feels seated when it isn't
   - Reseat the **CPU EPS 12V (4+4 pin or 8 pin)** connector — this is the most common culprit. Even slightly loose, the board won't power on
   - Check for bent pins in the EPS connector

3. **💡 Verify BMC is alive independently**
   - Plug an Ethernet cable into the **dedicated BMC/IPMI management port**
   - Check if the management port's link LED lights up (indicates BMC has networking)
   - Try to get an IP (DHCP) or reach the default IPMI IP
   - If the BMC management port gets link, the standby power rail is good — the problem is in the main power-up sequence (ATX power good, CPU voltage regulator, etc.)

4. **🧹 Minimal boot test**
   - Remove everything non-essential:
     - All drives (SATA/SAS/NVMe)
     - All PCIe cards (GPU, RAID, NIC)
     - All but **one DIMM** in slot A0 (check manual for correct single-DIMM slot)
     - All front-panel connectors except power switch
     - All fan headers except CPU fan (some boards refuse to POST without CPU fan)
   - If it POSTs, add components back one at a time

5. **🔄 Clear CMOS / NVRAM**
   - Locate the CLR_CMOS jumper on the motherboard
   - With AC power disconnected, short the jumper for 10 seconds
   - Alternatively, remove the CMOS battery for 1 minute
   - Reconnect AC and try again

6. **🔍 Check CPU installation**
   - SP3 / LGA3647 / LGA4189 sockets are sensitive to uneven pressure
   - Remove the heatsink, check for bent socket pins, re-seat the CPU
   - Apply fresh thermal paste (old paste may have hardened and lifted the heatsink slightly)

7. **🏗️ Bench test (last resort)**
   - Remove the motherboard from the chassis and place on a non-conductive surface (cardboard box)
   - Connect only: PSU, one DIMM, CPU + cooler, and a case speaker
   - Short the power switch pins with a screwdriver
   - Listen for POST beeps — they tell you where the boot process stops

### After power-on failure is resolved

Once the server POSTs and you can reach the BMC:

- **Check the SEL immediately** — it may contain a `Power Unit #0x50 Power off/down` or `Power Supply #0x5b AC lost` event from the failed startup attempt
- Run the standard `server-health-audit` or IPMI sensor check to confirm all voltage rails are stable
- Document which step resolved the issue for future reference

### Vendor-Specific Notes

| Vendor | Known Pattern | Reference |
|:-------|:--------------|:----------|
| **Gigabyte/技嘉** | Green blinking power LED = PSU issue | Gigabyte Server Trouble Shooting page (microsite) |
| **Supermicro** | Flashing BMC LED usually means BMC is alive and waiting; power-on failure often traces to power cables or CPU | Supermicro forums |
| **Huawei/xFusion** | Power-on failure often traces to PMem FW mismatch (MRC 0x1710) or CPU EPS connection | See `intel-optane-pmem` and `optane-pmem-firmware-management` skills |
| **Dell PowerEdge** | Solid amber = fault; blinking amber on power button = PSU or system board | iDRAC SEL is the definitive source |
| **HPE ProLiant** | Health LED 4-flash = PSU failure; 3-flash = system board | iLO event log

## Methods Overview

| Method | Port | Protocol | What You Get | When to Use || Health LED 4-flash = PSU failure; 3-flash = system board | iLO event log

## Methods Overview

| Method | Port | Protocol | What You Get | When to Use |
|:-------|:----:|:---------|:-------------|:------------|
| **IPMI (ipmitool)** | UDP 623 | IPMI v2.0 RMCP+ | Full SEL, sensor readings, power state, FRU | Most complete — always try this first |
| **Redfish REST API** | HTTPS 443 | REST/JSON | DMTF-standard health summary, Firmware info, indicator LED | Programmatic queries, when no IPMI |
| **Web GUI** | HTTP 80 / HTTPS 443 | HTML | Visual dashboard | Last resort / manual inspection |

**Key Insight:** Redfish's `EventLog` is NOT the same as IPMI's `SEL` (System Event Log). SEL is the hardware "black box" — it records every sensor threshold crossing, chassis event, and power transition. Redfish EventLog may only record subset events. **If Redfish EventLog is empty, always fall back to IPMI SEL.**

## Access Patterns

### Prerequisites: ipmitool Installation

On the jump host (e.g., SUSET01 X1 Tablet):

```bash
# openSUSE
sudo zypper install -y ipmitool
# RHEL/Fedora
sudo dnf install -y ipmitool
# Debian/Ubuntu
sudo apt install -y ipmitool
```

For systems without `sudo` TTY (SSH remote command), use:
```bash
ssh -t <user>@<jump-host> "sudo zypper install -y ipmitool"
```
If even `-t` fails, use the terminal tool's `pty=true` mode for interactive auth.

### Read SEL (System Event Log) — The Primary Diagnostic

```bash
# Via jump host: read BMC SEL
ssh <user>@<jump-host> \
  "ipmitool -I lanplus -H <bmc-ip> -U <bmc-user> -P <bmc-pass> sel list"

# Read with date filtering (show last N entries)
ssh <user>@<jump-host> \
  "ipmitool -I lanplus -H <bmc-ip> -U <bmc-user> -P <bmc-pass> sel list | tail -50"
```

**Credentials:** Do NOT embed passwords in terminal commands or memory. Fetch from GPG file with the headless-safe pattern:

```bash
# Source passphrase from .env, extract via grep
source <(grep 'GPG_Key_Alrcatraz' ~/.hermes/.env)
echo "$GPG_Key_Alrcatraz" | gpg --batch --no-tty --passphrase-fd 0 \
  --pinentry-mode loopback --decrypt <file> 2>/dev/null | grep <key>
```

### Read Sensor Data

```bash
# All sensors (names + readings + thresholds)
ssh <user>@<jump-host> \
  "ipmitool -I lanplus -H <bmc-ip> -U <bmc-user> -P <bmc-pass> sdr"

# Just temperature sensors
ssh <user>@<jump-host> \
  "ipmitool -I lanplus -H <bmc-ip> -U <bmc-user> -P <bmc-pass> sensor list | grep -i temp"
```

### Redfish REST API (Alternative)

For environments without IPMI or when you need JSON output:

```bash
# Health summary
curl -sku <user>:<pass> https://<bmc-ip>/redfish/v1/Managers/BMC

# System overview
curl -sku <user>:<pass> https://<bmc-ip>/redfish/v1/Systems/Self

# SEL — NOTE: this is the Path-Specific SEL endpoint, not EventLog!
curl -sku <user>:<pass> https://<bmc-ip>/redfish/v1/Managers/BMC/LogServices/SEL/Entries/

# EventLog (may be incomplete — always check IPMI if this is empty)
curl -sku <user>:<pass> https://<bmc-ip>/redfish/v1/Managers/BMC/LogServices/EventLog/Entries/
```

## SEL Interpretation Guide

### SEL Entry Format

```
<id> | <date> | <time> | <sensor-type> #<sensor-id> | <event-desc> | <state>
```

- **State: Asserted** = event started (e.g., temperature went high)
- **State: Deasserted** = event ended (e.g., temperature came back down)

### Common Sensor Types and Their Meaning

| Sensor Hex ID | Type | Common Aliases |
|:-------------|:-----|:---------------|
| `#0x6a` | Temperature (CPU/GPU adjacent) | Often GPU inlet or near-GPU zone |
| `#0xc2-0xcf` | Temperature (GPU) | Per-GPU sensors on multi-GPU systems |
| `#0x36, #0xa9` | Memory | DIMM ECC (Correctable/Uncorrectable) |
| `#0x50` | Power Unit | Power on/off/down events |
| `#0x56` | Physical Security | Chassis intrusion (open/close) |
| `#0x58-0x5b` | Power Supply | AC lost, failure detected |
| `#0x5d` | Battery | CMOS/RAID battery present |
| `#0x60-0x67` | Fan | Device present, speed, fault |

### Temperature Event Levels (ascending severity)

| Level | Meaning |
|:------|:--------|
| **Upper Non-critical** | Warning — approaching threshold, fan speed increasing |
| **Upper Critical** | ⚠️ Reached critical threshold — immediate risk, alarm light may activate |
| **Upper Non-recoverable** | 🚨 Highest level — hardware may shut down to prevent damage |

### Temperate alarm pattern: what to look for

- A single high-severity entry is less concerning than **sustained oscillating** (Assert → Deassert repeatedly over minutes)
- Multiple different sensors hitting Critical simultaneously = systemic airflow/cooling issue
- A spike followed by quick recovery = transient (e.g., test load ending)
- Sustained Critical + Non-recoverable oscillation = **thermal event confirmed**, investigate cooling

**Real-world example** (from a 4× GPU server under `gpu_burn`):

```
# Starting overheating at 22:32
69 | 09/06/26 | 22:32:35 HKT | Temperature #0x6a | Upper Non-critical going high | Asserted
70 | 09/06/26 | 22:35:11 HKT | Temperature #0x6a | Upper Critical going high | Asserted
74 | 09/06/26 | 22:39:33 HKT | Temperature #0xc2 | Upper Critical going high | Deasserted

# Non-recoverable peaks
99 | 09/06/26 | 22:46:28 HKT | Temperature #0x6a | Upper Non-recoverable going high | Asserted
10b | 09/06/26 | 23:13:59 HKT | Temperature #0xc3 | Upper Non-recoverable going high | Asserted
116 | 09/06/26 | 23:15:18 HKT | Temperature #0xc8 | Upper Non-recoverable going high | Asserted

# Recovery
1f3 | 10/06/26 | 00:01:02 HKT | Temperature #0xc8 | Upper Non-critical going high | Deasserted
```

This pattern: ~1.5 hours of heavy GPU load, 3 sensors hit Non-recoverable, then all returned to normal after load stopped. **Normal behavior for 4× GPU stress test in a single-chassis server — not a hardware fault.**

### Memory ECC Pattern

**Correctable ECC** (single-bit error, auto-corrected by hardware):

```
20 | 09/06/26 | 04:10:02 HKT | Memory #0x36 | Correctable ECC | Asserted
```

- **What it means:** Memory had a bit error but ECC fixed it silently
- **Frequency matters:** One every few hours = normal. Every 5 minutes = DIMM instability (likely contact oxidation or failing RAM)
- **Resolution:** Reseat the DIMM (remove, clean contacts, reinsert). If ECC errors stop, it was contact-related. If they continue, replace the DIMM.
- **Uncorrectable ECC** (not seen in this session) = 🚨 Crash risk, replace DIMM immediately

### Watchdog Timer / Reset Pattern

A distinct class of BMC event where the **system boots normally but resets after a fixed interval** (e.g., 4–16 minutes). This is **not** a crash — it's the BMC's Watchdog Timer (WDT) triggering a hardware reset because no software is "feeding" it.

**Key SEL signature — OEM Record Type codes:**
```
OEM Record 0xdf | 000137|0400000000000  — 生成警告    ← WDT pre-timeout (about to reset)
OEM Record 0xdf | 000137|0500000000000  — 生成警告    ← WDT timeout, system reset
#0x00 | OS 引导                          — C: 加载完成 ← POST/boot after reset
```

**Watchdog cycle pattern (from real IBM server SEL):**

| Time | Event | Meaning |
|------|-------|---------|
| 09:33:09 | OEM `040` | Watchdog pre-timeout — software hasn't fed the dog |
| 09:33:09 | OEM `050` | Watchdog timeout — BMC asserts system reset |
| 09:33:13 | OS 引导 `C: 加载完成` | System boots... and the cycle repeats |
| 09:49:49 | OEM `040` + `050` | Reset cycle repeats at regular interval |

**How to read this pattern:**
- ✅ **POST passes** — no hardware fault preventing boot
- ✅ **OS loads** — disk and filesystem are intact
- ❌ **System resets after N minutes** — the watchdog timer is armed but no software is feeding it

**Root causes (in order of likelihood):**

| Cause | Why | Proof |
|:------|:----|:------|
| **1. BMC WDT enabled, no OS watchdog driver** | BMC has a watchdog timer enabled with a timeout (e.g. 10 minutes). Windows/Linux needs a management agent (IBM DPC, Dell OMSA, HP Health Driver) to feed the watchdog at boot. If the agent is missing/uninstalled, WDT fires. | System resets even at BIOS/boot menu if left idle for the timeout period. |
| **2. Watchdog driver installed but not running** | The OS-side service that feeds the watchdog failed to start. | System boots OK but resets after the timeout once the OS should have started feeding. |
| **3. OS crashes without logging to SEL** | The OS hard-locks (not a clean crash that generates a SEL entry), so BMC WDT catches it. | Less likely — usually leaves a crash dump in the OS. |
| **4. Hardware brown-out** | PSU capacitor aging — voltage dips under sustained load. | Usually shows other power-related SEL entries. |

**Diagnostic procedure:**

1. **Check if the system resets at the BIOS/boot menu** — leave it at the POST screen or boot manager. If it resets there too, it's definitely **BMC WDT** (no OS involved). If it only resets after the OS starts, it could be #2 or #3.

2. **Enter BMC configuration** — Look for `Watchdog Timer`, `OS Watchdog`, or `BMC Watchdog Configuration` in the BMC web GUI under `Configuration` or `Maintenance`. Default action may be "Reset System".

3. **Resolution:**
   - **Disable BMC watchdog** in the configuration (set to `Disabled` or `No Action`) — immediate fix
   - **Install the vendor management agent** — e.g., IBM DPC/Director, Dell OMSA, HP iLO health driver — these feed the watchdog at OS boot
   - **Check for BIOS settings** that enable "OS Watchdog Timer" — some servers have this in BIOS setup, not just BMC

### Power/Cycle Events

```
5 | 14/05/26 | 21:50:21 HKT | Power Unit #0x50 | Power off/down | Asserted
6 | 14/05/26 | 21:50:25 HKT | Power Supply #0x5b | Power Supply AC lost | Asserted
```

- **On multi-NUMA systems**, sequential is the reliable approach

## Reference Files

- `references/bmc-192-168-100-27-sel-example.md` — Full SEL example with thermal event pattern
- `references/watchdog-sel-pattern-ibm-example.md` — Raw SEL extract showing BMC watchdog timeout cycle (040/050 OEM codes) on an IBM E3/E5 server
- `references/sas3508-raid-oce-expansion.md` — Broadcom SAS3508 (MegaRAID Tri-Mode) Online Capacity Expansion: which RAID levels support adding drives, constraints, and StorCLI commands

## Pitfalls

### 1. Diagnose from the Data You Already Have

**Critical lesson:** Before diving into BMC logs, check if you already have measurement data that explains the symptom.

This session's example:
- You ran `gpu_burn` and saw **4 cards all hit 85°C thermal throttle boundary**
- Server alarm light started blinking
- **Direct connection:** The alarm light IS the temperature alarm from your own test

The correct approach is:
```
Test data (85°C, thermal throttle) → "this explains the alarm light" → done
```
Instead of:
```
Test data collected → ignore it → BMC Redfish rabbit hole → SEL confirmation → "oh, it was the temperature"
```

**Rule:** If you generated test data that stresses hardware, check that data for the root cause before going to management interfaces.

### 2. Redfish EventLog ≠ IPMI SEL

Redfish EventLog may be empty while SEL is full. Always try IPMI first.

### 3. Temperature Events Are NOT Hardware Failures

A thermal alarm under sustained GPU load is a **normal safety response**, not a component failure. Only treat it as a defect if:
- Temperature alarms occur at idle (no load)
- A single sensor is 10°C+ above all others (bad TIM / cooler mounting)
- Fans fail while temperature is elevated

### 4. BMC Access Requires Network Separation Check

Servers with BMC expose a **separate management IP** that may be on a different VLAN/subnet than the server's OS IP. The BMC typically has ports 80/443 (web) and 623 (IPMI). The server's OS has port 22 (SSH). Verify you're reaching the right IP.

### 5. Credential Discipline

- **Never** store BMC passwords in memory, skills, or terminal commands
- Reference credentials to the GPG-encrypted credential files (see local reference index → credential storage specification)
- Fetch with `gpg --batch --decrypt --pinentry-mode loopback <file> | grep <key>` (headless safe — `--pinentry-mode loopback` + `.env` passphrase is the verified pattern for GPG 2.5+)

### 6. SEL Can Be Cleared by Logistics

If you see very few entries (e.g., only power-on events), the SEL was likely cleared during shipping/installation. Run `ipmitool sel list` right after a stress test to capture current data.

## Verifying BMC is Alive

```bash
# Ping test (from jump host that shares the management network)
ping -c 3 <bmc-ip>

# Check ports (BMC should have 623 open)
ssh <jump-host> "timeout 3 bash -c 'echo >/dev/tcp/<bmc-ip>/623' 2>/dev/null && echo 'Port 623 open' || echo 'Port 623 closed'"
```

## Credential Reference

BMC credentials are grouped under **work** credentials in the GPG-encrypted file system:
- See local reference index → credential storage specification for file locations and groups
- Key ID: Alrcatraz <alrcatraz@gmx.com> (ultimate trust)
- Headless access pattern (GPG 2.5+):

  ```bash
  # Store passphrase in .env (export GPG_Key_Alrcatraz=your_passphrase)
  source <(grep 'GPG_Key_Alrcatraz' ~/.hermes/.env)
  echo "$GPG_Key_Alrcatraz" | gpg --batch --no-tty --passphrase-fd 0 \
    --pinentry-mode loopback --decrypt <file> 2>/dev/null | grep <key>
  ```

  Note: `--pinentry-mode loopback` is REQUIRED for headless GPG access on GPG 2.5+. Without it, gpg-agent blocks waiting for a GUI pinentry that never comes.
