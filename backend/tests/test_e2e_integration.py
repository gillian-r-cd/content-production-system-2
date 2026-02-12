# backend/tests/test_e2e_integration.py
# 功能: 端到端集成测试
# 验证: 模拟完整的内容生产流程,确保所有环节协同工作

"""
端到端集成测试

模拟完整的内容生产流程:
1. 创建项目和关联创作者特质
2. 意图分析阶段
3. 消费者调研阶段
4. 内涵设计和生产（包含字段依赖）
5. 外延设计和生产
6. 消费者模拟
7. 评估

验证:
- 数据正确持久化
- 上下文正确传递
- 依赖关系正确处理
- 状态正确更新
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
    FieldTemplate,
    Channel,
    Simulator,
    SimulationRecord,
    EvaluationTemplate,
    EvaluationReport,
    GenerationLog,
    ChatMessage,
    PROJECT_PHASES,
    generate_uuid,
)
from core.prompt_engine import prompt_engine, GoldenContext
from core.tools.field_generator import resolve_field_order


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


class TestFullProductionFlow:
    """完整内容生产流程测试"""
    
    def test_create_project_with_creator_profile(self, db_session):
        """测试创建项目并关联创作者特质"""
        # 创建创作者特质
        profile = CreatorProfile(
            id=generate_uuid(),
            name="Medical Expert",
            description="AI medical content specialist",
            traits={
                "tone": "professional",
                "expertise": "medical AI",
                "taboos": ["unverified claims"],
            },
        )
        db_session.add(profile)
        db_session.commit()
        
        # 创建项目
        project = Project(
            id=generate_uuid(),
            name="AI Diagnosis Assistant Course",
            creator_profile_id=profile.id,
            current_phase="intent",
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        
        # 验证关联
        assert project.creator_profile_id == profile.id
        assert project.current_phase == "intent"
        assert len(project.phase_order) == 7
    
    def test_intent_analysis_phase(self, db_session):
        """测试意图分析阶段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="intent",
        )
        db_session.add(project)
        db_session.commit()
        
        # 创建意图分析字段
        intent_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="intent",
            name="Intent Analysis",
            content="""
            Core Goal: Build AI diagnostic assistant training for doctors
            Target Audience: Clinical doctors aged 35-50
            Expected Outcome: Doctors can use AI tools for preliminary diagnosis
            """,
            status="completed",
        )
        db_session.add(intent_field)
        
        # 更新Golden Context
        project.golden_context = {"intent": intent_field.content}
        project.phase_status = {**project.phase_status, "intent": "completed"}
        db_session.commit()
        
        # 验证
        assert "intent" in project.golden_context
        assert "AI diagnostic" in project.golden_context["intent"]
    
    def test_consumer_research_phase(self, db_session):
        """测试消费者调研阶段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="research",
            golden_context={"intent": "AI training for doctors"},
        )
        db_session.add(project)
        db_session.commit()
        
        # 创建调研字段
        research_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="research",
            name="Consumer Research",
            content="""
            ## Target Audience Profile
            - Age: 35-50
            - Profession: Clinical doctors
            
            ## Pain Points
            1. Heavy workload
            2. Need for diagnostic assistance
            
            ## Personas
            ### Dr. Zhang
            Background: 40 years old, 15 years experience
            Story: Works in busy hospital, seeks efficiency tools
            """,
            status="completed",
        )
        db_session.add(research_field)
        
        # 更新Golden Context
        project.golden_context = {
            **project.golden_context,
            "consumer_personas": research_field.content,
        }
        project.phase_status = {**project.phase_status, "research": "completed"}
        db_session.commit()
        
        # 验证
        assert "consumer_personas" in project.golden_context
        assert "Dr. Zhang" in project.golden_context["consumer_personas"]
    
    def test_inner_design_and_production(self, db_session):
        """测试内涵设计和生产阶段（包含依赖）"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="design_inner",
            golden_context={
                "intent": "AI training course",
                "consumer_personas": "Doctors aged 35-50",
            },
        )
        db_session.add(project)
        db_session.commit()
        
        # 内涵设计字段
        design_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="design_inner",
            name="Course Outline",
            content="""
            Module 1: Introduction to AI in Medicine
            Module 2: Understanding AI Diagnostics
            Module 3: Practical Applications
            """,
            status="completed",
        )
        db_session.add(design_field)
        db_session.commit()
        
        # 内涵生产字段（依赖设计）
        module1_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Module 1 Content",
            dependencies={"depends_on": [design_field.id], "dependency_type": "all"},
            status="pending",
        )
        module2_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Module 2 Content",
            dependencies={"depends_on": [design_field.id], "dependency_type": "all"},
            status="pending",
        )
        # Module 3 依赖 Module 1 和 2
        module3_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Module 3 Content",
            dependencies={
                "depends_on": [module1_field.id, module2_field.id],
                "dependency_type": "all",
            },
            status="pending",
        )
        
        db_session.add_all([module1_field, module2_field, module3_field])
        db_session.commit()
        
        # 验证依赖关系
        fields = [design_field, module1_field, module2_field, module3_field]
        order = resolve_field_order(fields)
        
        # Design first, then Module 1 & 2 in parallel, then Module 3
        assert len(order) == 3
        assert order[0][0].name == "Course Outline"
        assert len(order[1]) == 2
        assert order[2][0].name == "Module 3 Content"
        
        # 验证生成检查
        completed = {design_field.id}
        assert module1_field.can_generate(completed) == True
        assert module2_field.can_generate(completed) == True
        assert module3_field.can_generate(completed) == False  # 需要M1和M2
        
        # 模拟M1和M2完成
        module1_field.content = "Module 1 content..."
        module1_field.status = "completed"
        module2_field.content = "Module 2 content..."
        module2_field.status = "completed"
        db_session.commit()
        
        completed.add(module1_field.id)
        completed.add(module2_field.id)
        
        assert module3_field.can_generate(completed) == True
    
    def test_outer_design_and_production(self, db_session):
        """测试外延设计和生产阶段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="design_outer",
            golden_context={
                "intent": "AI training course",
                "consumer_personas": "Doctors",
            },
        )
        db_session.add(project)
        
        # 创建渠道
        channel = Channel(
            id=generate_uuid(),
            name="WeChat Official Account",
            description="Professional medical content platform",
            platform="social",
            constraints={"max_length": 10000, "format": "article"},
        )
        db_session.add(channel)
        db_session.commit()
        
        # 外延设计字段
        outer_design = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="design_outer",
            name="Marketing Strategy",
            content="Promote through medical communities and professional platforms",
            status="completed",
        )
        db_session.add(outer_design)
        db_session.commit()
        
        # 外延生产字段
        wechat_content = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_outer",
            name="WeChat Article",
            dependencies={"depends_on": [outer_design.id], "dependency_type": "all"},
            status="pending",
        )
        db_session.add(wechat_content)
        db_session.commit()
        
        # 验证渠道上下文构建
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_outer",
            channel=channel,
            dependent_fields=[outer_design],
        )
        
        system_prompt = context.to_system_prompt()
        
        # 渠道信息和依赖都应该在上下文中
        assert "Marketing Strategy" in system_prompt or outer_design.content in context.field_context
    
    def test_simulation_phase(self, db_session):
        """测试消费者模拟阶段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="simulate",
        )
        db_session.add(project)
        
        # 创建模拟器
        simulator = Simulator(
            id=generate_uuid(),
            name="Learning Experience Simulator",
            interaction_type="reading",
            prompt_template="You are {persona}. Please read the content and provide feedback.",
            evaluation_dimensions=["clarity", "engagement", "practicality"],
        )
        db_session.add(simulator)
        db_session.commit()
        
        # 创建模拟记录
        record = SimulationRecord(
            id=generate_uuid(),
            project_id=project.id,
            simulator_id=simulator.id,
            target_field_ids=["field_1", "field_2"],
            persona={
                "name": "Dr. Zhang",
                "background": "40 years old, 15 years experience",
            },
            interaction_log=[
                {"role": "system", "content": "Start simulation"},
                {"role": "user", "content": "Reading Module 1..."},
                {"role": "assistant", "content": "Content is clear and practical"},
            ],
            feedback={
                "scores": {"clarity": 4.5, "engagement": 4.0, "practicality": 5.0},
                "comments": "Very useful for daily practice",
            },
            status="completed",
        )
        db_session.add(record)
        db_session.commit()
        
        # 验证
        assert record.status == "completed"
        assert record.feedback["scores"]["practicality"] == 5.0
    
    def test_evaluation_phase(self, db_session):
        """测试评估阶段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
            current_phase="evaluate",
        )
        db_session.add(project)
        
        # 创建评估模板
        template = EvaluationTemplate(
            id=generate_uuid(),
            name="Standard Course Evaluation",
            sections=[
                {"id": "intent_alignment", "name": "Intent Alignment", "weight": 0.25, "criteria": "Content matches stated goals"},
                {"id": "user_match", "name": "User Match", "weight": 0.25, "criteria": "Content suits target audience"},
                {"id": "quality", "name": "Content Quality", "weight": 0.30, "criteria": "Professional and accurate"},
                {"id": "simulation", "name": "Simulation Results", "weight": 0.20, "criteria": "Positive user feedback"},
            ],
        )
        db_session.add(template)
        db_session.commit()
        
        # 创建评估报告
        report = EvaluationReport(
            id=generate_uuid(),
            project_id=project.id,
            template_id=template.id,
            scores={
                "intent_alignment": 4.5,
                "user_match": 4.2,
                "quality": 4.8,
                "simulation": 4.5,
            },
            suggestions=[
                {"id": "1", "section_id": "quality", "content": "Consider adding interactive elements", "priority": "medium", "adopted": False},
                {"id": "2", "section_id": "user_match", "content": "Include more real-world scenarios", "priority": "high", "adopted": False},
            ],
            summary="Clear content with practical examples. Areas for improvement: Add more case studies.",
            overall_score=4.5,
        )
        db_session.add(report)
        db_session.commit()
        
        # 验证
        assert report.overall_score == 4.5
        assert len(report.suggestions) == 2
    
    def test_chat_history_persistence(self, db_session):
        """测试对话历史持久化"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
        )
        db_session.add(project)
        db_session.commit()
        
        # 创建对话消息
        messages = [
            ChatMessage(
                id=generate_uuid(),
                project_id=project.id,
                role="user",
                content="Let's start the intent analysis",
                message_metadata={"phase": "intent"},
            ),
            ChatMessage(
                id=generate_uuid(),
                project_id=project.id,
                role="assistant",
                content="I'll help you clarify the project intent...",
                message_metadata={"phase": "intent"},
            ),
        ]
        for msg in messages:
            db_session.add(msg)
        db_session.commit()
        
        # 验证
        saved_messages = db_session.query(ChatMessage).filter(
            ChatMessage.project_id == project.id
        ).all()
        
        assert len(saved_messages) == 2
        assert saved_messages[0].role == "user"
        assert saved_messages[1].role == "assistant"
    
    def test_generation_log_tracking(self, db_session):
        """测试生成日志追踪"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
        )
        db_session.add(project)
        db_session.commit()
        
        field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Test Field",
        )
        db_session.add(field)
        db_session.commit()
        
        # 创建生成日志
        log = GenerationLog(
            id=generate_uuid(),
            project_id=project.id,
            field_id=field.id,
            phase="produce_inner",
            operation="generate_field",
            model="gpt-5.1",
            tokens_in=500,
            tokens_out=1000,
            duration_ms=2500,
            cost=GenerationLog.calculate_cost("gpt-5.1", 500, 1000),
            prompt_input="Test system prompt\n---\nGenerate content",
            prompt_output="Generated content here...",
            status="success",
        )
        db_session.add(log)
        db_session.commit()
        
        # 验证
        assert log.status == "success"
        assert log.tokens_out == 1000


class TestFieldTemplateUsage:
    """字段模板使用测试"""
    
    def test_create_fields_from_template(self, db_session):
        """测试从模板创建字段"""
        project = Project(
            id=generate_uuid(),
            name="Test Project",
        )
        db_session.add(project)
        db_session.commit()
        
        # 创建字段模板
        template = FieldTemplate(
            id=generate_uuid(),
            name="Course Content Template",
            category="course",
            fields=[
                {
                    "name": "Learning Objectives",
                    "type": "text",
                    "ai_prompt": "Define clear, measurable learning objectives",
                    "depends_on": [],
                },
                {
                    "name": "Content Outline",
                    "type": "structured",
                    "ai_prompt": "Create detailed content outline",
                    "depends_on": ["Learning Objectives"],
                },
                {
                    "name": "Main Content",
                    "type": "richtext",
                    "ai_prompt": "Write engaging course content",
                    "depends_on": ["Content Outline"],
                },
            ],
        )
        db_session.add(template)
        db_session.commit()
        
        # 从模板创建字段
        fields = []
        field_id_map = {}
        
        for i, template_field in enumerate(template.fields):
            field = ProjectField(
                id=generate_uuid(),
                project_id=project.id,
                template_id=template.id,
                phase="produce_inner",
                name=template_field["name"],
                field_type=template_field["type"],
                ai_prompt=template_field["ai_prompt"],
            )
            fields.append(field)
            field_id_map[template_field["name"]] = field.id
        
        # 设置依赖关系
        for i, template_field in enumerate(template.fields):
            dep_names = template_field.get("depends_on", [])
            dep_ids = [field_id_map[name] for name in dep_names if name in field_id_map]
            fields[i].dependencies = {"depends_on": dep_ids, "dependency_type": "all"}
        
        for f in fields:
            db_session.add(f)
        db_session.commit()
        
        # 验证
        saved_fields = db_session.query(ProjectField).filter(
            ProjectField.project_id == project.id
        ).all()
        
        assert len(saved_fields) == 3
        
        # 验证依赖解析顺序
        order = resolve_field_order(saved_fields)
        assert order[0][0].name == "Learning Objectives"
        assert order[1][0].name == "Content Outline"
        assert order[2][0].name == "Main Content"


class TestContextPropagationEndToEnd:
    """端到端上下文传递测试"""
    
    def test_full_context_chain(self, db_session):
        """测试完整的上下文传递链"""
        # 创建创作者特质
        profile = CreatorProfile(
            id=generate_uuid(),
            name="Medical AI Expert",
            traits={"expertise": "AI diagnostics"},
        )
        db_session.add(profile)
        db_session.commit()
        
        # 创建项目
        project = Project(
            id=generate_uuid(),
            name="AI Course",
            creator_profile_id=profile.id,
            golden_context={
                "intent": "Build comprehensive AI training",
                "consumer_personas": "Medical professionals",
            },
        )
        db_session.add(project)
        db_session.commit()
        
        # 创建依赖字段
        intro_field = ProjectField(
            id=generate_uuid(),
            project_id=project.id,
            phase="produce_inner",
            name="Introduction",
            content="Welcome to AI in Medicine course",
            status="completed",
        )
        db_session.add(intro_field)
        db_session.commit()
        
        # 构建完整上下文
        gc = prompt_engine.build_golden_context(project, creator_profile=profile)
        
        context = prompt_engine.build_prompt_context(
            project=project,
            phase="produce_inner",
            golden_context=gc,
            dependent_fields=[intro_field],
        )
        
        system_prompt = context.to_system_prompt()
        
        # 验证上下文元素存在（GoldenContext 只包含 creator_profile）
        assert "Medical AI Expert" in gc.creator_profile
        assert "Introduction" in context.field_context
        assert "Welcome to AI in Medicine" in context.field_context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

