# backend/scripts/migrate_content_blocks.py
# 功能: 迁移脚本 - 创建 content_blocks 和 phase_templates 表
# 主要函数: migrate(), seed_default_template(), migrate_existing_fields()

"""
内容块架构迁移脚本
运行: python -m scripts.migrate_content_blocks

此脚本将:
1. 创建 content_blocks 表
2. 创建 phase_templates 表
3. 插入默认阶段模板
4. 将现有 project_fields 数据迁移到 content_blocks（可选）
"""

import sys
from pathlib import Path

# 确保可以导入core模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Base, get_engine, get_session_maker
from core.models import (
    ContentBlock,
    PhaseTemplate,
    DEFAULT_PHASE_TEMPLATE,
    Project,
    ProjectField,
    generate_uuid,
)


def migrate():
    """创建新表"""
    print("正在创建 content_blocks 和 phase_templates 表...")
    engine = get_engine()
    
    # 只创建新表，不删除现有表
    Base.metadata.create_all(bind=engine)
    print("表创建完成！")


def seed_default_template():
    """插入默认阶段模板"""
    print("正在插入默认阶段模板...")
    
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    try:
        # 检查是否已存在默认模板
        existing = db.query(PhaseTemplate).filter(
            PhaseTemplate.name == DEFAULT_PHASE_TEMPLATE["name"]
        ).first()
        
        if existing:
            print("  - 默认模板已存在，跳过")
            return
        
        template = PhaseTemplate(
            id=DEFAULT_PHASE_TEMPLATE["id"],
            name=DEFAULT_PHASE_TEMPLATE["name"],
            description=DEFAULT_PHASE_TEMPLATE["description"],
            phases=DEFAULT_PHASE_TEMPLATE["phases"],
            is_default=True,
            is_system=True,
        )
        db.add(template)
        db.commit()
        print("  - 创建了默认阶段模板")
        
    except Exception as e:
        db.rollback()
        print(f"错误: {e}")
        raise
    finally:
        db.close()


def migrate_existing_fields(project_id: str = None):
    """
    将现有 project_fields 迁移到 content_blocks
    
    Args:
        project_id: 指定项目ID，为空则迁移所有项目
    """
    print("正在迁移现有字段数据...")
    
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    try:
        # 查询项目
        query = db.query(Project)
        if project_id:
            query = query.filter(Project.id == project_id)
        projects = query.all()
        
        if not projects:
            print("  - 没有找到需要迁移的项目")
            return
        
        # 阶段到特殊处理器的映射
        phase_handler_map = {
            "intent": "intent",
            "research": "research",
            "simulate": "simulate",
            "evaluate": "evaluate",
        }
        
        for project in projects:
            print(f"  迁移项目: {project.name} ({project.id})")
            
            # 检查是否已有 content_blocks
            existing_blocks = db.query(ContentBlock).filter(
                ContentBlock.project_id == project.id
            ).count()
            
            if existing_blocks > 0:
                print(f"    - 项目已有 {existing_blocks} 个内容块，跳过")
                continue
            
            # 创建阶段块
            phase_blocks = {}
            for idx, phase_name in enumerate(project.phase_order):
                phase_id = generate_uuid()
                
                # 阶段显示名称映射
                display_names = {
                    "intent": "意图分析",
                    "research": "消费者调研",
                    "design_inner": "内涵设计",
                    "produce_inner": "内涵生产",
                    "design_outer": "外延设计",
                    "produce_outer": "外延生产",
                    "simulate": "消费者模拟",
                    "evaluate": "评估",
                }
                
                phase_block = ContentBlock(
                    id=phase_id,
                    project_id=project.id,
                    parent_id=None,
                    name=display_names.get(phase_name, phase_name),
                    block_type="phase",
                    depth=0,
                    order_index=idx,
                    status=project.phase_status.get(phase_name, "pending"),
                    special_handler=phase_handler_map.get(phase_name),
                    need_review=project.agent_autonomy.get(phase_name, True),
                )
                db.add(phase_block)
                phase_blocks[phase_name] = phase_id
            
            # 迁移字段到对应阶段下
            fields = db.query(ProjectField).filter(
                ProjectField.project_id == project.id
            ).order_by(ProjectField.order).all()
            
            # 字段ID映射（旧ID -> 新ID）
            field_id_map = {}
            
            for field in fields:
                parent_phase_id = phase_blocks.get(field.phase)
                if not parent_phase_id:
                    print(f"    - 警告: 字段 {field.name} 的阶段 {field.phase} 不在项目阶段列表中")
                    continue
                
                new_id = generate_uuid()
                field_id_map[field.id] = new_id
                
                # 解析依赖
                old_depends = []
                if field.dependencies and isinstance(field.dependencies, dict):
                    old_depends = field.dependencies.get("depends_on", [])
                
                field_block = ContentBlock(
                    id=new_id,
                    project_id=project.id,
                    parent_id=parent_phase_id,
                    name=field.name,
                    block_type="field",
                    depth=1,
                    order_index=field.order or 0,
                    content=field.content or "",
                    status=field.status or "pending",
                    ai_prompt=field.ai_prompt or "",
                    constraints=field.constraints or {},
                    depends_on=[],  # 稍后更新
                    need_review=field.need_review if hasattr(field, 'need_review') else True,
                )
                db.add(field_block)
            
            db.flush()  # 确保所有块都有ID
            
            # 更新依赖关系（将旧字段ID转换为新ID）
            for field in fields:
                new_id = field_id_map.get(field.id)
                if not new_id:
                    continue
                
                old_depends = []
                if field.dependencies and isinstance(field.dependencies, dict):
                    old_depends = field.dependencies.get("depends_on", [])
                
                new_depends = [field_id_map[old_id] for old_id in old_depends if old_id in field_id_map]
                
                if new_depends:
                    block = db.query(ContentBlock).filter(ContentBlock.id == new_id).first()
                    if block:
                        block.depends_on = new_depends
            
            print(f"    - 迁移了 {len(phase_blocks)} 个阶段块和 {len(fields)} 个字段块")
        
        db.commit()
        print("迁移完成！")
        
    except Exception as e:
        db.rollback()
        print(f"错误: {e}")
        raise
    finally:
        db.close()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="内容块架构迁移")
    parser.add_argument(
        "--migrate-fields",
        action="store_true",
        help="同时迁移现有 project_fields 数据"
    )
    parser.add_argument(
        "--project-id",
        type=str,
        help="只迁移指定项目的字段"
    )
    args = parser.parse_args()
    
    print("=" * 50)
    print("内容生产系统 - 内容块架构迁移")
    print("=" * 50)
    
    migrate()
    seed_default_template()
    
    if args.migrate_fields:
        migrate_existing_fields(args.project_id)
    
    print("=" * 50)
    print("迁移完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
