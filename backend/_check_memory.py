"""Temp script to check all memories in the system."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests

# 1. Get all projects
r = requests.get("http://localhost:8000/api/projects")
projects = r.json()
print("=== 项目列表 ===")
for p in projects:
    print(f"  {p['id']} | {p['name']}")

print()
print("=" * 60)
print("=== 各项目记忆详情 ===")
print("=" * 60)

# 2. Get memories for each project
for p in projects:
    pid = p["id"]
    r2 = requests.get(f"http://localhost:8000/api/memories/{pid}?include_global=true")
    memories = r2.json()
    if memories:
        print(f"\n--- Project: {p['name']} ({len(memories)} 条记忆) ---")
        for i, m in enumerate(memories, 1):
            source = f"{m['source_mode']}/{m['source_phase']}" if m["source_phase"] else m["source_mode"]
            content = m['content'].replace('\u2011', '-')
            print(f"  {i:2d}. [{source}] {content}")
            if m.get("related_blocks"):
                print(f"      -> related: {m['related_blocks']}")
    else:
        print(f"\n--- Project: {p['name']} (无记忆) ---")

# 3. Check global memories
print()
print("=" * 60)
r3 = requests.get("http://localhost:8000/api/memories/_global")
global_mems = r3.json()
if global_mems:
    print(f"=== 全局记忆 ({len(global_mems)} 条) ===")
    for i, m in enumerate(global_mems, 1):
        print(f"  {i:2d}. [{m['source_mode']}] {m['content']}")
else:
    print("=== 无全局记忆 ===")
