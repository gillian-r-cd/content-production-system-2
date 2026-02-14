"""Test design_inner pre-question flow"""
import requests
import json
import sys

BASE = "http://localhost:8000"

# Get project
r = requests.get(f"{BASE}/api/projects")
pid = r.json()[0]["id"]
print(f"Project: {pid}")

# Check current state
r2 = requests.get(f"{BASE}/api/fields/project/{pid}")
fields = r2.json()
pref = [f for f in fields if f["phase"] == "design_inner" and f["name"] == "设计偏好"]
design = [f for f in fields if f["phase"] == "design_inner" and f["name"] == "内涵设计方案"]

print(f"Design preference exists: {len(pref) > 0}")
print(f"Design proposals field exists: {len(design) > 0}")

has_proposals = False
if design:
    try:
        d = json.loads(design[0]["content"])
        has_proposals = bool(d.get("proposals"))
        print(f"  Has proposals array: {has_proposals}, count: {len(d.get('proposals', []))}")
    except Exception:
        print("  Content is not valid JSON")

# To test the pre-question flow, we need NO proposals and NO preference
# Since existing project already has proposals, let's just verify the logic paths
if has_proposals:
    print("\n[INFO] Project already has proposals. Pre-question will NOT trigger (correct behavior).")
    print("[INFO] To test the pre-question flow, create a new project and go to design_inner phase.")
    print("[INFO] Verifying that normal routing works with existing proposals...")
    
    # Quick test: send a chat message in design_inner phase - should route normally
    payload = {
        "project_id": pid,
        "message": "你好，帮我看看当前方案",
        "current_phase": "design_inner",
        "references": []
    }
    r3 = requests.post(f"{BASE}/api/agent/stream", json=payload, stream=True, timeout=30)
    print(f"Stream status: {r3.status_code}")
    collected = ""
    for line in r3.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            data = json.loads(line[6:])
            t = data.get("type", "?")
            if t == "token":
                collected += data.get("content", "")
            elif t == "route":
                print(f"[route] {data.get('target', '?')}")
            elif t == "done":
                print(f"[done] route={data.get('route', '?')}")
                break
            elif t == "error":
                print(f"[error] {data.get('error', '?')}")
                break
    print(f"Response preview: {collected[:200]}")
else:
    print("\n[INFO] No proposals exist. Pre-question should trigger.")
    payload = {
        "project_id": pid,
        "message": "开始",
        "current_phase": "design_inner",
        "references": []
    }
    r3 = requests.post(f"{BASE}/api/agent/stream", json=payload, stream=True, timeout=60)
    print(f"Stream status: {r3.status_code}")
    collected = ""
    for line in r3.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            data = json.loads(line[6:])
            t = data.get("type", "?")
            if t == "token":
                collected += data.get("content", "")
            elif t == "content":
                print(f"[content] {data.get('content', '')[:200]}")
            elif t == "route":
                print(f"[route] {data.get('target', '?')}")
            elif t == "done":
                print(f"[done] route={data.get('route', '?')}")
                break
            elif t == "error":
                print(f"[error] {data.get('error', '?')}")
                break
    if collected:
        print(f"Response: {collected[:300]}")

print("\nDone.")
