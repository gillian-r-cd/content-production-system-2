from pathlib import Path

from core.config import settings
from core.locale_text import RUNTIME_TEXTS
from core.database import get_session_maker
from core.models import AgentMode, Channel, CreatorProfile, FieldTemplate, SystemPrompt
from scripts.init_db import init_database, seed_default_data

ROOT = Path(__file__).resolve().parents[2]


def test_ja_eval_prompt_presets_do_not_contain_known_cn_residue():
    content = (ROOT / "backend/api/settings.py").read_text(encoding="utf-8")
    ja_section_start = content.index('"locale": "ja-JP"')
    ja_section = content[ja_section_start:]

    forbidden_tokens = [
        "内容未覆盖",
        "请严格输出",
        "消费者调研",
        "评估当前内容",
    ]
    for token in forbidden_tokens:
        assert token not in ja_section


def test_ja_seeded_simulator_texts_do_not_reuse_cn_dimensions():
    content = (ROOT / "backend/scripts/init_db.py").read_text(encoding="utf-8")
    ja_seed_start = content.index("simulator_meta_ja = {")
    ja_seed_section = content[ja_seed_start:]

    forbidden_tokens = [
        "响应相关性",
        "问题解决率",
        "理解难度",
        "转化意愿",
        "找到答案效率",
    ]
    for token in forbidden_tokens:
        assert token not in ja_seed_section


def test_ja_runtime_locale_texts_do_not_contain_known_cn_residue():
    ja_text = "\n".join(str(value) for value in RUNTIME_TEXTS["ja-JP"].values())

    forbidden_tokens = [
        "内容未覆盖",
        "继续",
        "消费者调研",
        "请严格输出",
        "输出格式（必须遵守）",
        "创作者风格参考",
        "当前任务",
        "目标渠道",
    ]
    for token in forbidden_tokens:
        assert token not in ja_text


def test_ja_orchestrator_branch_does_not_embed_known_cn_control_text():
    content = (ROOT / "backend/core/orchestrator.py").read_text(encoding="utf-8")
    ja_start = content.index('if project_locale == "ja-JP":')
    zh_fallback = content.index('\n    return f"""<identity>', ja_start)
    ja_branch = content[ja_start:zh_fallback]

    forbidden_tokens = [
        "使用中文回复",
        "当前能力上下文",
        "继续",
        "下一步",
    ]
    for token in forbidden_tokens:
        assert token not in ja_branch


def test_inline_edit_route_does_not_keep_hardcoded_cn_prompt_fragments():
    content = (ROOT / "backend/api/agent.py").read_text(encoding="utf-8")
    inline_start = content.index("async def inline_edit(")
    inline_section = content[inline_start:]

    forbidden_tokens = [
        "创作者风格参考：",
        "专业的中文内容编辑",
        "需要修改的文本：",
    ]
    for token in forbidden_tokens:
        assert token not in inline_section


def test_seed_default_data_does_not_rewrite_existing_locale_asset_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "locale_asset_guard.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")

    init_database()
    seed_default_data()

    SessionLocal = get_session_maker()
    db = SessionLocal()
    try:
        tracked_rows = {
            "creator_profile": db.query(CreatorProfile).filter(
                CreatorProfile.stable_key == "professional_rigorous",
                CreatorProfile.locale == "ja-JP",
            ).first(),
            "system_prompt": db.query(SystemPrompt).filter(
                SystemPrompt.stable_key == "intent",
                SystemPrompt.locale == "ja-JP",
            ).first(),
            "channel": db.query(Channel).filter(
                Channel.stable_key == "xiaohongshu",
                Channel.locale == "ja-JP",
            ).first(),
            "field_template": db.query(FieldTemplate).filter(
                FieldTemplate.stable_key == "course_design",
                FieldTemplate.locale == "ja-JP",
            ).first(),
            "agent_mode": db.query(AgentMode).filter(
                AgentMode.stable_key == "assistant",
                AgentMode.locale == "ja-JP",
            ).first(),
        }
        original_ids = {key: row.id for key, row in tracked_rows.items()}
    finally:
        db.close()

    seed_default_data()

    db = SessionLocal()
    try:
        assert db.query(CreatorProfile).filter(
            CreatorProfile.stable_key == "professional_rigorous",
            CreatorProfile.locale == "ja-JP",
        ).first().id == original_ids["creator_profile"]
        assert db.query(SystemPrompt).filter(
            SystemPrompt.stable_key == "intent",
            SystemPrompt.locale == "ja-JP",
        ).first().id == original_ids["system_prompt"]
        assert db.query(Channel).filter(
            Channel.stable_key == "xiaohongshu",
            Channel.locale == "ja-JP",
        ).first().id == original_ids["channel"]
        assert db.query(FieldTemplate).filter(
            FieldTemplate.stable_key == "course_design",
            FieldTemplate.locale == "ja-JP",
        ).first().id == original_ids["field_template"]
        assert db.query(AgentMode).filter(
            AgentMode.stable_key == "assistant",
            AgentMode.locale == "ja-JP",
        ).first().id == original_ids["agent_mode"]
    finally:
        db.close()
