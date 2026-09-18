"""work-principles plugin: full integration test suite.

Covers:
  - complete phase lifecycle (task_started → research → plan → executing
    → modifying → closing → done)
  - research gate blocking behaviour
  - modify gate blocking behaviour
  - ssh gate blocking behaviour
  - closure gate blocking behaviour
  - marker detection from assistant response only
  - session isolation across hooks
  - read-only whitelist edge cases

Run:  python3 tests/test_harness_integration.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # plugin/

import discipline.state as S
import discipline.hooks as H

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def fresh_session(sid: str = "test-sess") -> None:
    S.reset(sid)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="wp-itest-")
    S.PERSISTENT_DIR = Path(tmp)
    S.STATE_FILE = S.PERSISTENT_DIR / "state.json"

    sid = "itest-main"
    print("== 1. Phase lifecycle ==")

    # 1.1 no_task → task_started (marker in assistant response)
    fresh_session(sid)
    H.on_post_llm_call(session_id=sid, assistant_response="这是一个任务 [HARNESS: task_started]")
    st = S.get(sid)
    check("task_started entered", st["phase"] == "task_started", st["phase"])
    check("research gate active", st["research_detected"] is True)

    # 1.2 research: read-only allowed, write blocked
    r = H.on_pre_tool_call("terminal", {"command": "ls -la"}, session_id=sid)
    check("research: ls allowed", r is None, str(r))
    r = H.on_pre_tool_call("terminal", {"command": "rm -rf /tmp/x"}, session_id=sid)
    check("research: rm blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("write_file", {"path": "/tmp/x"}, session_id=sid)
    check("research: write_file blocked", r is not None and r.get("action") == "block", str(r))

    # 1.3 plan marker → planning, research cleared
    H.on_post_llm_call(session_id=sid, assistant_response="计划如下 [HARNESS: plan]")
    st = S.get(sid)
    check("planning entered", st["phase"] == "planning", st["phase"])
    check("research cleared", st["research_detected"] is False)

    # 1.4 executing: write still blocked (must go to modifying first)
    H.on_post_llm_call(session_id=sid, assistant_response="开始执行 [HARNESS: executing]")
    # Note: 'executing' is not a marker — use set_phase directly (simulating agent call)
    S.set_phase(S.Phase.EXECUTING, "agent declared executing", session_id=sid)
    r = H.on_pre_tool_call("write_file", {"path": "/tmp/x"}, session_id=sid)
    check("executing: write_file blocked", r is not None and r.get("action") == "block", str(r))

    # 1.5 modifying: write allowed
    S.set_phase(S.Phase.MODIFYING, "declared modifying", session_id=sid)
    r = H.on_pre_tool_call("write_file", {"path": "/tmp/x"}, session_id=sid)
    check("modifying: write_file allowed", r is None, str(r))

    # 1.6 closing via done marker
    H.on_post_llm_call(session_id=sid, assistant_response="完成 [HARNESS: done]")
    st = S.get(sid)
    check("closing entered", st["phase"] == "closing", st["phase"])

    # 1.7 closure gate: research tools allowed, others blocked
    r = H.on_pre_tool_call("read_file", {"path": "/x"}, session_id=sid)
    check("closing: read_file allowed", r is None, str(r))
    r = H.on_pre_tool_call("skill_manage", {"action": "create", "name": "x"}, session_id=sid)
    check("closing: skill_manage allowed", r is None, str(r))
    r = H.on_pre_tool_call("browser_navigate", {"url": "http://x"}, session_id=sid)
    check("closing: browser allowed (research tool)", r is None, str(r))
    r = H.on_pre_tool_call("execute_code", {"code": "print(1)"}, session_id=sid)
    check("closing: execute_code allowed (sandboxed stats tool)", r is None, str(r))

    # 1.8 CLOSING is a checkpoint: plan marker → continue to planning
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: plan] 下一阶段")
    st = S.get(sid)
    check("closing: plan → planning", st["phase"] == "planning", st["phase"])
    check("closing: plan clears research gate", st["research_detected"] is False)

    # 1.9 done → closing again; then done confirms → archive to no_task
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: done]")
    check("closing re-entered", S.get(sid)["phase"] == "closing")
    H.on_post_llm_call(session_id=sid, assistant_response="收尾完成 [HARNESS: done]")
    st = S.get(sid)
    check("closing: done confirms → no_task", st["phase"] == "no_task", st["phase"])

    # 1.10 closing → task_started (new task) and → casual (idle)
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: done]")
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: task_started] 新任务")
    check("closing: task_started → new task", S.get(sid)["phase"] == "task_started")
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: done]")
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: casual]")
    st = S.get(sid)
    check("closing: casual → idle", st["phase"] == "no_task", st["phase"])

    # 1.11 branch task: mid-executing task_started suspends main task
    fresh_session(sid)
    S.set_phase(S.Phase.EXECUTING, "main task in progress", sid)
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: task_started] 分支来了")
    st = S.get(sid)
    check("branch: main task suspended", st["phase"] == "task_started", st["phase"])
    check("branch: suspended stack has executing",
          st["suspended"] and st["suspended"][-1]["phase"] == "executing",
          str(st.get("suspended")))
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: done]")
    check("branch: closing after done", S.get(sid)["phase"] == "closing")
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: done]")
    st = S.get(sid)
    check("branch: done confirms → resumed executing", st["phase"] == "executing", st["phase"])
    check("branch: suspended stack drained", not st.get("suspended"), str(st.get("suspended")))

    # 1.12 casual drops suspended stack
    S.set_phase(S.Phase.EXECUTING, "main task again", sid)
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: task_started] 分支2")
    check("branch2: suspended", bool(S.get(sid).get("suspended")))
    H.on_post_llm_call(session_id=sid, assistant_response="[HARNESS: casual]")
    st = S.get(sid)
    check("casual: idle + stack dropped",
          st["phase"] == "no_task" and not st.get("suspended"), str(st))

    print("== 2. Session isolation ==")
    sid_a, sid_b = "itest-A", "itest-B"
    fresh_session(sid_a); fresh_session(sid_b)
    H.on_post_llm_call(session_id=sid_a, assistant_response="[HARNESS: task_started]")
    check("A: task_started", S.get(sid_a)["phase"] == "task_started")
    check("B: still no_task", S.get(sid_b)["phase"] == "no_task")
    H.on_post_llm_call(session_id=sid_b, assistant_response="[HARNESS: done]")
    check("B: closing", S.get(sid_b)["phase"] == "closing")
    check("A: unaffected by B", S.get(sid_a)["phase"] == "task_started")

    print("== 3. Marker NOT detected from tool output ==")
    fresh_session(sid)
    H.on_post_tool_call("read_file", {"path": "/x"}, result={"content": "[HARNESS: done]"},
                        session_id=sid)
    check("read_file output ignored", S.get(sid)["phase"] == "no_task")
    H.on_post_tool_call("terminal", {"command": "cat x"}, result={"output": "[HARNESS: plan]"},
                        session_id=sid)
    check("terminal output ignored", S.get(sid)["phase"] == "no_task")
    # session_search in NO_TASK auto-transitions to task_started (design),
    # but the marker text in its output must NOT be the cause.
    H.on_post_tool_call("session_search", {"query": "x"}, result={"content": "[HARNESS: casual]"},
                        session_id=sid)
    st = S.get(sid)
    check("session_search output not marker-triggered",
          st["phase"] == "task_started" and st["research_detected"] is True,
          str(st))

    print("== 4. Read-only whitelist ==")
    cases = [
        ("git -C /tmp/x log --oneline -3", True),
        ("git -C /tmp/x status -sb", True),
        ("git --no-pager diff HEAD~1", True),
        ("git push origin main", False),
        ("git commit -m x", False),
        ("git checkout -b new", False),
        ("psql -c \"SELECT count(*) FROM sessions\" db", True),
        ("psql -c \"SHOW tables\" db", True),
        ("psql -c \"DELETE FROM sessions\" db", False),
        ("psql -c \"DROP TABLE sessions\" db", False),
        ("curl -I https://example.com", True),
        ("curl --head https://example.com", True),
        ("curl -X POST https://example.com", False),
        ("sudo cat /etc/hosts", True),
        ("sudo systemctl restart nginx", False),
        ("nohup python3 server.py", False),
        ("docker ps -a", True),
        ("docker exec -it c bash", False),
        ("podman images", True),
        ("podman run x", False),
        ("systemctl status nginx", True),
        ("systemctl restart nginx", False),
        ("journalctl -u nginx -n 50", True),
        ("ip addr show", True),
        ("ip route", True),
        ("nmcli general status", True),
        ("nmcli device status", True),
        ("python3 --version", True),
        ("node --version", True),
        ("git --version", True),
        ("command -v python3", True),
        ("ssh user@host", False),
        ("scp file user@host:", False),
        ("rsync -av /a/ /b/", False),
        ("python3 --version", True),
    ]
    for cmd, exp in cases:
        got = H._is_read_only_command(cmd)
        check(f"ro({cmd[:44]!r})={exp}", got == exp, f"got {got}")

    print("== 5. pre_llm_call context injection ==")
    fresh_session(sid)
    S.set_phase(S.Phase.TASK_STARTED, "auto: web_search", session_id=sid)
    S.set_research_detected(sid)
    ctx = H.on_pre_llm_call(session_id=sid)
    check("context injected", ctx is not None and "phase=task_started" in str(ctx), str(ctx))
    check("research gate mentioned", "Research gate" in str(ctx), str(ctx))
    # auto_loaded_skill is one-shot: cleared after injection
    S.set_auto_loaded_skill("camofox-browser", sid)
    ctx2 = H.on_pre_llm_call(session_id=sid)
    check("auto-skill injected once", "camofox-browser" in str(ctx2), str(ctx2))
    ctx3 = H.on_pre_llm_call(session_id=sid)
    check("auto-skill cleared after injection", "camofox-browser" not in str(ctx3), str(ctx3))

    print("== 6. tool-trigger auto-skill ==")
    fresh_session(sid)
    H.on_post_tool_call("browser_navigate", {"url": "http://x"}, session_id=sid)
    check("browser→camofox-browser", S.get(sid)["auto_loaded_skill"] == "camofox-browser",
          str(S.get(sid)["auto_loaded_skill"]))
    fresh_session(sid)
    H.on_post_tool_call("skill_manage", {"action": "create", "name": "test"}, session_id=sid)
    check("skill_manage create→skill-ecosystem",
          S.get(sid)["auto_loaded_skill"] == "skill-ecosystem",
          str(S.get(sid)["auto_loaded_skill"]))
    fresh_session(sid)
    H.on_post_tool_call("terminal", {"command": "keepassxc-cli open db"}, session_id=sid)
    check("keepass→credential-store-management",
          S.get(sid)["auto_loaded_skill"] == "credential-store-management",
          str(S.get(sid)["auto_loaded_skill"]))

    print("== 7. Gate relaxations (2026-09-18, data-driven) ==")
    # 7.1 accessing_device permits local file writes (was 770 false blocks)
    fresh_session(sid)
    S.set_phase(S.Phase.ACCESSING_DEVICE, "operating remote box", sid)
    r = H.on_pre_tool_call("write_file", {"path": "/tmp/x"}, session_id=sid)
    check("accessing_device: write_file allowed", r is None, str(r))

    # 7.2 read-only remote inspection in modifying/planning/closing
    S.set_phase(S.Phase.MODIFYING, "local edits", sid)
    r = H.on_pre_tool_call("terminal", {"command": "ssh host 'tail -n 50 log.txt'"},
                           session_id=sid)
    check("modifying: ssh read-only remote allowed", r is None, str(r))
    r = H.on_pre_tool_call("terminal", {"command": "ssh host 'rm -rf /tmp/x'"},
                           session_id=sid)
    check("modifying: ssh write remote blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("terminal", {"command": "scp host:/remote/f.png ./local.png"},
                           session_id=sid)
    check("modifying: scp pull allowed", r is None, str(r))
    r = H.on_pre_tool_call("terminal", {"command": "scp ./local.png host:/remote/"},
                           session_id=sid)
    check("modifying: scp push blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("terminal", {"command": "rsync -avz host:data/ ./data/"},
                           session_id=sid)
    check("modifying: rsync pull allowed", r is None, str(r))
    r = H.on_pre_tool_call("terminal", {"command": "rsync -avz ./data/ host:data/"},
                           session_id=sid)
    check("modifying: rsync push blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("terminal", {"command": "ssh -p 2222 user@box.nb.internal \"ps -eo args | grep '[s]dxl_train'\""},
                           session_id=sid)
    check("modifying: ssh -p + quoted ro cmd allowed", r is None, str(r))
    r = H.on_pre_tool_call("terminal", {"command": "ssh host"}, session_id=sid)
    check("modifying: bare ssh blocked (interactive)", r is not None and r.get("action") == "block", str(r))
    # no_task must NOT get the read-only pass
    fresh_session(sid)
    r = H.on_pre_tool_call("terminal", {"command": "ssh host 'ls'"}, session_id=sid)
    check("no_task: ssh read-only still blocked", r is not None and r.get("action") == "block", str(r))

    # 7.3 research gate: "reach, don't enter" — investigation free,
    # mutation blocked until a plan exists
    fresh_session(sid)
    S.set_phase(S.Phase.TASK_STARTED, "new task", sid)
    S.set_research_detected(sid)
    r = H.on_pre_tool_call("execute_code", {"code": "print(1)"}, session_id=sid)
    check("research: execute_code allowed (investigation)", r is None, str(r))
    for t in ("tool_search", "tool_describe", "browser_navigate"):
        r = H.on_pre_tool_call(t, {}, session_id=sid)
        check(f"research: {t} allowed", r is None, str(r))
    r = H.on_pre_tool_call("terminal", {"command": "git status"}, session_id=sid)
    check("research: read-only terminal allowed", r is None, str(r))
    r = H.on_pre_tool_call("terminal", {"command": "rm -rf /tmp/x"}, session_id=sid)
    check("research: mutating terminal blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("write_file", {"path": "/tmp/x"}, session_id=sid)
    check("research: write_file blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("skill_manage", {"action": "create"}, session_id=sid)
    check("research: skill_manage blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("delegate_task", {"tasks": []}, session_id=sid)
    check("research: delegate_task blocked", r is not None and r.get("action") == "block", str(r))
    r = H.on_pre_tool_call("process", {"action": "poll", "session_id": "x"}, session_id=sid)
    check("research: process poll allowed", r is None, str(r))
    r = H.on_pre_tool_call("process", {"action": "kill", "session_id": "x"}, session_id=sid)
    check("research: process kill blocked", r is not None and r.get("action") == "block", str(r))

    print()
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
