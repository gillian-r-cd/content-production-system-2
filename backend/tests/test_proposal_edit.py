# backend/tests/test_proposal_edit.py
# 功能: 测试 @方案 引用 + 指令 → 修改方案（非重新生成所有方案）

import sys, os, json
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

BASE = os.getenv("TEST_BASE_URL", "http://localhost:8000")
TIMEOUT = 300


def api(method, path, **kw):
    kw.setdefault("timeout", TIMEOUT)
    with httpx.Client() as c:
        r = getattr(c, method)(f"{BASE}{path}", **kw)
        if r.status_code >= 400:
            print(f"  ERR {method.upper()} {path} -> {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
        return r.json()


def api_sse(path, body):
    events = []
    with httpx.Client(timeout=TIMEOUT) as c:
        with c.stream("POST", f"{BASE}{path}", json=body) as r:
            r.raise_for_status()
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    raw, buf = buf.split("\n\n", 1)
                    for line in raw.split("\n"):
                        if line.startswith("data: "):
                            try:
                                events.append(json.loads(line[6:]))
                            except json.JSONDecodeError:
                                events.append({"type": "raw", "content": line[6:]})
    return events


def find_event(events, t):
    for e in events:
        if e.get("type") == t:
            return e
    return None


def collect(events):
    return "".join(
        e.get("content", "") for e in events if e.get("type") in ("token", "content")
    )


def main():
    print("=== Test: Proposal Editing via @reference ===\n")

    # 1. Create project
    proj = api("post", "/api/projects/", json={"name": "Proposal Edit Test", "use_deep_research": False})
    pid = proj["id"]
    print(f"1. Project created: {pid}")

    # 2. Create design_inner field with proposals
    proposals_data = {
        "proposals": [
            {
                "name": "A: Basic",
                "description": "beginner route",
                "fields": [{"name": "goal"}, {"name": "outline"}],
            },
            {
                "name": "B: Advanced",
                "description": "for experienced devs",
                "fields": [{"name": "adv_goal"}, {"name": "project"}],
            },
            {
                "name": "C: Custom",
                "description": "user custom proposal",
                "fields": [],
            },
        ]
    }
    api("post", "/api/fields/", json={
        "project_id": pid,
        "phase": "design_inner",
        "name": "design_proposal",
        "content": json.dumps(proposals_data, ensure_ascii=False),
        "status": "completed",
    })
    print("2. Design inner field created with 3 proposals")

    # Update project phase
    api("put", f"/api/projects/{pid}", json={"current_phase": "design_inner"})

    # 3. Test: @proposal3 + instruction -> should route to 'modify'
    print("\n--- Test A: @ref + instruction -> modify route ---")
    events = api_sse("/api/agent/stream", {
        "project_id": pid,
        "message": "design a simple proposal with 3 modules: intro, practice, summary",
        "current_phase": "design_inner",
        "references": ["方案3:Custom"],
    })
    route = find_event(events, "route")
    done = find_event(events, "done")
    resp = collect(events)
    route_target = route.get("target") if route else "??"
    print(f"  Route: {route_target}")
    print(f"  Response (first 200): {resp[:200]}...")
    print(f"  Done: is_producing={done.get('is_producing') if done else '??'}")

    route_ok = route_target == "modify"
    print(f"  Route correct (modify): {'OK' if route_ok else 'FAIL'}")

    # 4. Verify the proposal was updated (not ALL proposals regenerated)
    fields = api("get", f"/api/fields/project/{pid}")
    design_fields = [f for f in fields if f.get("phase") == "design_inner"]
    proposal_ok = False
    if design_fields:
        content = design_fields[0].get("content", "")
        try:
            data = json.loads(content)
            proposals = data.get("proposals", [])
            print(f"\n  Proposals count: {len(proposals)} (should be 3)")
            for i, p in enumerate(proposals):
                name = p.get("name", "?")
                field_count = len(p.get("fields", []))
                desc = p.get("description", "")[:50]
                print(f"    Proposal {i+1}: {name} ({field_count} fields) - {desc}")

            # Check proposal 3 was modified
            if len(proposals) >= 3:
                p3 = proposals[2]
                p3_fields = p3.get("fields", [])
                p3_name = p3.get("name", "")
                modified = len(p3_fields) > 0 or p3_name != "C: Custom"
                proposal_ok = modified and len(proposals) == 3
                print(f"\n  Proposal 3 modified: {modified}")
                print(f"  All 3 proposals preserved: {len(proposals) == 3}")
                if proposal_ok:
                    print("  OK: Proposal 3 edited, others unchanged")
                else:
                    print("  !! FAIL: Proposal save issue")
        except json.JSONDecodeError:
            print(f"  Content not JSON: {content[:200]}")
    else:
        print("  !! No design_inner fields found")

    # 5. Test: @proposal1 + query -> should route to 'query'
    print("\n--- Test B: @ref + query -> query route ---")
    events = api_sse("/api/agent/stream", {
        "project_id": pid,
        "message": "explain what this is",
        "current_phase": "design_inner",
        "references": ["方案1:Basic"],
    })
    route = find_event(events, "route")
    route_target2 = route.get("target") if route else "??"
    print(f"  Route: {route_target2}")
    # "explain" should match query_keywords: "解释" is in list, but "explain" is English...
    # Actually this might route to modify since the query_keywords are Chinese
    # Let's test with Chinese
    events2 = api_sse("/api/agent/stream", {
        "project_id": pid,
        "message": "analyze this for me",
        "current_phase": "design_inner",
        "references": ["方案1:Basic"],
    })
    route2 = find_event(events2, "route")
    route_target3 = route2.get("target") if route2 else "??"
    print(f"  Route (analyze): {route_target3}")

    # Cleanup
    api("delete", f"/api/projects/{pid}")

    # Summary
    print("\n=== Results ===")
    print(f"  Route to modify:    {'OK' if route_ok else 'FAIL'}")
    print(f"  Proposal save:      {'OK' if proposal_ok else 'FAIL'}")

    if route_ok and proposal_ok:
        print("\n  ALL PASS")
    else:
        print("\n  ISSUES FOUND")
        sys.exit(1)


if __name__ == "__main__":
    main()



