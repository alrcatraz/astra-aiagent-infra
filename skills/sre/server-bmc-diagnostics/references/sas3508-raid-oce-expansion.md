# Broadcom SAS3508 (MegaRAID Tri-Mode) — Online Capacity Expansion

> Broadcom 12Gb/s MegaRAID Tri-Mode series (SAS3508/3408 chipset, e.g. 9460-8i/16i, 9440-8i).
> Source: [Broadcom KB 1211161503168](https://www.broadcom.com/support/knowledgebase/1211161503168/)

## Which RAID Levels Can Expand by Adding Drives

| RAID Level | Can Add Drives? | Minimum Drives to Add | Notes |
|:-----------|:---------------:|:---------------------:|:------|
| **RAID 0** | ✅ Yes | 1 | Simple stripe expansion |
| **RAID 1** | ✅ Yes | 2 | Must add in pairs (new mirror leg) |
| **RAID 5** | ✅ Yes | 1 | Most common expansion scenario |
| **RAID 6** | ✅ Yes | 1 | Dual parity also expandable |
| **RAID 00** | ❌ No | — | Striped stripe — cannot modify |
| **RAID 10** | ❌ No | — | Multi-span: Broadcom prohibits modification |
| **RAID 50** | ❌ No | — | Multi-span |
| **RAID 60** | ❌ No | — | Multi-span |

## Critical Constraints

1. **One Virtual Drive per Drive Group** — If the array (drive group) contains more than one VD, expansion is impossible. Must backup → delete array → recreate with all drives → restore.
2. **No mixed use** — A drive group with a boot span + data span cannot be modified.
3. **OCE online** — Expansion runs while the system is online; the array enters a reconstruction state during which I/O performance degrades.
4. **Backup REQUIRED** — Broadcom: *"Always create a backup prior to Hardware / Software changes."*

## Alternative: Replace with Larger Drives

Also supported: replace existing drives one by one with larger-capacity drives. The controller automatically rebuilds onto each new drive, then OCE expands into the freed space.

## StorCLI Commands

```bash
# Check current virtual drive info
storcli /c0 /v0 show

# Preview expansion feasibility
storcli /c0 /v0 show expansion

# Expand: add free space from new drives to v0
# expandarray = also extend the underlying array (required when adding new drives)
storcli /c0 /v0 expand size=<new_total_size> expandarray

# For RAID levels that CANNOT expand (10/50/60):
# Must: backup → delete VD → create new VD with all drives → restore
storcli /c0 /v0 delete
storcli /c0 add vd type=r10 drives=<all_drive_enclosures:slots>
```

## Huawei Documentation Reference

Huawei's RAID controller documentation (which uses Avago SAS3508 in their servers) confirms two modes:
1. **Add new drives** to existing RAID array (RAID 0/1/5/6 only)
2. **Replace with larger drives** (all RAID levels, assumes OCE supports the new geometry)
