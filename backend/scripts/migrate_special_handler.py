# backend/scripts/migrate_special_handler.py
# 功能: 将父 phase 块的 special_handler 回填到子 field 块
# 修复: 历史项目中子 field 块缺失 special_handler 导致 _is_structured_handler 失效

"""
迁移脚本：回填 ContentBlock 的 special_handler

问题：phase_template.py::apply_to_project() 历史上创建子 field 时
不传递父 phase 的 special_handler，导致 generate_field_content 等
工具的 _is_structured_handler 检查对子块失效。

此脚本找到所有"父块有 special_handler 但子块没有"的情况并修复。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import get_db
from core.models.content_block import ContentBlock


def migrate():
    db = next(get_db())
    try:
        parents = db.query(ContentBlock).filter(
            ContentBlock.special_handler != None,  # noqa: E711
            ContentBlock.special_handler != "",
            ContentBlock.deleted_at == None,  # noqa: E711
        ).all()

        updated = 0
        for parent in parents:
            children = db.query(ContentBlock).filter(
                ContentBlock.parent_id == parent.id,
                ContentBlock.deleted_at == None,  # noqa: E711
            ).all()

            for child in children:
                if not child.special_handler:
                    print(f"  [{parent.name}] -> [{child.name}]: "
                          f"设置 special_handler = '{parent.special_handler}'")
                    child.special_handler = parent.special_handler
                    updated += 1

        if updated:
            db.commit()
            print(f"\n已更新 {updated} 个子块的 special_handler")
        else:
            print("无需更新：所有子块已有 special_handler")

    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("迁移 special_handler 到子 field 块")
    print("=" * 50)
    migrate()
