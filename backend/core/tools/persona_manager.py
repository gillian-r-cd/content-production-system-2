# backend/core/tools/persona_manager.py
# 功能: 人物小传管理工具
# 主要函数: manage_persona(), create_persona(), update_persona(), select_persona()
# 数据结构: Persona, PersonaOperation

"""
人物小传管理工具

提供 Agent 管理消费者人物小传的能力：
1. 创建新人物
2. 更新人物信息
3. 选择/取消选择用于模拟的人物
4. 根据画像生成人物
"""

import json
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Project, ProjectField
from core.models.content_block import ContentBlock
from core.ai_client import ai_client, ChatMessage


class PersonaOperation(str, Enum):
    """人物操作类型"""
    CREATE = "create"
    UPDATE = "update"
    SELECT = "select"
    DESELECT = "deselect"
    GENERATE = "generate"
    LIST = "list"
    DELETE = "delete"


@dataclass
class Persona:
    """人物小传"""
    id: str = ""
    name: str = ""
    basic_info: Dict[str, Any] = field(default_factory=dict)
    background: str = ""
    pain_points: List[str] = field(default_factory=list)
    behaviors: List[str] = field(default_factory=list)
    selected: bool = True
    
    def __post_init__(self):
        if not self.id:
            self.id = f"persona_{uuid.uuid4().hex[:8]}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "basic_info": self.basic_info,
            "background": self.background,
            "pain_points": self.pain_points,
            "behaviors": self.behaviors,
            "selected": self.selected,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Persona":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            basic_info=data.get("basic_info", {}),
            background=data.get("background", ""),
            pain_points=data.get("pain_points", []),
            behaviors=data.get("behaviors", []),
            selected=data.get("selected", True),
        )


@dataclass
class PersonaResult:
    """操作结果"""
    success: bool
    message: str
    persona: Optional[Persona] = None
    personas: Optional[List[Persona]] = None
    error: Optional[str] = None


def _get_research_field(project_id: str, db: Session) -> Optional[ProjectField]:
    """获取消费者调研报告字段"""
    return db.query(ProjectField).filter(
        ProjectField.project_id == project_id,
        ProjectField.name == "消费者调研报告"
    ).first()


def _get_persona_block(project_id: str, db: Session) -> Optional[ContentBlock]:
    """获取目标消费者画像的 ContentBlock（eval_persona_setup handler）"""
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.special_handler == "eval_persona_setup",
        ContentBlock.deleted_at.is_(None),
    ).first()


def _get_research_block(project_id: str, db: Session) -> Optional[ContentBlock]:
    """获取消费者调研的 ContentBlock（research handler）"""
    return db.query(ContentBlock).filter(
        ContentBlock.project_id == project_id,
        ContentBlock.special_handler == "research",
        ContentBlock.deleted_at.is_(None),
    ).first()


def _parse_personas(content: str) -> List[Persona]:
    """从调研报告内容中解析人物列表"""
    try:
        data = json.loads(content)
        personas_data = data.get("personas", [])
        return [Persona.from_dict(p) for p in personas_data]
    except:
        return []


def _save_personas(field: ProjectField, personas: List[Persona], db: Session):
    """保存人物列表到调研报告"""
    try:
        data = json.loads(field.content or "{}")
        data["personas"] = [p.to_dict() for p in personas]
        field.content = json.dumps(data, ensure_ascii=False, indent=2)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e


def _sync_personas_to_blocks(project_id: str, personas: List[Persona], db: Session):
    """将 personas 同步到相关的 ContentBlock（eval_persona_setup 和 research）"""
    persona_dicts = [p.to_dict() for p in personas]
    
    # 同步到 eval_persona_setup block
    persona_block = _get_persona_block(project_id, db)
    if persona_block:
        try:
            persona_block.content = json.dumps({
                "personas": persona_dicts,
                "source": "tool_synced",
            }, ensure_ascii=False, indent=2)
            db.flush()
        except Exception:
            pass  # 不影响主操作
    
    # 同步到 research block 的 personas 字段
    research_block = _get_research_block(project_id, db)
    if research_block and research_block.content:
        try:
            data = json.loads(research_block.content)
            data["personas"] = persona_dicts
            research_block.content = json.dumps(data, ensure_ascii=False, indent=2)
            db.flush()
        except Exception:
            pass


def list_personas(
    project_id: str,
    db: Optional[Session] = None,
) -> PersonaResult:
    """列出所有人物"""
    if db is None:
        db = next(get_db())
    
    field = _get_research_field(project_id, db)
    if not field or not field.content:
        return PersonaResult(
            success=True,
            message="暂无人物",
            personas=[],
        )
    
    personas = _parse_personas(field.content)
    return PersonaResult(
        success=True,
        message=f"共 {len(personas)} 个人物",
        personas=personas,
    )


def create_persona(
    project_id: str,
    persona_data: Dict[str, Any],
    db: Optional[Session] = None,
) -> PersonaResult:
    """创建新人物"""
    if db is None:
        db = next(get_db())
    
    field = _get_research_field(project_id, db)
    if not field:
        return PersonaResult(
            success=False,
            message="消费者调研报告不存在，请先完成调研",
            error="Research field not found",
        )
    
    try:
        personas = _parse_personas(field.content or "{}")
        
        # 创建新人物
        new_persona = Persona(
            name=persona_data.get("name", "未命名用户"),
            basic_info=persona_data.get("basic_info", {}),
            background=persona_data.get("background", ""),
            pain_points=persona_data.get("pain_points", []),
            behaviors=persona_data.get("behaviors", []),
            selected=persona_data.get("selected", True),
        )
        
        personas.append(new_persona)
        _save_personas(field, personas, db)
        # 同步到 ContentBlock
        _sync_personas_to_blocks(project_id, personas, db)
        db.commit()
        
        return PersonaResult(
            success=True,
            message=f"已创建人物「{new_persona.name}」",
            persona=new_persona,
        )
        
    except Exception as e:
        return PersonaResult(
            success=False,
            message=f"创建人物失败: {str(e)}",
            error=str(e),
        )


def update_persona(
    project_id: str,
    persona_id: str,
    updates: Dict[str, Any],
    db: Optional[Session] = None,
) -> PersonaResult:
    """更新人物信息"""
    if db is None:
        db = next(get_db())
    
    field = _get_research_field(project_id, db)
    if not field:
        return PersonaResult(
            success=False,
            message="消费者调研报告不存在",
            error="Research field not found",
        )
    
    try:
        personas = _parse_personas(field.content or "{}")
        
        # 查找人物
        target = None
        for p in personas:
            if p.id == persona_id or p.name == persona_id:
                target = p
                break
        
        if not target:
            return PersonaResult(
                success=False,
                message=f"人物「{persona_id}」不存在",
                error="Persona not found",
            )
        
        # 更新属性
        if "name" in updates:
            target.name = updates["name"]
        if "basic_info" in updates:
            target.basic_info.update(updates["basic_info"])
        if "background" in updates:
            target.background = updates["background"]
        if "pain_points" in updates:
            target.pain_points = updates["pain_points"]
        if "behaviors" in updates:
            target.behaviors = updates["behaviors"]
        if "selected" in updates:
            target.selected = updates["selected"]
        
        _save_personas(field, personas, db)
        _sync_personas_to_blocks(project_id, personas, db)
        db.commit()
        
        return PersonaResult(
            success=True,
            message=f"已更新人物「{target.name}」",
            persona=target,
        )
        
    except Exception as e:
        return PersonaResult(
            success=False,
            message=f"更新人物失败: {str(e)}",
            error=str(e),
        )


def select_persona(
    project_id: str,
    persona_id: str,
    selected: bool = True,
    db: Optional[Session] = None,
) -> PersonaResult:
    """选择/取消选择人物用于模拟"""
    return update_persona(
        project_id=project_id,
        persona_id=persona_id,
        updates={"selected": selected},
        db=db,
    )


def delete_persona(
    project_id: str,
    persona_id: str,
    db: Optional[Session] = None,
) -> PersonaResult:
    """删除人物"""
    if db is None:
        db = next(get_db())
    
    field = _get_research_field(project_id, db)
    if not field:
        return PersonaResult(
            success=False,
            message="消费者调研报告不存在",
            error="Research field not found",
        )
    
    try:
        personas = _parse_personas(field.content or "{}")
        
        # 查找并删除
        original_count = len(personas)
        personas = [p for p in personas if p.id != persona_id and p.name != persona_id]
        
        if len(personas) == original_count:
            return PersonaResult(
                success=False,
                message=f"人物「{persona_id}」不存在",
                error="Persona not found",
            )
        
        _save_personas(field, personas, db)
        _sync_personas_to_blocks(project_id, personas, db)
        db.commit()
        
        return PersonaResult(
            success=True,
            message=f"已删除人物",
        )
        
    except Exception as e:
        return PersonaResult(
            success=False,
            message=f"删除人物失败: {str(e)}",
            error=str(e),
        )


async def generate_persona(
    project_id: str,
    persona_hint: str = "",
    db: Optional[Session] = None,
) -> PersonaResult:
    """根据提示生成新人物"""
    if db is None:
        db = next(get_db())
    
    # 获取项目上下文
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return PersonaResult(
            success=False,
            message="项目不存在",
            error="Project not found",
        )
    
    gc = project.golden_context or {}
    intent = gc.get("intent", "")
    
    # 获取现有人物作为参考
    field = _get_research_field(project_id, db)
    existing_personas = []
    consumer_profile = {}
    if field and field.content:
        try:
            data = json.loads(field.content)
            existing_personas = data.get("personas", [])
            consumer_profile = data.get("consumer_profile", {})
        except:
            pass
    
    # 构建提示词
    system_prompt = f"""你是一个用户画像专家。请根据项目信息生成一个新的消费者人物小传。

## 项目意图
{intent}

## 消费者画像
{json.dumps(consumer_profile, ensure_ascii=False, indent=2) if consumer_profile else '待定义'}

## 已有人物（避免重复）
{json.dumps([p.get("name", "") for p in existing_personas], ensure_ascii=False)}

## 生成要求
{persona_hint if persona_hint else '请生成一个与已有人物不同类型的典型用户'}

## 输出格式
请以 JSON 格式输出：
```json
{{
    "name": "人物姓名（使用中文名）",
    "basic_info": {{
        "age": 年龄,
        "gender": "性别",
        "occupation": "职业",
        "city": "城市",
        "education": "学历",
        "income_range": "收入范围"
    }},
    "background": "背景简介（2-3句话）",
    "pain_points": ["痛点1", "痛点2", "痛点3"],
    "behaviors": ["行为特征1", "行为特征2"]
}}
```

只输出JSON，不要其他解释。"""

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content="请生成人物小传"),
    ]
    
    try:
        response = await ai_client.async_chat(messages, temperature=0.8)
        content = response.content.strip()
        
        # 提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        persona_data = json.loads(content)
        
        # 创建人物
        return create_persona(project_id, persona_data, db)
        
    except Exception as e:
        return PersonaResult(
            success=False,
            message=f"生成人物失败: {str(e)}",
            error=str(e),
        )


async def manage_persona(
    project_id: str,
    operation: PersonaOperation,
    params: Dict[str, Any] = None,
    db: Optional[Session] = None,
) -> PersonaResult:
    """
    人物管理统一入口
    
    Args:
        project_id: 项目ID
        operation: 操作类型
        params: 操作参数
        db: 数据库会话
    
    Returns:
        PersonaResult
    """
    params = params or {}
    
    if operation == PersonaOperation.LIST:
        return list_personas(project_id, db)
    
    elif operation == PersonaOperation.CREATE:
        return create_persona(project_id, params, db)
    
    elif operation == PersonaOperation.UPDATE:
        return update_persona(
            project_id,
            params.get("persona_id", ""),
            params.get("updates", {}),
            db,
        )
    
    elif operation == PersonaOperation.SELECT:
        return select_persona(project_id, params.get("persona_id", ""), True, db)
    
    elif operation == PersonaOperation.DESELECT:
        return select_persona(project_id, params.get("persona_id", ""), False, db)
    
    elif operation == PersonaOperation.DELETE:
        return delete_persona(project_id, params.get("persona_id", ""), db)
    
    elif operation == PersonaOperation.GENERATE:
        return await generate_persona(project_id, params.get("hint", ""), db)
    
    else:
        return PersonaResult(
            success=False,
            message=f"未知操作: {operation}",
            error="Unknown operation",
        )
