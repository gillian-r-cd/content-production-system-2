// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板，支持字段依赖选择和生成
// 主要组件: ContentPanel, FieldCard
// 新增: 依赖选择弹窗、生成按钮、依赖状态显示、模拟阶段特殊面板

"use client";

import { useState, useEffect, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PHASE_NAMES, PROJECT_PHASES } from "@/lib/utils";
import { fieldAPI, agentAPI, blockAPI } from "@/lib/api";
import type { Field, ContentBlock } from "@/lib/api";
import { ContentBlockEditor } from "./content-block-editor";
import { ContentBlockCard } from "./content-block-card";
import { SimulationPanel } from "./simulation-panel";
import { ChannelSelector } from "./channel-selector";
import { ResearchPanel } from "./research-panel";
import { FileText, Folder, Settings, ChevronRight } from "lucide-react";

interface ContentPanelProps {
  projectId: string | null;
  currentPhase: string;
  phaseStatus?: Record<string, string>;  // 各阶段状态
  fields: Field[];
  selectedBlock?: ContentBlock | null;  // 树形视图选中的内容块
  allBlocks?: ContentBlock[];  // 所有内容块（用于依赖选择）
  useFlexibleArchitecture?: boolean;  // 项目是否使用灵活架构
  onFieldUpdate?: (fieldId: string, content: string) => void;
  onFieldsChange?: () => void;
  onPhaseAdvance?: () => void;  // 阶段推进后的回调
  onBlockSelect?: (block: ContentBlock) => void;  // 选中内容块的回调
}

export function ContentPanel({
  projectId,
  currentPhase,
  phaseStatus = {},
  fields,
  selectedBlock,
  allBlocks = [],
  useFlexibleArchitecture = false,
  onFieldUpdate,
  onFieldsChange,
  onPhaseAdvance,
  onBlockSelect,
}: ContentPanelProps) {
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [autoGeneratingFieldId, setAutoGeneratingFieldId] = useState<string | null>(null);
  const [showFieldTemplateModal, setShowFieldTemplateModal] = useState(false);
  const [fieldTemplates, setFieldTemplates] = useState<any[]>([]);
  
  const phaseFields = fields.filter((f) => f.phase === currentPhase);
  const allCompletedFields = fields.filter((f) => f.status === "completed");
  const completedFieldIds = new Set(allCompletedFields.map(f => f.id));

  // 加载字段模板
  useEffect(() => {
    import("@/lib/api").then(({ settingsAPI }) => {
      settingsAPI.listFieldTemplates().then(setFieldTemplates).catch(console.error);
    });
  }, []);

  // 添加空字段
  const handleAddEmptyField = async () => {
    if (!projectId) return;
    try {
      await fieldAPI.create({
        project_id: projectId,
        phase: currentPhase,
        name: `新字段 ${phaseFields.length + 1}`,
        field_type: "richtext",
        content: "",
        status: "pending",
        ai_prompt: "",  // 空字符串，在约束弹窗中设置
        dependencies: { depends_on: [], dependency_type: "all" },
        need_review: true,
      });
      onFieldsChange?.();
    } catch (err) {
      console.error("添加字段失败:", err);
      alert("添加字段失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 从模板添加字段
  const handleAddFromTemplate = async (template: any) => {
    if (!projectId) return;
    try {
      const templateFields = template.fields || [];
      
      // 获取现有字段名以处理重复
      const existingNames = phaseFields.map(f => f.name);
      
      // 生成唯一名称的辅助函数
      const getUniqueName = (baseName: string): string => {
        if (!existingNames.includes(baseName)) {
          existingNames.push(baseName);
          return baseName;
        }
        let counter = 1;
        while (existingNames.includes(`${baseName} ${counter}`)) {
          counter++;
        }
        const uniqueName = `${baseName} ${counter}`;
        existingNames.push(uniqueName);
        return uniqueName;
      };
      
      // 第一轮：创建所有字段，记录 name -> id 映射
      const nameToIdMap: Record<string, string> = {};
      const createdFields: any[] = [];
      
      for (const tf of templateFields) {
        const uniqueName = getUniqueName(tf.name);
        const newField = await fieldAPI.create({
          project_id: projectId,
          phase: currentPhase,
          name: uniqueName,
          field_type: tf.type || "richtext",
          content: "",
          status: "pending",
          ai_prompt: tf.ai_prompt || "",
          pre_questions: tf.pre_questions || [],
          dependencies: { depends_on: [], dependency_type: "all" },
          need_review: true,
        });
        nameToIdMap[tf.name] = newField.id;
        createdFields.push({ field: newField, templateField: tf });
      }
      
      // 第二轮：更新依赖关系（将模板中的字段名转换为实际的字段 ID）
      for (const { field, templateField } of createdFields) {
        const templateDeps = templateField.depends_on || [];
        if (templateDeps.length > 0) {
          const realDepsIds = templateDeps
            .map((depName: string) => nameToIdMap[depName])
            .filter(Boolean);
          
          if (realDepsIds.length > 0) {
            await fieldAPI.update(field.id, {
              dependencies: { depends_on: realDepsIds, dependency_type: "all" },
            });
          }
        }
      }
      
      setShowFieldTemplateModal(false);
      onFieldsChange?.();
    } catch (err) {
      console.error("从模板添加失败:", err);
      alert("从模板添加失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 自动触发生成：检查是否有字段可以自动生成
  const checkAndAutoGenerate = async () => {
    if (autoGeneratingFieldId) return; // 已有自动生成在进行中
    
    // 找到可以自动生成的字段：pending、need_review=false、依赖已满足
    const autoGeneratableField = phaseFields.find(field => {
      if (field.status !== "pending") return false;
      if (field.need_review !== false) return false; // 需要人工确认的跳过
      
      const dependsOn = field.dependencies?.depends_on || [];
      if (dependsOn.length === 0) return true; // 无依赖
      
      // 检查所有依赖是否完成
      const allDepsCompleted = dependsOn.every(depId => completedFieldIds.has(depId));
      return allDepsCompleted;
    });
    
    if (autoGeneratableField) {
      console.log(`[AutoGen] 自动触发生成: ${autoGeneratableField.name}`);
      setAutoGeneratingFieldId(autoGeneratableField.id);
      
      try {
        // 调用流式生成 API
        const response = await fetch(`http://localhost:8000/api/fields/${autoGeneratableField.id}/generate/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pre_answers: autoGeneratableField.pre_answers || {} }),
        });
        
        // 等待生成完成
        const reader = response.body?.getReader();
        if (reader) {
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        }
        
        // 刷新字段列表
        onFieldsChange?.();
      } catch (err) {
        console.error("[AutoGen] 自动生成失败:", err);
      } finally {
        setAutoGeneratingFieldId(null);
      }
    }
  };

  // 当字段列表变化时，检查是否有字段可以自动生成
  useEffect(() => {
    if (currentPhase === "produce_inner" && phaseFields.length > 0) {
      checkAndAutoGenerate();
    }
  }, [fields, currentPhase]); // 依赖 fields 变化
  
  // 判断当前阶段是否可以进入下一阶段
  const phaseHasContent = phaseFields.length > 0 && phaseFields.some(f => f.status === "completed");
  const currentPhaseIndex = PROJECT_PHASES.indexOf(currentPhase);
  const isLastPhase = currentPhaseIndex === PROJECT_PHASES.length - 1;
  const nextPhase = isLastPhase ? null : PROJECT_PHASES[currentPhaseIndex + 1];
  
  // 内涵设计阶段不再使用特殊的方案格式检测
  // 改为与其他阶段一致的字段列表视图

  // 消费者调研阶段：检查是否是JSON格式
  const researchField = phaseFields.find(
    (f) => f.phase === "research" && f.name === "消费者调研报告"
  );
  
  const isResearchJsonFormat = useMemo(() => {
    if (currentPhase !== "research" || !researchField?.content) {
      return false;
    }
    try {
      const data = JSON.parse(researchField.content);
      return data.summary && data.personas && Array.isArray(data.personas);
    } catch {
      return false;
    }
  }, [currentPhase, researchField?.content]);
  
  // 确认进入下一阶段
  const handleAdvancePhase = async () => {
    if (!projectId || !nextPhase) return;
    
    setIsAdvancing(true);
    try {
      await agentAPI.advance(projectId);
      onPhaseAdvance?.();
    } catch (err) {
      console.error("进入下一阶段失败:", err);
      alert("进入下一阶段失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsAdvancing(false);
    }
  };

  // ===== 早期返回（在所有Hooks之后）=====
  
  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500">
        <div className="text-center">
          <p className="text-lg mb-2">请选择或创建一个项目</p>
          <p className="text-sm">在左侧选择项目开始工作</p>
        </div>
      </div>
    );
  }

  // ===== 树形视图选中内容块时，显示该块详情 =====
  
  // 处理阶段块点击（从树形视图点击阶段节点）
  if (selectedBlock && selectedBlock.block_type === "phase") {
    // 判断是虚拟块还是真正的 ContentBlock
    const isVirtualBlock = selectedBlock.id.startsWith("virtual_phase_");
    
    // 从虚拟块ID中提取阶段名称（格式：virtual_phase_xxx）
    const phaseMatch = selectedBlock.id.match(/virtual_phase_(.+)/);
    const selectedPhase = phaseMatch ? phaseMatch[1] : selectedBlock.special_handler;
    
    // 如果是真正的 ContentBlock 阶段/分组（灵活架构），显示其所有子节点
    if (!isVirtualBlock && selectedBlock.children && selectedBlock.children.length > 0) {
      // 统计不同类型的子节点
      const phaseCount = selectedBlock.children.filter(c => c.block_type === "phase").length;
      const groupCount = selectedBlock.children.filter(c => c.block_type === "group").length;
      const fieldCount = selectedBlock.children.filter(c => c.block_type === "field").length;
      const otherCount = selectedBlock.children.length - phaseCount - groupCount - fieldCount;
      
      // 生成描述文字
      const parts = [];
      if (phaseCount > 0) parts.push(`${phaseCount} 个子阶段`);
      if (groupCount > 0) parts.push(`${groupCount} 个分组`);
      if (fieldCount > 0) parts.push(`${fieldCount} 个字段`);
      if (otherCount > 0) parts.push(`${otherCount} 个其他`);
      const description = parts.join("、") || "暂无内容";
      
      return (
        <div className="h-full flex flex-col">
          <div className="p-4 border-b border-surface-3">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 text-xs rounded ${
                selectedBlock.block_type === "phase" 
                  ? "bg-purple-600/20 text-purple-400"
                  : "bg-amber-600/20 text-amber-400"
              }`}>
                {selectedBlock.block_type === "phase" ? "阶段" : "分组"}
              </span>
              <h1 className="text-xl font-bold text-zinc-100">{selectedBlock.name}</h1>
            </div>
            <p className="text-zinc-500 text-sm mt-1">
              包含 {description}
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {selectedBlock.children.map((child) => (
                <ContentBlockCard
                  key={child.id}
                  block={child}
                  projectId={projectId || ""}
                  allBlocks={allBlocks}
                  isVirtual={false}
                  onUpdate={onFieldsChange}
                  onSelect={() => onBlockSelect?.(child)}
                />
              ))}
            </div>
          </div>
        </div>
      );
    }
    
    // 如果是没有子块的阶段（空阶段或虚拟阶段）
    if (!isVirtualBlock && (!selectedBlock.children || selectedBlock.children.length === 0)) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-zinc-500">
          <p className="text-lg mb-2">{selectedBlock.name}</p>
          <p className="text-sm">该阶段暂无字段，请在左侧添加</p>
        </div>
      );
    }
    
    if (selectedPhase) {
      // 获取该阶段的所有字段（虚拟块模式）
      const phaseFields = fields.filter(f => f.phase === selectedPhase);
      
      // ===== 特殊阶段处理 =====
      
      // 消费者调研阶段
      if (selectedPhase === "research") {
        const researchField = phaseFields.find(f => f.name === "消费者调研报告");
        if (researchField) {
          try {
            const researchData = JSON.parse(researchField.content || "{}");
            if (researchData.summary || researchData.personas) {
              return (
                <ResearchPanel
                  projectId={projectId}
                  fieldId={researchField.id}
                  content={researchField.content}
                  onUpdate={onFieldsChange}
                  onAdvance={handleAdvancePhase}
                />
              );
            }
          } catch {
            // JSON 解析失败
          }
        }
      }
      
      // 内涵设计阶段 - 不再使用特殊处理，与其他阶段一致
      // 方案导入功能通过字段的 ProposalSelector 组件提供
      // 用户点击"内涵设计方案"字段时可以查看和导入方案
      
      // 外延设计阶段 - 使用 ChannelSelector
      if (selectedPhase === "design_outer") {
        const designOuterField = phaseFields.find(f => f.name === "外延设计方案");
        if (designOuterField) {
          try {
            const channelsData = JSON.parse(designOuterField.content || "{}");
            if (channelsData.channels && Array.isArray(channelsData.channels)) {
              return (
                <div className="h-full flex flex-col">
                  <div className="p-4 border-b border-surface-3">
                    <h1 className="text-xl font-bold text-zinc-100">外延设计</h1>
                    <p className="text-zinc-500 text-sm mt-1">
                      选择要使用的传播渠道，确认后进入外延生产
                    </p>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4">
                    <ChannelSelector
                      projectId={projectId}
                      fieldId={designOuterField.id}
                      content={designOuterField.content}
                      onConfirm={() => {
                        onFieldsChange?.();
                        onPhaseAdvance?.();
                      }}
                      onFieldsCreated={onFieldsChange}
                      onSave={onFieldsChange}
                    />
                  </div>
                </div>
              );
            }
          } catch {
            // JSON 解析失败
          }
        }
      }
      
      // 外延生产阶段 - 显示渠道字段列表（使用 FieldCard 提供完整编辑功能）
      if (selectedPhase === "produce_outer" && phaseFields.length > 0) {
        return (
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-surface-3">
              <h1 className="text-xl font-bold text-zinc-100">外延生产</h1>
              <p className="text-zinc-500 text-sm mt-1">
                共 {phaseFields.length} 个渠道 - 可展开编辑所有设置
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="space-y-4">
                {phaseFields.map(field => (
                  <FieldCard
                    key={field.id}
                    field={field}
                    allFields={fields}
                    onUpdate={(content) => onFieldUpdate?.(field.id, content)}
                    onFieldsChange={onFieldsChange}
                  />
                ))}
              </div>
            </div>
          </div>
        );
      }
      
      // 消费者模拟阶段
      if (selectedPhase === "simulate") {
        return (
          <SimulationPanel
            projectId={projectId}
            fields={fields}
            onSimulationCreated={onFieldsChange}
          />
        );
      }
      
      // 内涵生产阶段 - 显示字段列表（使用 FieldCard 提供完整编辑功能）
      if (selectedPhase === "produce_inner" && phaseFields.length > 0) {
        return (
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-surface-3">
              <h1 className="text-xl font-bold text-zinc-100">
                {PHASE_NAMES[selectedPhase] || selectedPhase}
              </h1>
              <p className="text-zinc-500 text-sm mt-1">
                共 {phaseFields.length} 个字段 - 可展开编辑所有设置
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="space-y-4">
                {phaseFields.map(field => (
                  <FieldCard
                    key={field.id}
                    field={field}
                    allFields={fields}
                    onUpdate={(content) => onFieldUpdate?.(field.id, content)}
                    onFieldsChange={onFieldsChange}
                  />
                ))}
              </div>
            </div>
          </div>
        );
      }
      
      // 其他阶段 - 显示阶段概览（使用 FieldCard 提供完整编辑功能）
      return (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="p-6 pb-0">
            <h1 className="text-xl font-bold text-zinc-100 mb-2">
              {PHASE_NAMES[selectedPhase] || selectedPhase}
            </h1>
            <p className="text-zinc-500 mb-4">
              共有 {phaseFields.length} 个字段 - 点击字段可编辑
            </p>
          </div>
          <div className="flex-1 overflow-y-auto px-6 pb-6">
            {phaseFields.length > 0 ? (
              <div className="space-y-4">
                {phaseFields.map(field => (
                  <FieldCard
                    key={field.id}
                    field={field}
                    allFields={fields}
                    onUpdate={(content: string) => onFieldUpdate?.(field.id, content)}
                    onFieldsChange={onFieldsChange}
                  />
                ))}
              </div>
            ) : (
              <p className="text-zinc-500">该阶段暂无内容字段</p>
            )}
          </div>
        </div>
      );
    }
  }
  
  // 处理字段块点击
  if (selectedBlock && selectedBlock.block_type === "field") {
    // ===== 检查 special_handler：显示对应的特殊界面 =====
    const handler = selectedBlock.special_handler as string | null | undefined;
    
    // 消费者模拟字段 - 使用 SimulationPanel
    if (handler === "consumer_simulation" || handler === "simulate") {
      return (
        <SimulationPanel
          projectId={projectId}
          fields={fields}
          onSimulationCreated={onFieldsChange}
        />
      );
    }
    
    // 消费者调研字段 - 检查是否有结构化内容
    if (handler === "consumer_research" || handler === "research") {
      // 尝试解析内容
      try {
        const researchData = JSON.parse(selectedBlock.content || "{}");
        if (researchData.summary && researchData.personas) {
          return (
            <ResearchPanel
              projectId={projectId}
              fieldId={selectedBlock.id}
              content={selectedBlock.content}
              onUpdate={onFieldsChange}
              onAdvance={handleAdvancePhase}
            />
          );
        }
      } catch {
        // JSON 解析失败，继续使用默认编辑器
      }
    }
    
    // 意图分析字段 - 由 Agent 处理，显示提示
    if (handler === "intent_analysis" || handler === "intent") {
      return (
        <div className="h-full flex flex-col items-center justify-center p-6 text-center">
          <div className="text-6xl mb-4">💬</div>
          <h2 className="text-xl font-bold text-zinc-200 mb-2">意图分析</h2>
          <p className="text-zinc-400 max-w-md">
            意图分析由 AI Agent 通过对话完成。请在右侧对话框中输入"开始"来启动意图分析流程。
          </p>
          <p className="text-zinc-500 text-sm mt-4">
            Agent 会问你 3 个问题来了解你的项目意图。
          </p>
        </div>
      );
    }
    
    // 尝试找到对应的传统 Field（虚拟树形视图使用真实的 field.id）
    const matchingField = fields.find(f => f.id === selectedBlock.id);
    
    // 如果找到对应的传统 Field
    if (matchingField) {
      // ===== 特殊处理：消费者调研报告 =====
      if (matchingField.phase === "research" && matchingField.name === "消费者调研报告") {
        try {
          const researchData = JSON.parse(matchingField.content || "{}");
          if (researchData.summary && researchData.personas) {
            return (
              <ResearchPanel
                projectId={projectId}
                fieldId={matchingField.id}
                content={matchingField.content}
                onUpdate={onFieldsChange}
                onAdvance={handleAdvancePhase}
              />
            );
          }
        } catch {
          // JSON 解析失败，使用默认 FieldCard
        }
      }
      
      // 默认：使用 FieldCard 显示完整功能
      return (
        <div className="h-full flex flex-col p-6">
          {/* 面包屑导航 */}
          <div className="flex items-center gap-2 text-sm text-zinc-500 mb-4">
            <Folder className="w-4 h-4" />
            <span>{PHASE_NAMES[matchingField.phase] || matchingField.phase}</span>
            <ChevronRight className="w-3 h-3" />
            <FileText className="w-4 h-4" />
            <span className="text-zinc-300">{matchingField.name}</span>
          </div>
          
          {/* 使用 FieldCard 显示完整功能 */}
          <div className="flex-1 overflow-y-auto">
            <FieldCard
              key={matchingField.id}
              field={matchingField}
              allFields={fields}
              onUpdate={(content: string) => onFieldUpdate?.(matchingField.id, content)}
              onFieldsChange={onFieldsChange}
            />
          </div>
        </div>
      );
    }
    
    // 显示 ContentBlock 编辑界面
    // isVirtual: 如果项目不使用灵活架构，则是虚拟块（来自 ProjectField）
    return (
      <ContentBlockEditor
        block={selectedBlock}
        projectId={projectId}
        allBlocks={allBlocks}
        isVirtual={!useFlexibleArchitecture}
        onUpdate={onFieldsChange}
      />
    );
  }
  
  // 灵活架构项目：没有选中块时，提示用户从左侧树形结构选择
  if (useFlexibleArchitecture && !selectedBlock) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center">
        <div className="text-6xl mb-4">🌲</div>
        <h2 className="text-xl font-bold text-zinc-200 mb-2">树形架构模式</h2>
        <p className="text-zinc-400 max-w-md">
          请在左侧树形结构中选择一个阶段或字段来查看和编辑内容。
        </p>
        <p className="text-zinc-500 text-sm mt-4">
          传统视图已锁定，所有操作通过树形结构进行。
        </p>
      </div>
    );
  }

  // 消费者模拟阶段使用专用面板
  if (currentPhase === "simulate") {
    return (
      <SimulationPanel
        projectId={projectId}
        fields={fields}
        onSimulationCreated={onFieldsChange}
      />
    );
  }

  // 消费者调研阶段：使用调研面板
  if (currentPhase === "research" && isResearchJsonFormat && researchField) {
    return (
      <ResearchPanel
        projectId={projectId}
        fieldId={researchField.id}
        content={researchField.content}
        onUpdate={onFieldsChange}
        onAdvance={handleAdvancePhase}
      />
    );
  }

  // 内涵设计阶段不再使用特殊的 ProposalSelector
  // 改为与其他阶段一致的字段列表视图

  // 构建字段ID到字段名称的映射（用于显示依赖）
  const fieldNameMap = Object.fromEntries(fields.map(f => [f.id, f.name]));
  
  // 滚动到指定字段
  const scrollToField = (fieldId: string) => {
    const element = document.getElementById(`field-${fieldId}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="h-full flex">
      {/* 内涵生产阶段：左侧字段目录 */}
      {currentPhase === "produce_inner" && phaseFields.length > 0 && (
        <div className="w-56 shrink-0 border-r border-surface-3 p-4 overflow-auto">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
            字段目录
          </h3>
          <div className="space-y-1">
            {phaseFields.map((field, index) => {
              const deps = field.dependencies?.depends_on || [];
              const depsComplete = deps.every(depId => 
                fields.find(f => f.id === depId)?.status === "completed"
              );
              
              return (
                <button
                  key={field.id}
                  onClick={() => scrollToField(field.id)}
                  className="w-full text-left p-2 rounded-lg hover:bg-surface-3 transition-colors group"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-600">{index + 1}</span>
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      field.status === "completed" ? "bg-green-500" :
                      field.status === "generating" ? "bg-yellow-500 animate-pulse" :
                      "bg-zinc-600"
                    }`} />
                    <span className="text-sm text-zinc-300 truncate flex-1">
                      {field.name}
                    </span>
                  </div>
                  {/* 依赖显示 */}
                  {deps.length > 0 && (
                    <div className="mt-1 ml-6 text-xs text-zinc-600">
                      ← {deps.map(d => fieldNameMap[d] || "?").join(", ")}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          
          {/* 添加字段按钮 */}
          <div className="mt-4 space-y-2">
            <button
              onClick={() => handleAddEmptyField()}
              className="w-full py-2 text-xs bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
            >
              + 添加字段
            </button>
            <button
              onClick={() => setShowFieldTemplateModal(true)}
              className="w-full py-2 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded-lg transition-colors"
            >
              📦 从模板添加
            </button>
          </div>
          
          {/* 依赖关系图例 */}
          <div className="mt-6 pt-4 border-t border-surface-3">
            <div className="text-xs text-zinc-600 space-y-1">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>已完成</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span>生成中</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-zinc-600" />
                <span>待生成</span>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* 主内容区 */}
      <div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto">
        {/* 阶段标题 */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-zinc-100">
            {PHASE_NAMES[currentPhase] || currentPhase}
          </h1>
          <p className="text-zinc-500 mt-1">
            {getPhaseDescription(currentPhase)}
          </p>
        </div>

        {/* 字段列表 */}
        {phaseFields.length > 0 ? (
          <div className="space-y-6">
            {phaseFields.map((field) => (
              <div key={field.id} id={`field-${field.id}`}>
                <FieldCard
                  field={field}
                  allFields={fields}
                  onUpdate={(content) => onFieldUpdate?.(field.id, content)}
                  onFieldsChange={onFieldsChange}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12 text-zinc-500">
            <p>当前阶段暂无内容</p>
            <p className="text-sm mt-2">
              在右侧与 AI Agent 对话开始生产内容
            </p>
          </div>
        )}
      
      {/* 确认进入下一阶段按钮 */}
      {phaseHasContent && nextPhase && (() => {
        const isPhaseCompleted = phaseStatus[currentPhase] === "completed";
        
        return (
          <div className="mt-8 pt-6 border-t border-surface-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-zinc-400 text-sm">
                  {isPhaseCompleted ? "✅ 当前阶段已确认" : "当前阶段内容已完成"}
                </p>
                <p className="text-zinc-500 text-xs mt-1">
                  下一阶段：{PHASE_NAMES[nextPhase] || nextPhase}
                </p>
              </div>
              {isPhaseCompleted ? (
                <div className="px-6 py-3 rounded-xl font-medium bg-green-600/20 text-green-400 border border-green-500/30">
                  ✅ 已确认
                </div>
              ) : (
                <button
                  onClick={handleAdvancePhase}
                  disabled={isAdvancing}
                  className={`px-6 py-3 rounded-xl font-medium transition-all ${
                    isAdvancing
                      ? "bg-zinc-700 text-zinc-400 cursor-wait"
                      : "bg-brand-600 hover:bg-brand-700 text-white shadow-lg hover:shadow-brand-600/25"
                  }`}
                >
                  {isAdvancing ? (
                    <span className="flex items-center gap-2">
                      <span className="animate-spin">⏳</span> 处理中...
                    </span>
                  ) : (
                    <span>✅ 确认，进入下一阶段</span>
                  )}
                </button>
              )}
            </div>
          </div>
        );
      })()}
      </div>

      {/* 字段模板选择弹窗 */}
      {showFieldTemplateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-3">
              <h3 className="font-medium text-zinc-200">从模板添加字段</h3>
              <p className="text-xs text-zinc-500 mt-1">
                选择一个模板添加到当前阶段
              </p>
            </div>

            <div className="p-4 max-h-[50vh] overflow-y-auto space-y-2">
              {fieldTemplates.length > 0 ? (
                fieldTemplates.map((template) => (
                  <button
                    key={template.id}
                    onClick={() => handleAddFromTemplate(template)}
                    className="w-full text-left p-4 rounded-lg bg-surface-1 border border-surface-3 hover:bg-surface-3 hover:border-brand-500/50 transition-all"
                  >
                    <div className="font-medium text-zinc-200">{template.name}</div>
                    <div className="text-xs text-zinc-500 mt-1">{template.description}</div>
                    <div className="text-xs text-zinc-600 mt-2">
                      📦 {template.fields?.length || 0} 个字段
                    </div>
                  </button>
                ))
              ) : (
                <p className="text-zinc-500 text-center py-8">
                  暂无字段模板，请在后台设置中添加
                </p>
              )}
            </div>

            <div className="px-4 py-3 border-t border-surface-3 flex justify-end">
              <button
                onClick={() => setShowFieldTemplateModal(false)}
                className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface FieldCardProps {
  field: Field;
  allFields: Field[];
  onUpdate?: (content: string) => void;
  onFieldsChange?: () => void;
}

function FieldCard({ field, allFields, onUpdate, onFieldsChange }: FieldCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(field.name);
  const [content, setContent] = useState(field.content);
  const [showDependencyModal, setShowDependencyModal] = useState(false);
  const [showConstraintsModal, setShowConstraintsModal] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatingContent, setGeneratingContent] = useState("");
  // 预提问相关状态
  const [showPreQuestions, setShowPreQuestions] = useState(false);
  const [preAnswers, setPreAnswers] = useState<Record<string, string>>(
    field.pre_answers || {}
  );
  const [isSavingPreAnswers, setIsSavingPreAnswers] = useState(false);
  const [preAnswersSaved, setPreAnswersSaved] = useState(false);
  const hasPreQuestions = field.pre_questions && field.pre_questions.length > 0;
  
  // 复制状态
  const [copied, setCopied] = useState(false);
  const handleCopyContent = () => {
    const text = field.content || content;
    if (text) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };
  
  // 保存预提问答案
  const handleSavePreAnswers = async () => {
    setIsSavingPreAnswers(true);
    try {
      await fieldAPI.update(field.id, { pre_answers: preAnswers });
      setPreAnswersSaved(true);
      setTimeout(() => setPreAnswersSaved(false), 2000);
      onFieldsChange?.();
    } catch (err) {
      console.error("保存答案失败:", err);
      alert("保存失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsSavingPreAnswers(false);
    }
  };

  useEffect(() => {
    setContent(field.content);
  }, [field.content]);

  // 获取依赖字段信息
  const dependsOnIds = field.dependencies?.depends_on || [];
  const dependencyFields = allFields.filter((f) => dependsOnIds.includes(f.id));
  const unmetDependencies = dependencyFields.filter((f) => f.status !== "completed");
  const canGenerate = unmetDependencies.length === 0;

  const handleSave = () => {
    onUpdate?.(content);
    setIsEditing(false);
  };

  const handleGenerate = async () => {
    if (!canGenerate) {
      alert(`请先完成依赖字段: ${unmetDependencies.map(f => f.name).join(", ")}`);
      return;
    }
    
    // 如果有预提问但还没展开，先展开让用户填写
    if (hasPreQuestions && !showPreQuestions && Object.keys(preAnswers).length === 0) {
      setShowPreQuestions(true);
      return;
    }

    setIsGenerating(true);
    setGeneratingContent("");
    setShowPreQuestions(false);

    try {
      // 使用流式生成，传递预回答
      const response = await fetch(`http://localhost:8000/api/fields/${field.id}/generate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pre_answers: preAnswers }),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value);
          const lines = text.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.chunk) {
                  setGeneratingContent((prev) => prev + data.chunk);
                }
                if (data.done) {
                  onFieldsChange?.();
                }
              } catch {}
            }
          }
        }
      }
    } catch (err) {
      console.error("生成失败:", err);
      alert("生成失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsGenerating(false);
    }
  };

  const handleUpdateDependencies = async (newDependsOn: string[]) => {
    try {
      await fieldAPI.update(field.id, {
        dependencies: {
          depends_on: newDependsOn,
          dependency_type: field.dependencies?.dependency_type || "all",
        },
      });
      onFieldsChange?.();
      setShowDependencyModal(false);
    } catch (err) {
      alert("更新依赖失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleUpdateConstraints = async (newConstraints: {
    ai_prompt?: string | null;
    max_length?: number | null;
    output_format?: string;
    structure?: string | null;
    example?: string | null;
  }) => {
    try {
      // 分离 ai_prompt 和 constraints
      const { ai_prompt, ...constraints } = newConstraints;
      
      await fieldAPI.update(field.id, { 
        ai_prompt: ai_prompt || "",
        constraints 
      });
      onFieldsChange?.();
      setShowConstraintsModal(false);
    } catch (err) {
      alert("更新约束失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  const handleSaveName = async () => {
    if (editedName.trim() && editedName !== field.name) {
      try {
        await fieldAPI.update(field.id, { name: editedName.trim() });
        onFieldsChange?.();
      } catch (err) {
        alert("更新名称失败: " + (err instanceof Error ? err.message : "未知错误"));
        setEditedName(field.name);  // 恢复原名称
      }
    }
    setIsEditingName(false);
  };

  const handleDelete = async () => {
    if (!confirm(`确定要删除字段「${field.name}」吗？此操作不可撤销。`)) return;
    try {
      await fieldAPI.delete(field.id);
      onFieldsChange?.();
    } catch (err) {
      alert("删除失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  return (
    <div className="bg-surface-2 rounded-xl border border-surface-3 overflow-hidden">
      {/* 字段头部 */}
      <div className="px-4 py-3 border-b border-surface-3">
        <div className="flex items-center justify-between">
          <div>
            {isEditingName ? (
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                onBlur={handleSaveName}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") {
                    setEditedName(field.name);
                    setIsEditingName(false);
                  }
                }}
                className="font-medium text-zinc-200 bg-surface-1 border border-surface-3 rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-brand-500"
                autoFocus
              />
            ) : (
              <h3 
                className="font-medium text-zinc-200 cursor-pointer hover:text-brand-400 transition-colors"
                onClick={() => setIsEditingName(true)}
                title="点击编辑标题"
              >
                {field.name} <span className="text-xs text-zinc-600">✏️</span>
              </h3>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className={`text-xs px-2 py-0.5 rounded ${
                field.status === "completed" 
                  ? "bg-green-600/20 text-green-400"
                  : field.status === "generating"
                  ? "bg-yellow-600/20 text-yellow-400"
                  : "bg-zinc-600/20 text-zinc-400"
              }`}>
                {field.status === "completed" ? "已生成" 
                  : field.status === "generating" ? "生成中..." 
                  : "待生成"}
              </span>
            </div>
          </div>
          
          <div className="flex gap-2">
            {/* 未完成 + 不在生成中：显示生成按钮 */}
            {field.status !== "completed" && !isGenerating && (
              <button
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                  canGenerate
                    ? "bg-brand-600 hover:bg-brand-700 text-white"
                    : "bg-zinc-700 text-zinc-500 cursor-not-allowed"
                }`}
                title={canGenerate ? "生成内容" : `依赖未满足: ${unmetDependencies.map(f => f.name).join(", ")}`}
              >
                生成
              </button>
            )}
            
            {/* 已完成：显示重新生成按钮 */}
            {field.status === "completed" && !isGenerating && (
              <button
                onClick={handleGenerate}
                className="px-3 py-1 text-sm bg-amber-600/20 hover:bg-amber-600/30 text-amber-400 border border-amber-500/30 rounded-lg transition-colors"
                title="重新生成内容（会覆盖现有内容）"
              >
                🔄 重新生成
              </button>
            )}
            
            {isEditing ? (
              <>
                <button
                  onClick={handleSave}
                  className="px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
                >
                  保存
                </button>
                <button
                  onClick={() => {
                    setContent(field.content);
                    setIsEditing(false);
                  }}
                  className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
                >
                  取消
                </button>
              </>
            ) : (
              <button
                onClick={() => setIsEditing(true)}
                className="px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
              >
                编辑
              </button>
            )}
            
            {/* 删除按钮 */}
            <button
              onClick={handleDelete}
              className="px-3 py-1 text-sm bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30 rounded-lg transition-colors"
              title="删除此字段"
            >
              🗑️
            </button>
          </div>
        </div>

        {/* 依赖关系 + 约束显示 */}
        <div className="mt-2 flex items-center gap-4 flex-wrap text-xs">
          {/* 依赖关系 */}
          <button
            onClick={() => setShowDependencyModal(true)}
            className="text-zinc-500 hover:text-zinc-300 flex items-center gap-1"
          >
            <span>📎 依赖:</span>
            {dependencyFields.length > 0 ? (
              dependencyFields.map((df) => (
                <span
                  key={df.id}
                  className={`px-1.5 py-0.5 rounded ${
                    df.status === "completed"
                      ? "bg-green-600/20 text-green-400"
                      : "bg-red-600/20 text-red-400"
                  }`}
                >
                  {df.name}
                </span>
              ))
            ) : (
              <span className="text-zinc-600">无</span>
            )}
          </button>
          
          {/* 生成配置概览（可点击编辑） */}
          <button
            onClick={() => setShowConstraintsModal(true)}
            className="flex items-center gap-2 text-zinc-600 hover:text-zinc-400 transition-colors flex-wrap"
          >
            {/* AI 提示词状态 */}
            <span className={`flex items-center gap-1 ${
              field.ai_prompt && field.ai_prompt !== "请在这里编写生成提示词..." 
                ? "text-brand-400" 
                : "text-red-400"
            }`}>
              {field.ai_prompt && field.ai_prompt !== "请在这里编写生成提示词..." ? (
                <>
                  <span>✨</span>
                  <span className="px-1.5 py-0.5 bg-brand-600/20 rounded max-w-[150px] truncate" title={field.ai_prompt}>
                    {field.ai_prompt.slice(0, 20)}{field.ai_prompt.length > 20 ? "..." : ""}
                  </span>
                </>
              ) : (
                <>
                  <span>⚠️</span>
                  <span className="px-1.5 py-0.5 bg-red-600/20 rounded">未设置提示词</span>
                </>
              )}
            </span>
            
            {/* 约束标签 */}
            {field.constraints?.max_length ? (
              <span className="px-1.5 py-0.5 bg-surface-3 rounded text-zinc-400" title="最大字数">
                ≤{field.constraints.max_length}字
              </span>
            ) : null}
            {field.constraints?.output_format && field.constraints.output_format !== "markdown" ? (
              <span className="px-1.5 py-0.5 bg-surface-3 rounded text-zinc-400" title="输出格式">
                {field.constraints.output_format}
              </span>
            ) : null}
            
            <span className="text-xs text-zinc-600">（点击配置）</span>
          </button>
        </div>
      </div>

      {/* 预提问区域（模板定义的生成前提问） */}
      {showPreQuestions && hasPreQuestions && (
        <div className="mx-4 mb-4 p-4 bg-surface-1 border border-amber-500/30 rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium text-amber-400 flex items-center gap-2">
              <span>📝</span>
              生成前请先回答以下问题
            </h4>
            <div className="flex items-center gap-2">
              {preAnswersSaved && (
                <span className="text-xs text-green-400">✓ 已保存</span>
              )}
              <button
                onClick={handleSavePreAnswers}
                disabled={isSavingPreAnswers}
                className="px-3 py-1 text-xs bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 text-white rounded transition-colors"
              >
                {isSavingPreAnswers ? "保存中..." : "保存回答"}
              </button>
            </div>
          </div>
          <div className="space-y-3">
            {field.pre_questions.map((question: string, index: number) => (
              <div key={index}>
                <label className="block text-xs text-zinc-400 mb-1">
                  {index + 1}. {question}
                </label>
                <input
                  type="text"
                  value={preAnswers[question] || ""}
                  onChange={(e) => {
                    setPreAnswers({
                      ...preAnswers,
                      [question]: e.target.value,
                    });
                    setPreAnswersSaved(false);
                  }}
                  placeholder="请输入您的回答..."
                  className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            💡 填写完毕后请点击「保存回答」按钮保存答案
          </p>
          <div className="mt-4 flex gap-2 justify-end">
            <button
              onClick={() => setShowPreQuestions(false)}
              className="px-3 py-1.5 text-sm bg-surface-3 hover:bg-surface-4 text-zinc-400 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleGenerate}
              className="px-4 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
            >
              ✅ 确认并生成
            </button>
          </div>
        </div>
      )}

      {/* 预提问提示（显示在内容区域上方） */}
      {hasPreQuestions && !showPreQuestions && !field.content && (
        <div className="mx-4 mb-2 p-3 bg-amber-900/20 border border-amber-500/30 rounded-lg">
          <div className="flex items-center gap-2 text-sm text-amber-400">
            <span>📝</span>
            <span>此字段有 {field.pre_questions.length} 个预设问题需要回答</span>
          </div>
          <ul className="mt-2 space-y-1 text-xs text-zinc-400">
            {field.pre_questions.slice(0, 3).map((q: string, i: number) => (
              <li key={i}>• {q}</li>
            ))}
            {field.pre_questions.length > 3 && (
              <li className="text-zinc-500">...还有 {field.pre_questions.length - 3} 个问题</li>
            )}
          </ul>
        </div>
      )}

      {/* 字段内容 */}
      <div className="p-4">
        {isGenerating ? (
          <div className="bg-surface-1 border border-surface-3 rounded-lg p-3">
            <div className="text-xs text-brand-400 mb-2">正在生成...</div>
            <div className="whitespace-pre-wrap text-zinc-300 animate-pulse">
              {generatingContent || "⏳ 准备中..."}
            </div>
          </div>
        ) : isEditing ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="w-full min-h-[200px] bg-surface-1 border border-surface-3 rounded-lg p-3 text-zinc-200 resize-y focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        ) : (
          <div className="relative">
            {/* 复制按钮 */}
            {field.content && (
              <button
                onClick={handleCopyContent}
                className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 text-xs bg-surface-3 hover:bg-surface-4 text-zinc-400 hover:text-zinc-200 rounded transition-colors z-10"
                title="复制全文（Markdown格式）"
              >
                {copied ? "✓ 已复制" : "📋 复制"}
              </button>
            )}
            <div className="prose prose-invert max-w-none prose-headings:text-zinc-100 prose-p:text-zinc-300 prose-li:text-zinc-300 prose-strong:text-zinc-200">
              {field.content ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{field.content}</ReactMarkdown>
              ) : hasPreQuestions && !showPreQuestions ? (
                <p className="text-zinc-500 italic">
                  此字段有预设问题需要回答，点击"生成"按钮开始
                </p>
              ) : (
                <p className="text-zinc-500 italic">暂无内容，点击"生成"按钮开始</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* 依赖选择弹窗 */}
      {showDependencyModal && (
        <DependencyModal
          field={field}
          allFields={allFields}
          onClose={() => setShowDependencyModal(false)}
          onSave={handleUpdateDependencies}
        />
      )}

      {/* 约束编辑弹窗 */}
      {showConstraintsModal && (
        <ConstraintsModal
          field={field}
          onClose={() => setShowConstraintsModal(false)}
          onSave={handleUpdateConstraints}
        />
      )}
    </div>
  );
}

interface DependencyModalProps {
  field: Field;
  allFields: Field[];
  onClose: () => void;
  onSave: (dependsOn: string[]) => void;
}

function DependencyModal({ field, allFields, onClose, onSave }: DependencyModalProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>(
    field.dependencies?.depends_on || []
  );

  // 阶段显示名称映射（后端使用 intent, research 等）
  const phaseNameMap: Record<string, string> = {
    intent: "意图分析",
    research: "消费者调研",
    design_inner: "内涵设计",
    produce_inner: "内涵生产",
    design_outer: "外显设计",
    produce_outer: "外显生产",
    simulate: "模拟评估",
    evaluate: "总结优化",
  };

  // 可选的依赖字段（排除自己）
  const availableFields = allFields.filter((f) => f.id !== field.id);

  // 按阶段分组（全局字段在前）
  const globalPhases = ["intent", "research"];
  const globalFields = availableFields.filter((f) => globalPhases.includes(f.phase));
  const currentPhaseFields = availableFields.filter((f) => f.phase === field.phase);
  const otherFields = availableFields.filter(
    (f) => !globalPhases.includes(f.phase) && f.phase !== field.phase
  );

  const toggleField = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const renderFieldGroup = (fields: Field[], title: string, isGlobal: boolean = false) => {
    if (fields.length === 0) return null;
    return (
      <div>
        <div className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-2">
          <span>{isGlobal ? "🌐" : "📄"}</span>
          <span>{title}</span>
        </div>
        <div className="space-y-2">
          {fields.map((f) => (
            <label
              key={f.id}
              className={`flex items-center gap-3 p-2 rounded-lg hover:bg-surface-3 cursor-pointer ${
                isGlobal ? "border border-surface-3" : ""
              }`}
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(f.id)}
                onChange={() => toggleField(f.id)}
                className="rounded accent-brand-500"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    isGlobal ? "bg-brand-600/30 text-brand-300" : "bg-surface-3 text-zinc-500"
                  }`}>
                    {phaseNameMap[f.phase] || f.phase}
                  </span>
                  <span className="text-sm text-zinc-200">{f.name}</span>
                </div>
              </div>
              <span
                className={`w-2 h-2 rounded-full ${
                  f.status === "completed" ? "bg-green-500" : "bg-zinc-600"
                }`}
              />
            </label>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">设置依赖关系</h3>
          <p className="text-xs text-zinc-500 mt-1">
            选择生成"{field.name}"前需要先完成的字段
          </p>
        </div>

        <div className="p-4 max-h-[50vh] overflow-y-auto space-y-4">
          {/* 全局字段（意图分析、消费者调研） */}
          {renderFieldGroup(globalFields, "全局字段（可引用项目上游阶段）", true)}
          
          {/* 当前阶段字段 */}
          {renderFieldGroup(currentPhaseFields, `当前阶段（${phaseNameMap[field.phase] || field.phase}）`)}
          
          {/* 其他阶段字段 */}
          {renderFieldGroup(otherFields, "其他阶段")}
          
          {availableFields.length === 0 && (
            <p className="text-zinc-500 text-center py-4">暂无可选的依赖字段</p>
          )}
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
          >
            取消
          </button>
          <button
            onClick={() => onSave(selectedIds)}
            className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}

// ============== 约束编辑弹窗 ==============
interface ConstraintsModalProps {
  field: Field;
  onClose: () => void;
  onSave: (config: {
    ai_prompt?: string | null;
    max_length?: number | null;
    output_format?: string;
    structure?: string | null;
    example?: string | null;
  }) => void;
}

function ConstraintsModal({ field, onClose, onSave }: ConstraintsModalProps) {
  // 核心：AI 生成提示词
  const [aiPrompt, setAiPrompt] = useState(
    field.ai_prompt && field.ai_prompt !== "请在这里编写生成提示词..." 
      ? field.ai_prompt 
      : ""
  );
  const [maxLength, setMaxLength] = useState<string>(
    field.constraints?.max_length?.toString() || ""
  );
  const [outputFormat, setOutputFormat] = useState(
    field.constraints?.output_format || "markdown"
  );
  const [structure, setStructure] = useState(field.constraints?.structure || "");
  const [example, setExample] = useState(field.constraints?.example || "");

  const handleSave = () => {
    onSave({
      ai_prompt: aiPrompt || null,
      max_length: maxLength ? parseInt(maxLength, 10) : null,
      output_format: outputFormat,
      structure: structure || null,
      example: example || null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3">
          <h3 className="font-medium text-zinc-200">字段生成配置</h3>
          <p className="text-xs text-zinc-500 mt-1">
            设置「{field.name}」的生成提示词和约束
          </p>
        </div>

        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* ⭐ 核心：AI 生成提示词 */}
          <div className="bg-brand-600/10 border border-brand-500/30 rounded-lg p-3">
            <label className="block text-sm text-brand-400 mb-1.5 font-medium">
              ✨ 生成提示词（最重要！）
            </label>
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="例如：写一段开场白，用轻松幽默的语气介绍本文的主题"
              rows={4}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
            <p className="text-xs text-zinc-500 mt-1.5">
              告诉 AI 这个字段应该生成什么内容。越具体越好！
            </p>
          </div>

          {/* 最大字数 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              📏 最大字数
            </label>
            <input
              type="number"
              value={maxLength}
              onChange={(e) => setMaxLength(e.target.value)}
              placeholder="不限制"
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <p className="text-xs text-zinc-600 mt-1">
              留空表示不限制长度
            </p>
          </div>

          {/* 输出格式 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              📋 输出格式
            </label>
            <select
              value={outputFormat}
              onChange={(e) => setOutputFormat(e.target.value)}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="markdown">Markdown（富文本）</option>
              <option value="plain_text">纯文本</option>
              <option value="json">JSON 结构化</option>
              <option value="list">列表（每行一项）</option>
            </select>
          </div>

          {/* 结构模板 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              🏗️ 结构模板（可选）
            </label>
            <textarea
              value={structure}
              onChange={(e) => setStructure(e.target.value)}
              placeholder="例如：标题 + 正文 + 总结&#10;或：问题 → 原因分析 → 解决方案"
              rows={2}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
          </div>

          {/* 示例输出 */}
          <div>
            <label className="block text-sm text-zinc-400 mb-1.5">
              💡 示例输出（可选）
            </label>
            <textarea
              value={example}
              onChange={(e) => setExample(e.target.value)}
              placeholder="提供一个期望输出的示例，帮助 AI 理解格式"
              rows={3}
              className="w-full px-3 py-2 bg-surface-1 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-none"
            />
          </div>
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex justify-between">
          <button
            onClick={() => {
              setAiPrompt("");
              setMaxLength("");
              setOutputFormat("markdown");
              setStructure("");
              setExample("");
            }}
            className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            重置为默认
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors"
            >
              保存
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function getPhaseDescription(phase: string): string {
  const descriptions: Record<string, string> = {
    intent: "澄清内容生产的核心意图和目标",
    research: "调研目标用户，了解痛点和需求",
    design_inner: "设计内容生产方案和大纲",
    produce_inner: "生产核心内容",
    design_outer: "设计外延传播方案",
    produce_outer: "为各渠道生产营销内容",
    simulate: "模拟用户体验，收集反馈",
    evaluate: "全面评估内容质量",
  };
  return descriptions[phase] || "";
}
