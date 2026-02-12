// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板，支持字段依赖选择和生成
// 主要组件: ContentPanel, FieldCard
// 新增: 依赖选择弹窗、生成按钮、依赖状态显示、模拟阶段特殊面板

"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PHASE_NAMES, PROJECT_PHASES, sendNotification, requestNotificationPermission } from "@/lib/utils";
import { fieldAPI, agentAPI, blockAPI } from "@/lib/api";
import type { Field, ContentBlock } from "@/lib/api";
import { VersionHistoryButton } from "./version-history";
import { ContentBlockEditor } from "./content-block-editor";
import { ContentBlockCard } from "./content-block-card";
import { ChannelSelector } from "./channel-selector";
import { ResearchPanel } from "./research-panel";
import { EvalPhasePanel } from "./eval-phase-panel";
import { ProposalSelector } from "./proposal-selector";
import { FileText, Folder, Settings, ChevronRight } from "lucide-react";

interface ContentPanelProps {
  projectId: string | null;
  currentPhase: string;
  phaseStatus?: Record<string, string>;  // 各组状态
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
  const [showFieldTemplateModal, setShowFieldTemplateModal] = useState(false);
  const [fieldTemplates, setFieldTemplates] = useState<any[]>([]);
  const autoGenRef = useRef(false); // ref 守卫，防止 stale closure 导致重复启动
  
  const phaseFields = fields.filter((f) => f.phase === currentPhase);
  const completedFieldIds = useMemo(() => new Set(fields.filter(f => f.status === "completed").map(f => f.id)), [fields]);

  // 加载内容块模板
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
        name: `新内容块 ${phaseFields.length + 1}`,
        field_type: "richtext",
        content: "",
        status: "pending",
        ai_prompt: "",  // 空字符串，在约束弹窗中设置
        dependencies: { depends_on: [], dependency_type: "all" },
        need_review: true,
      });
      onFieldsChange?.();
    } catch (err) {
      console.error("添加内容块失败:", err);
      alert("添加内容块失败: " + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  // 从模板添加内容块
  const handleAddFromTemplate = async (template: any) => {
    if (!projectId) return;
    try {
      const templateFields = template.fields || [];
      
      // 获取现有内容块名以处理重复
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
      
      // 第一轮：创建所有内容块，记录 name -> id 映射
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
      
      // 第二轮：更新依赖关系（将模板中的内容块名转换为实际的内容块 ID）
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

  // 自动触发生成：检查是否有内容块可以自动生成
  // 使用 ref 守卫防止 stale closure 导致并发启动
  const checkAndAutoGenerate = useCallback(async () => {
    if (autoGenRef.current) return; // 已有自动生成在进行中

    // 找到可以自动生成的内容块：pending、need_review=false、依赖已满足
    const candidate = phaseFields.find(field => {
      if (field.status !== "pending") return false;
      if (field.need_review !== false) return false;
      const dependsOn = field.dependencies?.depends_on || [];
      if (dependsOn.length === 0) return true;
      return dependsOn.every(depId => completedFieldIds.has(depId));
    });

    if (!candidate) return;

    console.log(`[AutoGen] 自动触发生成: ${candidate.name}`);
    autoGenRef.current = true;

    try {
      // 调用流式生成 API（后端会设 status="generating"）
      const response = await fetch(`http://localhost:8000/api/fields/${candidate.id}/generate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pre_answers: candidate.pre_answers || {} }),
      });

      // 立刻刷新一次，让 FieldCard 看到 status="generating"
      onFieldsChange?.();

      // 读完整个 stream
      const reader = response.body?.getReader();
      if (reader) {
        while (true) {
          const { done } = await reader.read();
          if (done) break;
        }
      }

      // 生成完成，刷新内容块列表
      onFieldsChange?.();
      sendNotification("自动生成完成", `「${candidate.name}」已自动生成完毕`);
    } catch (err) {
      console.error("[AutoGen] 自动生成失败:", err);
    } finally {
      autoGenRef.current = false;
    }
  }, [phaseFields, completedFieldIds, onFieldsChange]);

  // 当内容块列表变化时，延迟检查是否有内容块可以自动生成（防止黑屏 / 无限循环）
  useEffect(() => {
    if (currentPhase !== "produce_inner" || phaseFields.length === 0) return;
    const timer = setTimeout(() => checkAndAutoGenerate(), 500);
    return () => clearTimeout(timer);
  }, [fields, currentPhase, checkAndAutoGenerate]);
  
  // 判断当前组是否可以进入下一组
  const phaseHasContent = phaseFields.length > 0 && phaseFields.some(f => f.status === "completed");
  const currentPhaseIndex = PROJECT_PHASES.indexOf(currentPhase);
  const isLastPhase = currentPhaseIndex === PROJECT_PHASES.length - 1;
  const nextPhase = isLastPhase ? null : PROJECT_PHASES[currentPhaseIndex + 1];
  
  // 内涵设计阶段不再使用特殊的方案格式检测
  // 改为与其他组一致的内容块列表视图

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
  
  // 确认进入下一组
  const handleAdvancePhase = async () => {
    if (!projectId || !nextPhase) return;
    
    setIsAdvancing(true);
    try {
      await agentAPI.advance(projectId);
      onPhaseAdvance?.();
    } catch (err) {
      console.error("进入下一组失败:", err);
      alert("进入下一组失败: " + (err instanceof Error ? err.message : "未知错误"));
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
    
    // ===== 意图分析阶段特殊处理 =====
    if (selectedBlock.special_handler === "intent" || selectedPhase === "intent") {
      const intentContent = selectedBlock.content?.trim();
      if (intentContent) {
        // 有内容时：显示意图分析结果，使用 ContentBlockEditor
        return (
          <ContentBlockEditor
            block={selectedBlock}
            projectId={projectId}
            allBlocks={allBlocks}
            isVirtual={isVirtualBlock}
            onUpdate={onFieldsChange}
          />
        );
      } else {
        // 没有内容时显示引导占位
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
    }
    
    // ===== 消费者调研阶段特殊处理 =====
    if (selectedBlock.special_handler === "research" || selectedPhase === "research") {
      const researchContent = selectedBlock.content?.trim();
      if (researchContent) {
        // 有内容：尝试用 ResearchPanel 展示
        try {
          const parsed = JSON.parse(researchContent);
          // 只要是有效 JSON 且包含调研相关字段，就用 ResearchPanel
          if (parsed && typeof parsed === "object" && (parsed.summary || parsed.consumer_profile || parsed.personas || parsed.pain_points)) {
            // 确保 ResearchPanel 需要的内容块存在（补全缺失字段）
            const normalized = {
              summary: parsed.summary || "",
              consumer_profile: parsed.consumer_profile || {},
              pain_points: parsed.pain_points || parsed.main_pain_points || [],
              value_propositions: parsed.value_propositions || parsed.value_proposition || [],
              personas: parsed.personas || [],
              sources: parsed.sources || [],
            };
            return (
              <ResearchPanel
                projectId={projectId}
                fieldId={selectedBlock.id}
                content={JSON.stringify(normalized, null, 2)}
                onUpdate={onFieldsChange}
                onAdvance={handleAdvancePhase}
                isBlock={!isVirtualBlock}
              />
            );
          }
        } catch {
          // JSON 解析失败，用 ContentBlockEditor
        }
        // JSON 解析失败或格式不匹配 — 用 ContentBlockEditor 显示原始内容
        return (
          <ContentBlockEditor
            block={selectedBlock}
            projectId={projectId}
            allBlocks={allBlocks}
            isVirtual={isVirtualBlock}
            onUpdate={onFieldsChange}
          />
        );
      } else {
        // 没有内容时显示引导占位
        return (
          <div className="h-full flex flex-col items-center justify-center p-6 text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h2 className="text-xl font-bold text-zinc-200 mb-2">消费者调研</h2>
            <p className="text-zinc-400 max-w-md">
              消费者调研由 AI Agent 通过 DeepResearch 工具完成。请在右侧对话框中输入"开始调研"来启动。
            </p>
            <p className="text-zinc-500 text-sm mt-4">
              Agent 会基于你的意图分析结果，搜索相关信息并生成调研报告。
            </p>
          </div>
        );
      }
    }
    
    // 如果是真正的 ContentBlock 阶段/分组（灵活架构），显示其所有子节点
    if (!isVirtualBlock && selectedBlock.children && selectedBlock.children.length > 0) {
      // 统计不同类型的子节点
      const phaseCount = selectedBlock.children.filter(c => c.block_type === "phase").length;
      const groupCount = selectedBlock.children.filter(c => c.block_type === "group").length;
      const fieldCount = selectedBlock.children.filter(c => c.block_type === "field").length;
      const otherCount = selectedBlock.children.length - phaseCount - groupCount - fieldCount;
      
      // 生成描述文字
      const parts = [];
      if (phaseCount > 0) parts.push(`${phaseCount} 个子组`);
      if (groupCount > 0) parts.push(`${groupCount} 个分组`);
      if (fieldCount > 0) parts.push(`${fieldCount} 个内容块`);
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
                {selectedBlock.block_type === "phase" ? "组" : "分组"}
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
    
    // 如果是没有子块的组（空阶段或虚拟阶段）
    if (!isVirtualBlock && (!selectedBlock.children || selectedBlock.children.length === 0)) {
      return (
        <div className="h-full flex flex-col items-center justify-center text-zinc-500">
          <p className="text-lg mb-2">{selectedBlock.name}</p>
          <p className="text-sm">该组暂无内容块，请在左侧添加</p>
        </div>
      );
    }
    
    if (selectedPhase) {
      // 获取该组的所有内容块（虚拟块模式）
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
      
      // 内涵设计阶段 - 使用 ProposalSelector
      if (selectedPhase === "design_inner") {
        const designInnerField = phaseFields.find(f => f.name === "内涵设计方案");
        if (designInnerField) {
          try {
            const proposalsData = JSON.parse(designInnerField.content || "{}");
            if (proposalsData.proposals && Array.isArray(proposalsData.proposals) && proposalsData.proposals.length > 0) {
              return (
                <div className="h-full flex flex-col">
                  <div className="p-4 border-b border-surface-3">
                    <h1 className="text-xl font-bold text-zinc-100">内涵设计</h1>
                    <p className="text-zinc-500 text-sm mt-1">
                      选择一个方案，确认后将进入内涵生产阶段
                    </p>
                  </div>
                  <div className="flex-1 overflow-y-auto p-4">
                    <ProposalSelector
                      projectId={projectId}
                      fieldId={designInnerField.id}
                      content={designInnerField.content}
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
            // JSON 解析失败，使用默认 FieldCard
          }
        }
      }
      
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
      
      // 外延生产阶段 - 显示渠道内容块列表（使用 FieldCard 提供完整编辑功能）
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

              {/* 确认进入下一组按钮 */}
              {phaseHasContent && nextPhase && (() => {
                const isPhaseCompleted = phaseStatus[currentPhase] === "completed";
                return (
                  <div className="mt-8 pt-6 border-t border-surface-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-zinc-400 text-sm">
                          {isPhaseCompleted ? "✅ 当前组已确认" : "当前组内容已完成"}
                        </p>
                        <p className="text-zinc-500 text-xs mt-1">
                          下一组：{PHASE_NAMES[nextPhase] || nextPhase}
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
                            <span>✅ 确认，进入下一组</span>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        );
      }
      
      // 评估阶段 - 使用 EvalTaskConfig + EvalReportPanel
      if (selectedPhase === "evaluate") {
        return (
          <EvalPhasePanel
            projectId={projectId}
            fields={fields}
            onFieldsChange={onFieldsChange}
          />
        );
      }
      
      // 内涵生产阶段 - 显示内容块列表（使用 FieldCard 提供完整编辑功能）
      if (selectedPhase === "produce_inner" && phaseFields.length > 0) {
        return (
          <div className="h-full flex flex-col">
            <div className="p-4 border-b border-surface-3">
              <h1 className="text-xl font-bold text-zinc-100">
                {PHASE_NAMES[selectedPhase] || selectedPhase}
              </h1>
              <p className="text-zinc-500 text-sm mt-1">
                共 {phaseFields.length} 个内容块 - 可展开编辑所有设置
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

              {/* 确认进入下一组按钮 */}
              {phaseHasContent && nextPhase && (() => {
                const isPhaseCompleted = phaseStatus[currentPhase] === "completed";
                return (
                  <div className="mt-8 pt-6 border-t border-surface-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-zinc-400 text-sm">
                          {isPhaseCompleted ? "✅ 当前组已确认" : "当前组内容已完成"}
                        </p>
                        <p className="text-zinc-500 text-xs mt-1">
                          下一组：{PHASE_NAMES[nextPhase] || nextPhase}
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
                            <span>✅ 确认，进入下一组</span>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        );
      }
      
      // 其他组 - 显示阶段概览（使用 FieldCard 提供完整编辑功能）
      return (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="p-6 pb-0">
            <h1 className="text-xl font-bold text-zinc-100 mb-2">
              {PHASE_NAMES[selectedPhase] || selectedPhase}
            </h1>
            <p className="text-zinc-500 mb-4">
              共有 {phaseFields.length} 个内容块 - 点击字段可编辑
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
              <p className="text-zinc-500">该组暂无内容块</p>
            )}
          </div>
        </div>
      );
    }
  }
  
  // 处理内容块块点击
  if (selectedBlock && selectedBlock.block_type === "field") {
    // ===== 检查 special_handler：显示对应的特殊界面 =====
    const handler = selectedBlock.special_handler as string | null | undefined;
    
    // 消费者调研字段 - 检查是否有结构化内容
    if (handler === "consumer_research" || handler === "research") {
      try {
        const parsed = JSON.parse(selectedBlock.content || "{}");
        if (parsed && typeof parsed === "object" && (parsed.summary || parsed.consumer_profile || parsed.personas || parsed.pain_points)) {
          // 补全缺失字段，确保 ResearchPanel 可以正常渲染
          const normalized = {
            summary: parsed.summary || "",
            consumer_profile: parsed.consumer_profile || {},
            pain_points: parsed.pain_points || parsed.main_pain_points || [],
            value_propositions: parsed.value_propositions || parsed.value_proposition || [],
            personas: parsed.personas || [],
            sources: parsed.sources || [],
          };
          return (
            <ResearchPanel
              projectId={projectId}
              fieldId={selectedBlock.id}
              content={JSON.stringify(normalized, null, 2)}
              onUpdate={onFieldsChange}
              onAdvance={handleAdvancePhase}
              isBlock={true}
            />
          );
        }
      } catch {
        // JSON 解析失败，继续使用默认编辑器
      }
    }
    
    // 意图分析字段 - 由 Agent 处理
    if (handler === "intent_analysis" || handler === "intent") {
      const hasContent = selectedBlock.content && selectedBlock.content.trim() !== "";
      if (!hasContent) {
        // 没有内容时显示引导占位
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
      // 有内容时：使用通用 ContentBlockEditor 展示（可查看和编辑）
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
      
      // ===== 特殊处理：内涵设计方案（JSON proposals）=====
      if (matchingField.phase === "design_inner" && matchingField.name === "内涵设计方案") {
        try {
          const proposalsData = JSON.parse(matchingField.content || "{}");
          if (proposalsData.proposals && Array.isArray(proposalsData.proposals) && proposalsData.proposals.length > 0) {
            return (
              <div className="h-full flex flex-col">
                <div className="p-4 border-b border-surface-3">
                  <h1 className="text-xl font-bold text-zinc-100">内涵设计</h1>
                  <p className="text-zinc-500 text-sm mt-1">
                    选择一个方案，确认后将进入内涵生产阶段
                  </p>
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                  <ProposalSelector
                    projectId={projectId}
                    fieldId={matchingField.id}
                    content={matchingField.content}
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
      
      // ===== 特殊处理：外延设计方案（JSON channels）=====
      if (matchingField.phase === "design_outer" && matchingField.name === "外延设计方案") {
        try {
          const channelsData = JSON.parse(matchingField.content || "{}");
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
                    fieldId={matchingField.id}
                    content={matchingField.content}
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
          请在左侧树形结构中选择一个组或字段来查看和编辑内容。
        </p>
        <p className="text-zinc-500 text-sm mt-4">
          传统视图已锁定，所有操作通过树形结构进行。
        </p>
      </div>
    );
  }

  // 评估阶段使用专用面板
  if (currentPhase === "evaluate") {
    return (
      <EvalPhasePanel
        projectId={projectId}
        fields={fields}
        onFieldsChange={onFieldsChange}
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

  // 内涵设计阶段：使用 ProposalSelector
  if (currentPhase === "design_inner") {
    const designInnerField = phaseFields.find(f => f.name === "内涵设计方案");
    if (designInnerField) {
      try {
        const proposalsData = JSON.parse(designInnerField.content || "{}");
        if (proposalsData.proposals && Array.isArray(proposalsData.proposals) && proposalsData.proposals.length > 0) {
          return (
            <div className="h-full flex flex-col">
              <div className="p-4 border-b border-surface-3">
                <h1 className="text-xl font-bold text-zinc-100">内涵设计</h1>
                <p className="text-zinc-500 text-sm mt-1">
                  选择一个方案，确认后将进入内涵生产阶段
                </p>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                <ProposalSelector
                  projectId={projectId}
                  fieldId={designInnerField.id}
                  content={designInnerField.content}
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
        // JSON 解析失败，使用默认 FieldCard
      }
    }
  }

  // 外延设计阶段：使用 ChannelSelector
  if (currentPhase === "design_outer") {
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

  // 构建字段ID到内容块名称的映射（用于显示依赖）
  const fieldNameMap = Object.fromEntries(fields.map(f => [f.id, f.name]));
  
  // 滚动到指定字段
  const scrollToField = (fieldId: string) => {
    const element = document.getElementById(`field-${fieldId}`);
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="h-full flex">
      {/* 内涵生产阶段：左侧内容块目录 */}
      {currentPhase === "produce_inner" && phaseFields.length > 0 && (
        <div className="w-56 shrink-0 border-r border-surface-3 p-4 overflow-auto">
          <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3">
            内容块目录
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
          
          {/* 添加内容块按钮 */}
          <div className="mt-4 space-y-2">
            <button
              onClick={() => handleAddEmptyField()}
              className="w-full py-2 text-xs bg-brand-600 hover:bg-brand-700 text-white rounded-lg transition-colors"
            >
              + 添加内容块
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

        {/* 内容块列表 */}
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
            <p>当前组暂无内容</p>
            <p className="text-sm mt-2">
              在右侧与 AI Agent 对话开始生产内容
            </p>
          </div>
        )}
      
      {/* 确认进入下一组按钮 */}
      {phaseHasContent && nextPhase && (() => {
        const isPhaseCompleted = phaseStatus[currentPhase] === "completed";
        
        return (
          <div className="mt-8 pt-6 border-t border-surface-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-zinc-400 text-sm">
                  {isPhaseCompleted ? "✅ 当前组已确认" : "当前组内容已完成"}
                </p>
                <p className="text-zinc-500 text-xs mt-1">
                  下一组：{PHASE_NAMES[nextPhase] || nextPhase}
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
                    <span>✅ 确认，进入下一组</span>
                  )}
                </button>
              )}
            </div>
          </div>
        );
      })()}
      </div>

      {/* 内容块模板选择弹窗 */}
      {showFieldTemplateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-surface-2 rounded-xl border border-surface-3 w-full max-w-lg max-h-[80vh] overflow-hidden">
            <div className="px-4 py-3 border-b border-surface-3">
              <h3 className="font-medium text-zinc-200">从模板添加内容块</h3>
              <p className="text-xs text-zinc-500 mt-1">
                选择一个模板添加到当前组
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
                      📦 {template.fields?.length || 0} 个内容块
                    </div>
                  </button>
                ))
              ) : (
                <p className="text-zinc-500 text-center py-8">
                  暂无内容块模板，请在后台设置中添加
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
  const abortControllerRef = useRef<AbortController | null>(null);
  // 预提问相关状态
  const [preAnswers, setPreAnswers] = useState<Record<string, string>>(
    field.pre_answers || {}
  );
  const [isSavingPreAnswers, setIsSavingPreAnswers] = useState(false);
  const [preAnswersSaved, setPreAnswersSaved] = useState(false);
  const hasPreQuestions = field.pre_questions && field.pre_questions.length > 0;
  // ===== 关键修复：预提问默认展开（如果有未回答的问题）=====
  const hasUnansweredQuestions = hasPreQuestions && field.pre_questions!.some(
    q => !preAnswers[q] || !preAnswers[q].trim()
  );
  const [showPreQuestions, setShowPreQuestions] = useState(hasUnansweredQuestions);
  
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

  // 获取依赖内容块信息
  const dependsOnIds = field.dependencies?.depends_on || [];
  const dependencyFields = allFields.filter((f) => dependsOnIds.includes(f.id));
  const unmetDependencies = dependencyFields.filter((f) => f.status !== "completed");
  const canGenerate = unmetDependencies.length === 0;

  const handleSave = () => {
    onUpdate?.(content);
    setIsEditing(false);
  };

  const handleGenerate = async () => {
    // 首次点击生成时请求通知权限（需在用户交互中）
    requestNotificationPermission();
    
    if (!canGenerate) {
      alert(`请先完成依赖内容块: ${unmetDependencies.map(f => f.name).join(", ")}`);
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
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      // 使用流式生成，传递预回答
      const response = await fetch(`http://localhost:8000/api/fields/${field.id}/generate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pre_answers: preAnswers }),
        signal: abortController.signal,
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
                  sendNotification("内容生成完成", `「${field.name}」已生成完毕，点击查看`);
                }
              } catch {}
            }
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        console.log("[FieldCard] 用户停止了生成");
        onFieldsChange?.();
      } else {
        console.error("生成失败:", err);
        alert("生成失败: " + (err instanceof Error ? err.message : "未知错误"));
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;
    }
  };

  // 停止生成
  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
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
    if (!confirm(`确定要删除内容块「${field.name}」吗？此操作不可撤销。`)) return;
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
              {hasPreQuestions && hasUnansweredQuestions && (
                <span className="text-xs px-2 py-0.5 rounded bg-amber-600/20 text-amber-400">
                  📝 有未回答的提问
                </span>
              )}
            </div>
          </div>
          
          <div className="flex gap-2">
            {/* 生成中：显示停止按钮 */}
            {isGenerating && (
              <button
                onClick={handleStopGeneration}
                className="flex items-center gap-1.5 px-3 py-1 text-sm bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                title="停止生成"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor"><rect x="3" y="3" width="10" height="10" rx="1" /></svg>
                停止生成
              </button>
            )}
            
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

            {/* 版本历史按钮（有内容时显示） */}
            {field.content && !isGenerating && (
              <VersionHistoryButton
                entityId={field.id}
                entityName={field.name}
                onRollback={() => onFieldsChange?.()}
              />
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
              title="删除此内容块"
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
          
          {/* 自动生成开关 */}
          <label className="flex items-center gap-1.5 cursor-pointer select-none" title={field.need_review ? "当前需手动点击生成" : "依赖完成后自动生成"}>
            <span className="text-zinc-500">⚡</span>
            <span className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${field.need_review === false ? "bg-brand-600" : "bg-zinc-600"}`}>
              <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${field.need_review === false ? "translate-x-3.5" : "translate-x-0.5"}`} />
            </span>
            <span className={`text-xs ${field.need_review === false ? "text-brand-400" : "text-zinc-500"}`}>
              {field.need_review === false ? "自动" : "手动"}
            </span>
            <input
              type="checkbox"
              checked={field.need_review === false}
              onChange={async (e) => {
                try {
                  await fieldAPI.update(field.id, { need_review: !e.target.checked });
                  onFieldsChange?.();
                } catch (err) {
                  alert("更新失败: " + (err instanceof Error ? err.message : "未知错误"));
                }
              }}
              className="sr-only"
            />
          </label>

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
            <span>此内容块有 {field.pre_questions.length} 个预设问题需要回答</span>
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
        ) : field.status === "generating" ? (
          <div className="bg-surface-1 border border-surface-3 rounded-lg p-3">
            <div className="text-xs text-brand-400 mb-2 animate-pulse">⏳ 自动生成中...</div>
            <div className="text-sm text-zinc-500">内容正在后台生成，完成后将自动显示</div>
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
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({ children, ...props }) => (
                      <div className="table-wrapper">
                        <table {...props}>{children}</table>
                      </div>
                    ),
                  }}
                >{field.content}</ReactMarkdown>
              ) : hasPreQuestions && !showPreQuestions ? (
                <p className="text-zinc-500 italic">
                  此内容块有预设问题需要回答，点击"生成"按钮开始
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
    evaluate: "评估",
  };

  // 可选的依赖内容块（排除自己）
  const availableFields = allFields.filter((f) => f.id !== field.id);

  // 按阶段分组（全局内容块在前）
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
            选择生成"{field.name}"前需要先完成的内容块
          </p>
        </div>

        <div className="p-4 max-h-[50vh] overflow-y-auto space-y-4">
          {/* 全局内容块（意图分析、消费者调研） */}
          {renderFieldGroup(globalFields, "全局内容块（可引用项目上游组）", true)}
          
          {/* 当前组字段 */}
          {renderFieldGroup(currentPhaseFields, `当前组（${phaseNameMap[field.phase] || field.phase}）`)}
          
          {/* 其他组字段 */}
          {renderFieldGroup(otherFields, "其他组")}
          
          {availableFields.length === 0 && (
            <p className="text-zinc-500 text-center py-4">暂无可选的依赖内容块</p>
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
  const [aiPromptPurpose, setAiPromptPurpose] = useState("");
  const [generatingPrompt, setGeneratingPrompt] = useState(false);

  const handleGeneratePrompt = async () => {
    if (!aiPromptPurpose.trim()) return;
    setGeneratingPrompt(true);
    try {
      const result = await blockAPI.generatePrompt({
        purpose: aiPromptPurpose,
        field_name: field.name,
        project_id: field.project_id || "",
      });
      setAiPrompt(result.prompt);
      setAiPromptPurpose("");  // 清空输入
    } catch (e: any) {
      alert("生成提示词失败: " + (e.message || "未知错误"));
    } finally {
      setGeneratingPrompt(false);
    }
  };

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
          <h3 className="font-medium text-zinc-200">内容块生成配置</h3>
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
              告诉 AI 这个内容块应该生成什么内容。越具体越好！
            </p>

            {/* 🤖 用 AI 生成提示词 */}
            <div className="mt-3 p-2.5 bg-surface-1/50 border border-surface-3 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs text-zinc-400">🤖 用 AI 生成提示词</span>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={aiPromptPurpose}
                  onChange={(e) => setAiPromptPurpose(e.target.value)}
                  placeholder="简述内容块目的，如：介绍产品核心卖点"
                  className="flex-1 px-2.5 py-1.5 bg-surface-1 border border-surface-3 rounded text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && aiPromptPurpose.trim() && !generatingPrompt) {
                      handleGeneratePrompt();
                    }
                  }}
                />
                <button
                  onClick={handleGeneratePrompt}
                  disabled={!aiPromptPurpose.trim() || generatingPrompt}
                  className="px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-sm rounded disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1 whitespace-nowrap"
                >
                  {generatingPrompt ? (
                    <>
                      <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                      生成中...
                    </>
                  ) : "AI 生成"}
                </button>
              </div>
            </div>
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
    evaluate: "配置评估任务，多维度评估内容",
  };
  return descriptions[phase] || "";
}
