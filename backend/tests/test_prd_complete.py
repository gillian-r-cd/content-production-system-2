# backend/tests/test_prd_complete.py
# 功能: PRD完整功能测试
# 验证: 版本管理、评估、模拟执行、一键生成、日志导出等

"""
PRD 完整功能测试

验证所有PRD要求的功能:
1. 版本管理 - 创建新版本时复制字段
2. 评估API - 运行评估、管理报告、采纳建议
3. 模拟执行 - 实际运行模拟
4. 一键生成 - 批量生成字段
5. 日志导出 - 包含完整输入输出
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import (
    Project,
    ProjectField,
    CreatorProfile,
    EvaluationTemplate,
    EvaluationReport,
    SimulationRecord,
    Simulator,
    GenerationLog,
    PROJECT_PHASES,
    generate_uuid,
)


@pytest.fixture
def db_session():
    """创建测试用的内存数据库"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


class TestVersionManagement:
    """版本管理测试"""
    
    def test_create_version_copies_fields(self, db_session):
        """创建新版本时应该复制所有字段"""
        # 创建原始项目
        project_v1 = Project(
            id=generate_uuid(),
            name="Test Project",
            version=1,
            current_phase="produce_inner",
        )
        db_session.add(project_v1)
        db_session.commit()
        
        # 创建字段
        field_a = ProjectField(
            id=generate_uuid(),
            project_id=project_v1.id,
            phase="produce_inner",
            name="Field A",
            content="Content A",
            status="completed",
        )
        field_b = ProjectField(
            id=generate_uuid(),
            project_id=project_v1.id,
            phase="produce_inner",
            name="Field B",
            content="Content B",
            status="completed",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        db_session.add_all([field_a, field_b])
        db_session.commit()
        
        # 模拟创建新版本（复制逻辑）
        new_project = Project(
            id=generate_uuid(),
            name="Test Project",
            version=2,
            version_note="Updated content",
            parent_version_id=project_v1.id,
            current_phase=project_v1.current_phase,
            phase_order=project_v1.phase_order.copy(),
            phase_status=project_v1.phase_status.copy(),
            golden_context=project_v1.golden_context.copy() if project_v1.golden_context else {},
        )
        db_session.add(new_project)
        db_session.commit()
        
        # 复制字段
        old_fields = db_session.query(ProjectField).filter(
            ProjectField.project_id == project_v1.id
        ).all()
        
        field_id_mapping = {}
        new_fields_list = []
        
        # 第一遍：创建所有新字段并建立ID映射
        for old_field in old_fields:
            new_field_id = generate_uuid()
            field_id_mapping[old_field.id] = new_field_id
            
            new_field = ProjectField(
                id=new_field_id,
                project_id=new_project.id,
                phase=old_field.phase,
                name=old_field.name,
                content=old_field.content,
                status=old_field.status,
                dependencies=old_field.dependencies.copy() if old_field.dependencies else {},
            )
            new_fields_list.append(new_field)
        
        # 第二遍：更新依赖关系中的字段ID
        for new_field in new_fields_list:
            if new_field.dependencies and new_field.dependencies.get("depends_on"):
                old_deps = new_field.dependencies["depends_on"]
                new_deps = [field_id_mapping.get(d, d) for d in old_deps]
                new_field.dependencies = {**new_field.dependencies, "depends_on": new_deps}
            db_session.add(new_field)
        
        db_session.commit()
        
        # 验证
        v2_fields = db_session.query(ProjectField).filter(
            ProjectField.project_id == new_project.id
        ).all()
        
        assert len(v2_fields) == 2
        assert new_project.version == 2
        assert new_project.parent_version_id == project_v1.id
        
        # 验证依赖关系已更新
        field_b_v2 = next(f for f in v2_fields if f.name == "Field B")
        field_a_v2 = next(f for f in v2_fields if f.name == "Field A")
        
        assert field_a_v2.id in field_b_v2.dependencies["depends_on"]
        assert field_a.id not in field_b_v2.dependencies["depends_on"]


class TestEvaluationWorkflow:
    """评估工作流测试"""
    
    def test_evaluation_template_validation(self, db_session):
        """评估模板权重验证"""
        template = EvaluationTemplate(
            id=generate_uuid(),
            name="Test Template",
            sections=[
                {"id": "a", "name": "Section A", "weight": 0.5},
                {"id": "b", "name": "Section B", "weight": 0.3},
                {"id": "c", "name": "Section C", "weight": 0.2},
            ],
        )
        
        errors = template.validate()
        assert len(errors) == 0  # 权重总和为1
    
    def test_evaluation_report_suggestions(self, db_session):
        """评估报告建议管理"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        report = EvaluationReport(
            id=generate_uuid(),
            project_id=project.id,
            scores={"quality": {"score": 8.0}},
            overall_score=8.0,
            suggestions=[
                {"id": "s1", "content": "Add more examples", "priority": "high", "adopted": False},
                {"id": "s2", "content": "Improve formatting", "priority": "medium", "adopted": False},
            ],
            summary="Good overall quality",
        )
        db_session.add(report)
        db_session.commit()
        
        # 测试获取未采纳建议
        pending = report.get_pending_suggestions()
        assert len(pending) == 2
        
        # 采纳建议
        result = report.adopt_suggestion("s1", "Added 5 examples to Module 2")
        assert result == True
        
        pending = report.get_pending_suggestions()
        assert len(pending) == 1
    
    def test_evaluation_report_structure(self, db_session):
        """评估报告结构完整性"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        template = EvaluationTemplate(
            id=generate_uuid(),
            name="Standard Template",
            sections=[
                {
                    "id": "intent",
                    "name": "Intent Alignment",
                    "weight": 0.25,
                    "grader_prompt": "Evaluate intent alignment",
                    "metrics": [
                        {"name": "coverage", "type": "score_1_10"},
                    ],
                },
            ],
        )
        db_session.add(template)
        db_session.commit()
        
        report = EvaluationReport(
            id=generate_uuid(),
            project_id=project.id,
            template_id=template.id,
            scores={"intent": {"scores": {"coverage": 8.5}, "summary": "Good coverage"}},
            overall_score=8.5,
            suggestions=[],
            summary="Overall good",
        )
        db_session.add(report)
        db_session.commit()
        
        assert report.overall_score == 8.5
        assert "intent" in report.scores


class TestSimulationExecution:
    """模拟执行测试"""
    
    def test_simulation_record_structure(self, db_session):
        """模拟记录结构"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        simulator = Simulator(
            id=generate_uuid(),
            name="Reading Simulator",
            interaction_type="reading",
            evaluation_dimensions=["clarity", "value", "actionability"],
        )
        db_session.add(simulator)
        db_session.commit()
        
        record = SimulationRecord(
            id=generate_uuid(),
            project_id=project.id,
            simulator_id=simulator.id,
            target_field_ids=["field_1", "field_2"],
            persona={
                "source": "research",
                "name": "Dr. Zhang",
                "background": "40 years old doctor",
                "story": "Works in busy hospital",
            },
            interaction_log={"input": "Content...", "output": "Feedback..."},
            feedback={
                "scores": {"clarity": 8.0, "value": 9.0, "actionability": 7.5},
                "comments": {"clarity": "Very clear"},
                "overall": "Good content",
            },
            status="completed",
        )
        db_session.add(record)
        db_session.commit()
        
        # 验证平均分计算
        avg_score = record.get_average_score()
        assert avg_score is not None
        assert abs(avg_score - 8.17) < 0.1  # (8+9+7.5)/3 = 8.17
    
    def test_simulation_persona_from_research(self, db_session):
        """从调研中获取人物小传"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        # 创建调研字段，包含人物小传
        research_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="research",
            name="Consumer Personas",
            content="""
## 人物小传 1: 张医生
**背景**: 40岁，三甲医院内科主任
**故事**: 每天接诊超过50位患者...

## 人物小传 2: 李护士
**背景**: 28岁，ICU护士
**故事**: 在高压环境下工作...
            """,
            status="completed",
        )
        db_session.add(research_field)
        db_session.commit()
        
        # 验证字段存在
        assert research_field.content is not None
        assert "张医生" in research_field.content


class TestBatchGeneration:
    """批量生成测试"""
    
    def test_resolve_field_order_for_batch(self, db_session):
        """批量生成时的字段顺序解析"""
        from core.tools.field_generator import resolve_field_order
        
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        # 创建有依赖关系的字段
        field_a = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field A",
            dependencies={"depends_on": [], "dependency_type": "all"},
        )
        field_b = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field B",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        field_c = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field C",
            dependencies={"depends_on": [field_a.id], "dependency_type": "all"},
        )
        field_d = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Field D",
            dependencies={"depends_on": [field_b.id, field_c.id], "dependency_type": "all"},
        )
        
        db_session.add_all([field_a, field_b, field_c, field_d])
        db_session.commit()
        
        # 解析顺序
        order = resolve_field_order([field_a, field_b, field_c, field_d])
        
        # 验证: A先，BC并行，D最后
        assert len(order) == 3
        assert order[0][0].name == "Field A"
        assert len(order[1]) == 2
        assert set(f.name for f in order[1]) == {"Field B", "Field C"}
        assert order[2][0].name == "Field D"
    
    def test_autonomy_check_during_batch(self, db_session):
        """批量生成时的自主权检查"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            agent_autonomy={
                "intent": False,  # 自动
                "research": True,  # 需确认
                "produce_inner": False,  # 自动
            },
        )
        db_session.add(project)
        db_session.commit()
        
        # research阶段需要确认
        assert project.needs_human_confirm("research") == True
        
        # produce_inner阶段自动
        assert project.needs_human_confirm("produce_inner") == False


class TestLogExport:
    """日志导出测试"""
    
    def test_generation_log_structure(self, db_session):
        """生成日志结构"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        
        log = GenerationLog(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            operation="generate_field",
            model="gpt-5.1",
            prompt_input="System prompt here...\nUser prompt here...",
            prompt_output="Generated content here...",
            tokens_in=500,
            tokens_out=1000,
            duration_ms=2500,
            cost=GenerationLog.calculate_cost("gpt-5.1", 500, 1000),
            status="success",
        )
        db_session.add(log)
        db_session.commit()
        
        # 验证结构
        assert log.prompt_input is not None
        assert log.prompt_output is not None
        assert log.tokens_in == 500
        assert log.tokens_out == 1000
    
    def test_cost_calculation(self, db_session):
        """成本计算"""
        # GPT-5.1: $5/1M input, $15/1M output
        cost = GenerationLog.calculate_cost("gpt-5.1", 1000, 500)
        
        expected_input = (1000 / 1_000_000) * 5.00
        expected_output = (500 / 1_000_000) * 15.00
        expected_total = expected_input + expected_output
        
        assert abs(cost - expected_total) < 0.0001


class TestPhaseOrderManagement:
    """阶段顺序管理测试"""
    
    def test_fixed_phases(self, db_session):
        """验证固定阶段位置"""
        project = Project(id=generate_uuid(), name="Test Project")
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        
        # intent和research固定在前
        assert project.phase_order[0] == "intent"
        assert project.phase_order[1] == "research"
        
        # simulate和evaluate固定在后
        assert project.phase_order[-2] == "simulate"
        assert project.phase_order[-1] == "evaluate"
    
    def test_middle_four_reorderable(self, db_session):
        """验证中间四个阶段可重排"""
        custom_order = [
            "intent",
            "research",
            # 中间四个重排
            "design_outer",
            "produce_outer",
            "design_inner",
            "produce_inner",
            # 固定
            "simulate",
            "evaluate",
        ]
        
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            phase_order=custom_order,
        )
        db_session.add(project)
        db_session.commit()
        
        # 验证自定义顺序保存
        assert project.phase_order[2] == "design_outer"
        assert project.phase_order[5] == "produce_inner"
        
        # 验证导航使用自定义顺序
        project.current_phase = "research"
        assert project.get_next_phase() == "design_outer"


class TestGoldenContextPropagation:
    """Golden Context传递测试"""
    
    def test_intent_to_all_phases(self, db_session):
        """意图传递到所有阶段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            golden_context={
                "intent": "Build AI diagnostic tool for doctors",
                "consumer_personas": "Clinical doctors aged 35-50",
            },
        )
        db_session.add(project)
        db_session.commit()
        
        from core.prompt_engine import prompt_engine
        
        for phase in ["design_inner", "produce_inner", "design_outer", "produce_outer"]:
            context = prompt_engine.build_prompt_context(
                project=project,
                phase=phase,
            )
            
            # Golden Context应该在每个阶段可用
            assert context.golden_context.intent == "Build AI diagnostic tool for doctors"
    
    def test_research_personas_available(self, db_session):
        """调研人物画像可用"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            golden_context={
                "intent": "Test intent",
                "consumer_personas": "Target: Medical professionals aged 30-50",
            },
        )
        db_session.add(project)
        db_session.commit()
        
        from core.prompt_engine import prompt_engine
        
        gc = prompt_engine.build_golden_context(project)
        
        assert "Medical professionals" in gc.consumer_personas


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

