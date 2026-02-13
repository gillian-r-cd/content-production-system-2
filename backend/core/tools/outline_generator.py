# backend/core/tools/outline_generator.py
# 功能: 内容大纲生成工具
# 主要函数: generate_outline(), apply_outline_to_project()
# 数据结构: OutlineNode, ContentOutline

"""
内容大纲生成工具

根据项目意图和消费者调研生成结构化的内容大纲：
1. 分析项目上下文
2. 生成嵌套的大纲结构
3. 为每个节点生成 AI 提示词
4. 可将大纲应用为项目字段
"""

import json
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, ProjectField
from langchain_core.messages import SystemMessage, HumanMessage

from core.llm import llm
from core.tools.architecture_reader import get_project_architecture


@dataclass
class OutlineNode:
    """大纲节点"""
    id: str = ""
    name: str = ""
    description: str = ""
    ai_prompt: str = ""
    depends_on: List[str] = field(default_factory=list)
    children: List["OutlineNode"] = field(default_factory=list)
    order_index: int = 0
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]


@dataclass
class ContentOutline:
    """内容大纲"""
    title: str
    summary: str
    content_type: str  # 课程、文章、视频脚本等
    nodes: List[OutlineNode] = field(default_factory=list)
    estimated_fields: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转为字典"""
        def node_to_dict(node: OutlineNode) -> Dict:
            return {
                "id": node.id,
                "name": node.name,
                "description": node.description,
                "ai_prompt": node.ai_prompt,
                "depends_on": node.depends_on,
                "order_index": node.order_index,
                "children": [node_to_dict(c) for c in node.children],
            }
        
        return {
            "title": self.title,
            "summary": self.summary,
            "content_type": self.content_type,
            "nodes": [node_to_dict(n) for n in self.nodes],
            "estimated_fields": self.estimated_fields,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentOutline":
        """从字典创建"""
        def dict_to_node(d: Dict) -> OutlineNode:
            return OutlineNode(
                id=d.get("id", ""),
                name=d.get("name", ""),
                description=d.get("description", ""),
                ai_prompt=d.get("ai_prompt", ""),
                depends_on=d.get("depends_on", []),
                order_index=d.get("order_index", 0),
                children=[dict_to_node(c) for c in d.get("children", [])],
            )
        
        return cls(
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            content_type=data.get("content_type", ""),
            nodes=[dict_to_node(n) for n in data.get("nodes", [])],
            estimated_fields=data.get("estimated_fields", 0),
        )


# 内容类型到大纲结构的映射
CONTENT_TYPE_TEMPLATES = {
    "课程": {
        "typical_sections": ["课程目标", "课程大纲", "核心知识点", "实践案例", "作业设计"],
        "structure_hint": "按章节组织，每章包含知识点和练习",
    },
    "文章": {
        "typical_sections": ["核心论点", "论据分析", "案例佐证", "行动建议"],
        "structure_hint": "按论点-论据-结论的逻辑展开",
    },
    "视频脚本": {
        "typical_sections": ["开场Hook", "内容主体", "互动环节", "结尾CTA"],
        "structure_hint": "注意节奏和观众注意力曲线",
    },
    "产品介绍": {
        "typical_sections": ["痛点引入", "解决方案", "核心功能", "使用场景", "社会证明", "行动号召"],
        "structure_hint": "按AIDA模型组织",
    },
    "培训材料": {
        "typical_sections": ["学习目标", "知识框架", "案例分析", "实操练习", "考核评估"],
        "structure_hint": "确保理论与实践结合",
    },
}


async def generate_outline(
    project_id: str,
    content_type: str = "",
    structure_hint: str = "",
    db: Optional[Session] = None,
) -> ContentOutline:
    """
    根据项目上下文生成内容大纲
    
    Args:
        project_id: 项目ID
        content_type: 内容类型（课程、文章、视频等）
        structure_hint: 结构提示
        db: 数据库会话
    
    Returns:
        ContentOutline
    """
    if db is None:
        db = next(get_db())
    
    # 获取项目上下文
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ContentOutline(
            title="错误",
            summary="项目不存在",
            content_type="unknown",
        )
    
    # 获取 Golden Context
    gc = project.golden_context or {}
    intent = gc.get("intent", "")
    creator_profile = gc.get("creator_profile", "")
    consumer_personas = gc.get("consumer_personas", [])
    
    # 自动推断内容类型（如果未指定）
    if not content_type:
        content_type = _infer_content_type(intent)
    
    # 获取内容类型模板
    type_template = CONTENT_TYPE_TEMPLATES.get(content_type, {})
    typical_sections = type_template.get("typical_sections", [])
    default_hint = type_template.get("structure_hint", "")
    
    # 构建提示词
    system_prompt = f"""你是一个专业的内容架构师。请根据项目信息生成结构化的内容大纲。

## 项目信息
- 内容类型: {content_type}
- 创作者特质: {creator_profile}
- 项目意图: {intent}
- 目标用户: {json.dumps(consumer_personas, ensure_ascii=False) if consumer_personas else '待定义'}

## 大纲要求
{structure_hint or default_hint}

典型板块参考（可调整）: {', '.join(typical_sections) if typical_sections else '自由设计'}

## 输出格式
请以 JSON 格式输出大纲，结构如下：
```json
{{
    "title": "大纲标题",
    "summary": "大纲概述（1-2句话）",
    "nodes": [
        {{
            "name": "板块名称",
            "description": "板块描述",
            "ai_prompt": "生成该板块内容时的AI提示词",
            "depends_on": ["依赖的其他板块名称"],
            "children": [
                {{
                    "name": "子板块名称",
                    "description": "子板块描述",
                    "ai_prompt": "AI提示词",
                    "depends_on": []
                }}
            ]
        }}
    ]
}}
```

规则：
1. 大纲应该逻辑清晰、层次分明
2. ai_prompt 要具体明确，能指导AI生成内容
3. depends_on 列出该板块需要依赖的前置板块
4. children 用于嵌套子板块（如章节下的小节）
5. 根据项目特点决定是否需要嵌套

只输出JSON，不要其他解释。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="请生成内容大纲"),
    ]
    
    response = await llm.ainvoke(messages)
    
    # 解析响应
    try:
        content = response.content.strip()
        # 提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        data = json.loads(content)
        
        # 构建大纲对象
        outline = ContentOutline.from_dict(data)
        outline.content_type = content_type
        
        # 计算字段数
        def count_nodes(nodes: List[OutlineNode]) -> int:
            count = len(nodes)
            for n in nodes:
                count += count_nodes(n.children)
            return count
        
        outline.estimated_fields = count_nodes(outline.nodes)
        
        return outline
        
    except Exception as e:
        return ContentOutline(
            title="大纲生成失败",
            summary=f"解析错误: {str(e)}\n\n原始输出:\n{response.content[:500]}",
            content_type=content_type,
        )


async def apply_outline_to_project(
    project_id: str,
    outline: ContentOutline,
    target_phase: str = "produce_inner",
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    将大纲应用到项目（创建字段）
    
    Args:
        project_id: 项目ID
        outline: 大纲对象
        target_phase: 目标阶段
        db: 数据库会话
    
    Returns:
        应用结果
    """
    if db is None:
        db = next(get_db())
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"success": False, "error": "项目不存在"}
    
    if target_phase not in project.phase_order:
        return {"success": False, "error": f"阶段 {target_phase} 不存在"}
    
    created_fields = []
    
    def create_fields_from_nodes(
        nodes: List[OutlineNode], 
        parent_names: List[str] = None,
        order_start: int = 0
    ) -> int:
        """递归创建字段"""
        nonlocal created_fields
        order = order_start
        
        for node in nodes:
            # 构建字段名称（带层级前缀）
            if parent_names:
                full_name = f"{'.'.join(parent_names)}.{node.name}"
            else:
                full_name = node.name
            
            # 创建 ProjectField
            field = ProjectField(
                id=str(uuid.uuid4()),
                project_id=project_id,
                phase=target_phase,
                name=full_name,
                field_type="text",
                ai_prompt=node.ai_prompt,
                dependencies={"depends_on": node.depends_on},
                status="pending",
                need_review=False,
            )
            db.add(field)
            created_fields.append(field.name)
            
            order += 1
            
            # 递归处理子节点
            if node.children:
                new_parent = (parent_names or []) + [node.name]
                order = create_fields_from_nodes(node.children, new_parent, order)
        
        return order
    
    try:
        create_fields_from_nodes(outline.nodes)
        db.commit()
        
        return {
            "success": True,
            "message": f"已创建 {len(created_fields)} 个字段",
            "fields": created_fields,
        }
        
    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}


def _infer_content_type(intent: str) -> str:
    """根据意图推断内容类型"""
    intent_lower = intent.lower() if intent else ""
    
    keywords = {
        "课程": ["课程", "培训", "教学", "学习", "教程"],
        "文章": ["文章", "博客", "专栏", "分析", "观点"],
        "视频脚本": ["视频", "脚本", "短视频", "vlog", "直播"],
        "产品介绍": ["产品", "介绍", "landing", "落地页", "官网"],
        "培训材料": ["培训", "手册", "指南", "操作"],
    }
    
    for content_type, kws in keywords.items():
        if any(kw in intent_lower for kw in kws):
            return content_type
    
    return "文章"  # 默认类型
