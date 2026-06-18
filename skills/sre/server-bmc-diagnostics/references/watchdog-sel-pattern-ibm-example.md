# Watchdog Timer SEL Pattern — Raw Example (IBM E3/E5 Server)

## Context

**Server:** IBM x86 E3/E5-era (DDR3), ~2020+ platform
**BMC:** PERMICR web interface (IBM branded)
**OS:** Windows Server 2019
**Symptom:** System boots fine to WinRE, but resets automatically after ~4–16 minutes

## Raw SEL Extract

```
Max=512, Used=200 → 218 entries

# Row # | Date/Time           | OEM Record Type | OEM SEL Record  | Description
121     | 2020/06/09 18:51:59  | 0xdf            |                 | 000137|0500000000000 - 生成警告
122     | 2026/06/09 18:52:03  | #0x00           | OS 引导         | C: 加载完成 - 生成警告
123     | 2026/06/09 18:58:48  | 0xdf            | OEM SEL Record  | 000137|0400000000000 - 生成警告
124     | 2026/06/09 18:58:49  | 0xdf            | OEM SEL Record  | 000137|0500000000000 - 生成警告
125     | 2026/06/09 18:58:52  | #0x00           | OS 引导         | C: 加载完成 - 生成警告
126     | 2026/06/09 19:02:30  | 0xdf            | OEM SEL Record  | 000137|0400000000000 - 生成警告
127     | 2026/06/09 19:02:30  | 0xdf            | OEM SEL Record  | 000137|0500000000000 - 生成警告
128     | 2026/06/09 19:03:26  | #0x00           | OS 引导         | C: 加载完成 - 生成警告
187     | 2026/06/09 20:46:39  | OEM Record Type | OEM SEL Record  | 000137|0500000000000 - 生成警告
188     | 2026/06/09 20:46:45  | #0x00           | OS 引导         | C: 加载完成 - 生成警告
189     | 2026/06/09 20:53:03  | OEM Record Type | OEM SEL Record  | 000137|0500000000000 - 生成警告
190     | 2026/06/09 20:53:03  | #0x00           | OS 引导         | C: 加载完成 - 生成警告
191     | 2026/06/09 20:53:07  | #0x00           | OEM SEL Record  | 000137|0400000000000 - 生成警告
192     | 2026/06/09 20:57:18  | OEM Record Type | OEM SEL Record  | 000137|0500000000000 - 生成警告
193     | 2026/06/09 20:57:18  | OEM Record Type | OEM SEL Record  | (cut off)
```

## Code Interpretation

| Code in hex | Interpretation |
|:------------|:---------------|
| `000137\|0400000000000` | Watchdog pre-timeout alert — BMC warning that the watchdog timer is about to expire |
| `000137\|0500000000000` | Watchdog timeout — BMC forcibly resets the system |
| `#0x00` | Standard OS Boot Record (generic POST/boot completion) |

## Notes

- Row 121 timestamp shows **2020** — likely BMC RTC battery was low at some point, then NTP-corrected. All subsequent entries show correct 2026 date.
- 040 always precedes or coincides with 050 → watchdog pre-timeout fires just before the actual reset.
- OS 引导 always follows the 050 → system successfully POSTs and starts booting Windows.
- The cycle repeats every ~4–7 minutes (or ~16 minutes, varying with boot + idle time), which matches the WDT timeout period.
- Anomaly: row 121's 050 has no corresponding 040 — could be the initial WDT enable event (one-shot enable).

## WinRE (Windows Recovery Environment) State

The server lands in WinRE after a few failed boots. From the screen:
- "选择一个选项" → "疑难解答" → "高级选项"
- Available: 启动修复, 卸载更新, 命令提示符, 系统还原

The watchdog reset happens **during boot** before Windows can fully load its watchdog-feeding driver/service.
