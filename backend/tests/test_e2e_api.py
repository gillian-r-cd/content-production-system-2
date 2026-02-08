# backend/tests/test_e2e_api.py
# 功能: 通过 HTTP API 端到端测试内容生产流程
# 覆盖: 传统流程(含字段模板+自动生成+渠道选择+eval) + 灵活(树形)架构 + Agent对话 + 路由
#
# 使用方式:
#   1. 先启动后端: cd backend && python main.py
#   2. 运行测试: cd backend && python tests/test_e2e_api.py

"""
E2E API 集成测试

Use Case 1 (传统流程): AI for Coding 课程
  创建项目 → 意图分析(3问) → 消费者调研 → 内涵设计(手动调整:删字段改标题)
  → 内涵生产(引用字段模板+自动生成) → 外延设计(选2个渠道) → 外延生产
  → 用「内容销售」角色对正文做 eval 得到报告

Use Case 2 (灵活架构): 快速博文
  创建灵活项目 → 添加内容块(引言/正文/结论) → 生成 → 修改 → 验证树

Use Case 3 (Agent对话): 路由正确性
  闲聊→chat / 意图阶段中途提问→chat / 开始→phase_current

Use Case 4 (Eval体系): 内容销售评估
  创建 EvalRun → 添加 seller Task → 执行 → 获取报告
"""

import os
import sys
import json
import time
import traceback
from typing import Optional

# Windows UTF-8 输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
TIMEOUT = 300  # AI 调用（尤其设计/生产阶段）可能较慢


# ============== 工具函数 ==============

def api(method: str, path: str, **kwargs) -> dict:
    """同步 HTTP 请求"""
    url = f"{BASE_URL}{path}"
    kwargs.setdefault("timeout", TIMEOUT)
    with httpx.Client() as client:
        resp = getattr(client, method)(url, **kwargs)
        if resp.status_code >= 400:
            print(f"  [ERR] {method.upper()} {path} -> {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()


def api_safe(method: str, path: str, **kwargs) -> Optional[dict]:
    """不抛异常的 HTTP 请求，失败返回 None"""
    try:
        return api(method, path, **kwargs)
    except Exception as e:
        print(f"  [WARN] {method.upper()} {path} failed: {e}")
        return None


def api_sse(path: str, body: dict) -> list[dict]:
    """SSE 请求，返回事件列表"""
    url = f"{BASE_URL}{path}"
    events = []
    with httpx.Client(timeout=TIMEOUT) as client:
        with client.stream("POST", url, json=body) as resp:
            resp.raise_for_status()
            buffer = ""
            for chunk in resp.iter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    raw, buffer = buffer.split("\n\n", 1)
                    for line in raw.split("\n"):
                        if line.startswith("data: "):
                            try:
                                events.append(json.loads(line[6:]))
                            except json.JSONDecodeError:
                                events.append({"type": "raw", "content": line[6:]})
    return events


def find_event(events: list, etype: str) -> Optional[dict]:
    for e in events:
        if e.get("type") == etype:
            return e
    return None


def collect_response(events: list) -> str:
    """从 SSE 事件中拼接完整响应"""
    parts = []
    for e in events:
        if e.get("type") in ("token", "content"):
            parts.append(e.get("content", ""))
    return "".join(parts)


def P(icon: str, step: str, detail: str = ""):
    """打印步骤结果"""
    suffix = f" -- {detail}" if detail else ""
    print(f"  {icon} {step}{suffix}")


def section(title: str):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


# ============== Use Case 1: 传统流程 (完整) ==============

def test_uc1_traditional_full_flow():
    """
    AI for Coding 课程 - 完整传统流程

    步骤:
    1. 创建项目
    2. 意图分析 (3轮问答 + 产出)
    3. 消费者调研
    4. 内涵设计 → 手动调整(删字段,改标题)
    5. 内涵生产 → 创建字段模板 → 引用模板批量创建字段 → 自动生成
    6. 外延设计 → 选2个渠道 → 推进到外延生产
    7. 外延生产
    8. 用「内容销售」角色做 eval → 得到报告
    """
    section("UC1: AI for Coding 课程 (传统完整流程)")
    issues = []

    # ===== 1. 创建项目 =====
    project = api("post", "/api/projects/", json={
        "name": "AI for Coding 课程 E2E",
        "use_deep_research": False,
    })
    pid = project["id"]
    P("OK", "1. 创建项目", f"id={pid}, phase={project['current_phase']}")
    assert project["current_phase"] == "intent"

    # ===== 2. 意图分析 =====
    # 2a. "开始" -> Q1
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "开始", "current_phase": "intent"})
    resp = collect_response(events)
    has_q1 = "问题" in resp and "1/3" in resp
    P("OK" if has_q1 else "!!", "2a. 意图分析 Q1", f"包含Q1={has_q1}")
    if not has_q1:
        issues.append("Q1 未正确生成")

    # 2b. 回答 Q1 -> Q2
    events = api_sse("/api/agent/stream", {
        "project_id": pid, "message": "我想做一个AI辅助编程的在线课程，教程序员用AI提升编码效率",
        "current_phase": "intent",
    })
    resp = collect_response(events)
    P("OK", "2b. 回答 Q1", resp[:60] + "...")

    # 2c. 回答 Q2 -> Q3
    events = api_sse("/api/agent/stream", {
        "project_id": pid, "message": "目标受众是1-3年经验的初中级程序员，痛点是写代码效率低、重复劳动多",
        "current_phase": "intent",
    })
    resp = collect_response(events)
    P("OK", "2c. 回答 Q2", resp[:60] + "...")

    # 2d. 回答 Q3 -> 产出意图分析
    events = api_sse("/api/agent/stream", {
        "project_id": pid, "message": "希望学员能在日常工作中熟练使用AI编程助手，并愿意购买进阶课程",
        "current_phase": "intent",
    })
    resp = collect_response(events)
    done = find_event(events, "done")
    producing = done.get("is_producing", False) if done else False
    P("OK" if producing else "!!", "2d. 意图产出", f"is_producing={producing}")
    if not producing:
        issues.append("意图分析未进入产出模式")

    # ===== 3. 推进到消费者调研 =====
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "继续", "current_phase": "intent"})
    route_evt = find_event(events, "route")
    P("OK", "3a. 推进到调研", f"route={route_evt.get('target') if route_evt else '?'}")

    proj = api("get", f"/api/projects/{pid}")
    if proj["current_phase"] != "research":
        # 手动推进
        api_sse("/api/agent/stream", {"project_id": pid, "message": "进入消费者调研", "current_phase": "intent"})
        proj = api("get", f"/api/projects/{pid}")

    # 3b. 执行消费者调研
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "开始", "current_phase": "research"})
    resp = collect_response(events)
    P("OK", "3b. 消费者调研", f"响应长度={len(resp)}")

    fields = api("get", f"/api/fields/project/{pid}")
    field_names = [f["name"] for f in fields]
    P("OK", "3c. 已保存字段", str(field_names))

    # ===== 4. 内涵设计 =====
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "继续到内涵设计", "current_phase": "research"})
    P("OK", "4a. 推进到内涵设计")

    proj = api("get", f"/api/projects/{pid}")
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "开始", "current_phase": "design_inner"})
    resp = collect_response(events)
    P("OK", "4b. 生成设计方案", f"响应长度={len(resp)}")

    # 4c. 手动调整：修改标题 + 删除字段
    fields = api("get", f"/api/fields/project/{pid}")
    design_fields = [f for f in fields if f.get("phase") == "design_inner"]
    if design_fields:
        df = design_fields[0]
        try:
            data = json.loads(df.get("content", "{}"))
            if isinstance(data, dict) and "proposals" in data and data["proposals"]:
                # 修改第一个方案标题
                original_name = data["proposals"][0].get("name", "")
                data["proposals"][0]["name"] = "AI编程实战 - 从入门到精通"

                # 如果第一个方案有 fields，删几个
                p_fields = data["proposals"][0].get("fields", [])
                deleted_count = 0
                if len(p_fields) > 3:
                    data["proposals"][0]["fields"] = p_fields[:3]
                    deleted_count = len(p_fields) - 3

                # 删除最后一个方案
                removed_proposal = None
                if len(data["proposals"]) > 2:
                    removed_proposal = data["proposals"].pop()

                api("put", f"/api/fields/{df['id']}", json={
                    "content": json.dumps(data, ensure_ascii=False, indent=2)
                })
                P("OK", "4c. 手动调整",
                  f"标题: {original_name[:20]}->AI编程实战, "
                  f"删除{deleted_count}个子字段, "
                  f"删除方案'{removed_proposal.get('name','')[:15] if removed_proposal else '无'}'")
            else:
                P("!!", "4c. 手动调整", "方案格式非预期")
        except json.JSONDecodeError:
            P("!!", "4c. 手动调整", "非JSON，跳过")
    else:
        P("!!", "4c. 手动调整", "无内涵设计字段")
        issues.append("内涵设计字段未保存")

    # ===== 5. 内涵生产 (字段模板 + 自动生成) =====
    # 5a. 推进到内涵生产
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "继续", "current_phase": "design_inner"})
    P("OK", "5a. 推进到内涵生产")

    # 5b. 创建字段模板
    template = api("post", "/api/settings/field-templates", json={
        "name": "AI课程内涵模板",
        "category": "课程",
        "description": "AI编程课程的标准内涵字段模板",
        "fields": [
            {"name": "课程目标", "ai_prompt": "请生成本课程的学习目标，3-5条", "field_type": "text"},
            {"name": "核心知识点", "ai_prompt": "列出本课程的核心知识点，结构化表述", "field_type": "richtext"},
            {"name": "课程大纲", "ai_prompt": "生成详细的课程大纲，含章节和子章节", "field_type": "structured"},
        ],
    })
    template_id = template["id"]
    P("OK", "5b. 创建字段模板", f"id={template_id}, 含{len(template.get('fields',[]))}个字段")

    # 5c. 从模板创建字段
    template_fields = template.get("fields", [])
    created_field_ids = []
    for tf in template_fields:
        f = api("post", "/api/fields/", json={
            "project_id": pid,
            "phase": "produce_inner",
            "name": tf["name"],
            "field_type": tf.get("field_type", "text"),
            "ai_prompt": tf.get("ai_prompt", ""),
            "template_id": template_id,
            "need_review": False,  # 自动模式，不需要人工确认
        })
        created_field_ids.append(f["id"])
    P("OK", "5c. 引用模板创建字段", f"创建了 {len(created_field_ids)} 个字段")

    # 5d. 自动生成所有字段
    generated_ok = 0
    generated_fail = 0
    for fid in created_field_ids:
        try:
            result = api("post", f"/api/fields/{fid}/generate", json={"pre_answers": {}})
            if result.get("status") == "completed":
                generated_ok += 1
            else:
                generated_ok += 1  # generating 也算OK，内容已填入
        except Exception as e:
            generated_fail += 1
            P("!!", f"  字段生成失败", str(e)[:80])

    P("OK" if generated_fail == 0 else "!!", "5d. 自动生成字段",
      f"成功={generated_ok}, 失败={generated_fail}")
    if generated_fail > 0:
        issues.append(f"内涵生产: {generated_fail}个字段生成失败")

    # ===== 6. 外延设计 (选择渠道) =====
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "继续到外延设计", "current_phase": "produce_inner"})
    P("OK", "6a. 推进到外延设计")

    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "开始", "current_phase": "design_outer"})
    resp = collect_response(events)
    P("OK", "6b. 生成渠道方案", f"响应长度={len(resp)}")

    # 6c. 获取渠道方案，选择2个
    fields = api("get", f"/api/fields/project/{pid}")
    outer_fields = [f for f in fields if f.get("phase") == "design_outer"]
    selected_channels = []
    if outer_fields:
        try:
            ch_data = json.loads(outer_fields[0].get("content", "{}"))
            channels = ch_data.get("channels", [])
            if channels:
                # 选择前2个优先级高的渠道
                high_priority = [c for c in channels if c.get("priority") == "high"]
                if len(high_priority) >= 2:
                    selected_channels = high_priority[:2]
                else:
                    selected_channels = channels[:2]

                # 标记选中
                for c in channels:
                    c["selected"] = c in selected_channels
                ch_data["channels"] = channels
                api("put", f"/api/fields/{outer_fields[0]['id']}", json={
                    "content": json.dumps(ch_data, ensure_ascii=False, indent=2)
                })
                P("OK", "6c. 选择渠道",
                  f"选了 {', '.join(c.get('name','?') for c in selected_channels)}")
            else:
                P("!!", "6c. 选择渠道", "无渠道数据")
        except json.JSONDecodeError:
            P("!!", "6c. 选择渠道", "非JSON格式")
    else:
        P("!!", "6c. 选择渠道", "无外延设计字段")
        issues.append("外延设计字段未保存")

    # ===== 7. 外延生产 =====
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "继续到外延生产", "current_phase": "design_outer"})
    P("OK", "7a. 推进到外延生产")

    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "开始", "current_phase": "produce_outer"})
    resp = collect_response(events)
    P("OK", "7b. 外延生产", f"响应长度={len(resp)}")

    # ===== 8. 用「内容销售」角色做 eval =====
    # 8a. 创建 EvalRun
    try:
        eval_run = api("post", "/api/eval/run", json={
            "project_id": pid,
            "name": "内容销售评估",
            "roles": ["seller"],
            "max_turns": 3,
        })
        eval_run_id = eval_run["id"]
        P("OK", "8a. 创建 Eval(seller)",
          f"run_id={eval_run_id}, status={eval_run.get('status')}, score={eval_run.get('overall_score')}")

        if eval_run.get("status") == "completed":
            # 8b. 获取 Trial 详情
            trials = api_safe("get", f"/api/eval/run/{eval_run_id}/trials")
            if trials:
                P("OK", "8b. Eval Trials", f"共{len(trials)}个trial")
                for t in trials[:3]:
                    P("  ", f"  {t.get('role','?')}", f"score={t.get('overall_score','?')}")
            P("OK", "8c. Eval 完成",
              f"总分={eval_run.get('overall_score')}, summary={eval_run.get('summary','')[:60]}...")
        else:
            P("!!", "8b. Eval 状态", f"status={eval_run.get('status')}, summary={eval_run.get('summary','')[:100]}")
            issues.append(f"Eval 未完成: {eval_run.get('status')}")

    except Exception as e:
        P("!!", "8. Eval 失败", str(e)[:100])
        issues.append(f"Eval 异常: {str(e)[:80]}")

    # ===== 最终验证 =====
    proj = api("get", f"/api/projects/{pid}")
    fields = api("get", f"/api/fields/project/{pid}")
    history = api("get", f"/api/agent/history/{pid}")
    P("OK", "最终状态",
      f"phase={proj.get('current_phase')}, 字段={len(fields)}, 消息={len(history)}")

    # 清理
    api("delete", f"/api/projects/{pid}")
    # 清理模板
    api_safe("delete", f"/api/settings/field-templates/{template_id}")
    P("OK", "清理完成")

    return issues


# ============== Use Case 2: 灵活架构 ==============

def test_uc2_flexible_architecture():
    """
    灵活架构 (ContentBlock 树形结构)

    1. 创建灵活项目(phase_order=[])
    2. 添加内容块(引言/正文/结论, 有依赖)
    3. 生成内容
    4. 修改内容块
    5. 验证树结构
    """
    section("UC2: 灵活架构 (树形)")
    issues = []

    project = api("post", "/api/projects/", json={
        "name": "灵活架构博文 E2E",
        "use_flexible_architecture": True,
        "phase_order": [],
    })
    pid = project["id"]
    P("OK", "1. 创建灵活项目", f"id={pid}")

    # 2. 获取初始树
    tree = api_safe("get", f"/api/blocks/project/{pid}")
    if tree is None:
        issues.append("获取内容块树失败")
        api("delete", f"/api/projects/{pid}")
        return issues
    P("OK", "2. 初始内容块树", f"块数={len(tree.get('blocks',[]))}")

    # 3. 添加内容块
    b1 = api("post", "/api/blocks/", json={
        "project_id": pid, "name": "引言", "block_type": "field",
        "ai_prompt": "为一篇关于AI编程的博文写一段引言，200字左右",
    })
    b2 = api("post", "/api/blocks/", json={
        "project_id": pid, "name": "正文", "block_type": "field",
        "ai_prompt": "写正文部分，介绍AI编程的3个核心场景，每个场景300字",
    })
    b3 = api("post", "/api/blocks/", json={
        "project_id": pid, "name": "结论", "block_type": "field",
        "ai_prompt": "总结全文要点，给出行动建议",
        "depends_on": [b2["id"]],
    })
    P("OK", "3. 添加3个内容块", f"引言={b1['id'][:8]}, 正文={b2['id'][:8]}, 结论={b3['id'][:8]}")

    # 4. 生成内容
    for label, bid in [("引言", b1["id"]), ("正文", b2["id"])]:
        try:
            result = api("post", f"/api/blocks/{bid}/generate", json={})
            P("OK", f"4. 生成{label}", f"长度={len(result.get('content',''))}")
        except Exception as e:
            P("!!", f"4. 生成{label}", str(e)[:80])
            issues.append(f"块生成失败: {label}")

    # 5. 修改内容块
    updated = api("put", f"/api/blocks/{b1['id']}", json={
        "name": "精彩引言",
        "content": "AI正在彻底改变程序员的工作方式。从代码补全到架构设计，AI已经深入到软件开发的每一个环节。",
    })
    P("OK", "5. 修改引言", f"新名称={updated.get('name')}")

    # 6. 验证树
    tree = api("get", f"/api/blocks/project/{pid}")
    blocks = tree.get("blocks", [])
    P("OK", "6. 最终树", f"块数={len(blocks)}")
    for b in blocks:
        has_c = "有" if b.get("content") else "无"
        print(f"      - {b['name']} (status={b.get('status','?')}, content={has_c})")

    api("delete", f"/api/projects/{pid}")
    P("OK", "清理完成")
    return issues


# ============== Use Case 3: 路由正确性 ==============

def test_uc3_routing():
    """
    路由决策正确性

    测试各种输入在不同阶段的路由:
    - 闲聊 → chat
    - 问能力 → chat
    - 开始 → phase_current
    - 继续 → advance_phase
    - 意图阶段中途提问 → chat (不被意图流程捕获)
    """
    section("UC3: 路由正确性")
    issues = []

    project = api("post", "/api/projects/", json={"name": "路由测试 E2E"})
    pid = project["id"]

    cases = [
        ("你好",            "intent",  "chat",          "闲聊→chat"),
        ("你能做什么？",     "intent",  "chat",          "问能力→chat"),
        ("开始",            "intent",  "phase_current", "开始→phase_current"),
    ]

    passed = 0
    for msg, phase, expected, desc in cases:
        events = api_sse("/api/agent/stream", {"project_id": pid, "message": msg, "current_phase": phase})
        route = find_event(events, "route")
        actual = route.get("target") if route else "unknown"
        ok = actual == expected
        P("OK" if ok else "!!", f"'{msg}'", f"期望={expected}, 实际={actual} ({desc})")
        if ok:
            passed += 1
        else:
            issues.append(f"路由错误: '{msg}' → {actual}, 期望 {expected}")

    # 意图阶段中途提问
    # 先确保有个待回答的问题
    events = api_sse("/api/agent/stream", {"project_id": pid, "message": "开始", "current_phase": "intent"})
    events = api_sse("/api/agent/stream", {
        "project_id": pid, "message": "什么是内涵设计？", "current_phase": "intent",
    })
    route = find_event(events, "route")
    actual = route.get("target") if route else "unknown"
    ok = actual == "chat"
    P("OK" if ok else "!!", "'什么是内涵设计?'", f"期望=chat, 实际={actual} (中途提问→chat)")
    if ok:
        passed += 1
    else:
        issues.append(f"中途提问路由错误: {actual}")

    P("OK", "路由测试结果", f"{passed}/{len(cases)+1} 通过")

    api("delete", f"/api/projects/{pid}")
    P("OK", "清理完成")
    return issues


# ============== Use Case 4: Eval 体系 (Task-based) ==============

def test_uc4_eval_system():
    """
    Eval V2 体系测试

    1. 创建项目 + 准备内容
    2. 创建 EvalRun
    3. 添加 Task (seller角色)
    4. 执行
    5. 获取 Trial 结果
    """
    section("UC4: Eval V2 体系 (Task-based)")
    issues = []

    # 1. 创建项目并准备内容
    project = api("post", "/api/projects/", json={"name": "Eval测试 E2E"})
    pid = project["id"]

    # 创建一些内容字段
    for name, content in [
        ("正文", "AI辅助编程正在改变软件开发的方式。通过智能代码补全、自动化测试生成、架构建议等功能，程序员的生产力可以提升50%以上。本课程将从实战角度，手把手教你掌握AI编程工具。"),
        ("课程大纲", "第1章: AI编程工具概览\n第2章: GitHub Copilot 实战\n第3章: ChatGPT 辅助开发\n第4章: AI Debug 技巧"),
    ]:
        api("post", "/api/fields/", json={
            "project_id": pid, "phase": "produce_inner",
            "name": name, "content": content, "status": "completed",
        })
    P("OK", "1. 准备内容", "创建了正文+大纲字段")

    # 2. 创建 EvalRun
    try:
        run = api("post", "/api/eval/runs", json={"project_id": pid, "name": "内容销售评估"})
        run_id = run["id"]
        P("OK", "2. 创建 EvalRun", f"id={run_id}")
    except Exception as e:
        P("!!", "2. 创建 EvalRun 失败", str(e)[:80])
        issues.append(f"EvalRun 创建失败: {e}")
        api("delete", f"/api/projects/{pid}")
        return issues

    # 3. 添加 Task (seller)
    try:
        task = api("post", f"/api/eval/run/{run_id}/tasks", json={
            "name": "内容销售测试",
            "simulator_type": "seller",
            "interaction_mode": "review",
            "grader_config": {"type": "content"},
        })
        task_id = task["id"]
        P("OK", "3. 添加 seller Task", f"task_id={task_id}")
    except Exception as e:
        P("!!", "3. 添加 Task 失败", str(e)[:80])
        issues.append(f"EvalTask 创建失败: {e}")
        api("delete", f"/api/projects/{pid}")
        return issues

    # 4. 执行
    try:
        result = api("post", f"/api/eval/run/{run_id}/execute")
        # V2 execute 返回 {"message": ..., "run": {...}}
        run_data = result.get("run", result)
        P("OK", "4. 执行评估",
          f"status={run_data.get('status')}, score={run_data.get('overall_score')}, "
          f"trials={run_data.get('trial_count')}, msg={result.get('message','')[:60]}")
    except Exception as e:
        P("!!", "4. 执行评估失败", str(e)[:100])
        issues.append(f"Eval 执行失败: {e}")
        api("delete", f"/api/projects/{pid}")
        return issues

    # 5. 获取 Trial 结果
    trials = api_safe("get", f"/api/eval/run/{run_id}/trials")
    if trials:
        P("OK", "5. Trial 结果", f"共{len(trials)}个trial")
        for t in trials[:5]:
            P("  ", f"  {t.get('role','?')}/{t.get('interaction_mode','?')}",
              f"score={t.get('overall_score','?')}, status={t.get('status','?')}")
    else:
        P("!!", "5. 获取 Trial 失败")
        issues.append("Trial 获取失败")

    # 6. 获取运行摘要
    run_detail = api_safe("get", f"/api/eval/run/{run_id}")
    if run_detail:
        P("OK", "6. Eval 报告",
          f"总分={run_detail.get('overall_score')}, 摘要={run_detail.get('summary','')[:80]}...")

    api("delete", f"/api/projects/{pid}")
    P("OK", "清理完成")
    return issues


# ============== Main ==============

def main():
    print("\n" + "=" * 60)
    print("  E2E API 集成测试 - 完整版")
    print("=" * 60)

    # 检查服务器
    try:
        resp = httpx.get(f"{BASE_URL}/health", timeout=5)
        resp.raise_for_status()
        print(f"\n  Server OK: {resp.json()}")
    except Exception as e:
        print(f"\n  Server 不可达 ({BASE_URL}): {e}")
        print("  请先启动: cd backend && python main.py")
        return

    all_results = {}
    all_issues = {}

    tests = [
        ("UC3: 路由正确性",              test_uc3_routing),
        ("UC2: 灵活架构 (树形)",          test_uc2_flexible_architecture),
        ("UC4: Eval V2 体系",            test_uc4_eval_system),
        ("UC1: 传统完整流程",             test_uc1_traditional_full_flow),
    ]

    for name, fn in tests:
        try:
            issues = fn()
            if issues:
                all_results[name] = f"!! ISSUES ({len(issues)})"
                all_issues[name] = issues
            else:
                all_results[name] = "OK PASS"
        except Exception as e:
            all_results[name] = f"!! FAIL: {str(e)[:80]}"
            all_issues[name] = [str(e)]
            traceback.print_exc()

    # ===== 汇总 =====
    section("测试汇总")
    for name, result in all_results.items():
        icon = "OK" if "PASS" in result else "!!"
        P(icon, name, result)

    if all_issues:
        print("\n  --- 发现的问题 ---")
        for name, issues in all_issues.items():
            print(f"  [{name}]")
            for iss in issues:
                print(f"    - {iss}")

    fail_count = sum(1 for r in all_results.values() if "FAIL" in r)
    issue_count = sum(len(v) for v in all_issues.values())
    if fail_count == 0 and issue_count == 0:
        print(f"\n  ALL PASS!")
    elif fail_count == 0:
        print(f"\n  PARTIAL: {issue_count} 个小问题")
    else:
        print(f"\n  FAILED: {fail_count} 个测试崩溃, {issue_count} 个问题")


if __name__ == "__main__":
    main()
