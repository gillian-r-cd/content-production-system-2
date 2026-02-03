// frontend/components/proposal-selector.tsx
// 功能: 内涵设计方案选择组件
// 主要功能: 展示3个方案、方案选择、字段编辑、确认进入下一阶段

"use client";

import { useState, useMemo } from "react";
import { fieldAPI, agentAPI } from "@/lib/api";

// 方案中的字段定义
interface ProposalField {
  id: string;
  name: string;
  field_type: string;
  ai_prompt: string;
  depends_on: string[];
  order: number;
  need_review: boolean;
}

// 方案定义
interface Proposal {
  id: string;
  name: string;
  description: string;
  fields: ProposalField[];
}

// 方案数据结构
interface ProposalsData {
  proposals: Proposal[];
  selected_proposal?: string | null;
  error?: string;
}

interface ProposalSelectorProps {
  projectId: string;
  content: string;  // JSON格式的方案内容
  onConfirm: () => void;  // 确认后的回调
  onFieldsCreated?: () => void;  // 字段创建后的回调
}

export function ProposalSelector({
  projectId,
  content,
  onConfirm,
  onFieldsCreated,
}: ProposalSelectorProps) {
  // 解析方案数据
  const proposalsData = useMemo<ProposalsData>(() => {
    try {
      const data = JSON.parse(content);
      return data;
    } catch {
      return { proposals: [], error: "方案数据解析失败" };
    }
  }, [content]);

  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(
    proposalsData.selected_proposal || proposalsData.proposals?.[0]?.id || null
  );
  const [editedFields, setEditedFields] = useState<Record<string, ProposalField[]>>({});
  const [isConfirming, setIsConfirming] = useState(false);

  // 当前选中的方案
  const selectedProposal = useMemo(() => {
    return proposalsData.proposals?.find((p) => p.id === selectedProposalId) || null;
  }, [proposalsData.proposals, selectedProposalId]);

  // 获取当前方案的字段（可能被编辑过）
  const currentFields = useMemo(() => {
    if (!selectedProposalId) return [];
    return editedFields[selectedProposalId] || selectedProposal?.fields || [];
  }, [selectedProposalId, editedFields, selectedProposal]);

  // 切换字段的 need_review 状态
  const toggleNeedReview = (fieldId: string) => {
    if (!selectedProposalId) return;
    
    const fields = [...currentFields];
    const fieldIndex = fields.findIndex((f) => f.id === fieldId);
    if (fieldIndex !== -1) {
      fields[fieldIndex] = {
        ...fields[fieldIndex],
        need_review: !fields[fieldIndex].need_review,
      };
      setEditedFields((prev) => ({
        ...prev,
        [selectedProposalId]: fields,
      }));
    }
  };

  // 确认方案，创建实际的字段
  const handleConfirmProposal = async () => {
    if (!selectedProposal || !projectId) return;

    setIsConfirming(true);
    try {
      // 为选中方案的每个字段创建 ProjectField
      for (const field of currentFields) {
        await fieldAPI.create({
          project_id: projectId,
          name: field.name,
          phase: "produce_inner",  // 字段属于内涵生产阶段
          field_type: field.field_type || "richtext",
          content: "",  // 内容待生产
          status: "pending",
          ai_prompt: field.ai_prompt,
          dependencies: {
            depends_on: field.depends_on,
            dependency_type: "all",
          },
        });
      }

      onFieldsCreated?.();
      
      // 推进到下一阶段
      await agentAPI.advance(projectId);
      onConfirm();
    } catch (err) {
      console.error("确认方案失败:", err);
      alert("确认方案失败: " + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setIsConfirming(false);
    }
  };

  if (proposalsData.error) {
    return (
      <div className="p-6 text-center text-red-400">
        <p>{proposalsData.error}</p>
        <p className="text-sm mt-2 text-zinc-500">请在右侧对话框让Agent重新生成</p>
      </div>
    );
  }

  if (!proposalsData.proposals || proposalsData.proposals.length === 0) {
    return (
      <div className="p-6 text-center text-zinc-500">
        <p>暂无方案数据</p>
      </div>
    );
  }

  return (
    <div className="h-full flex">
      {/* 左侧：方案目录 */}
      <div className="w-64 border-r border-surface-3 p-4 flex flex-col">
        <h3 className="text-sm font-medium text-zinc-400 mb-4">选择方案</h3>
        <div className="space-y-2 flex-1">
          {proposalsData.proposals.map((proposal, index) => (
            <button
              key={proposal.id}
              onClick={() => setSelectedProposalId(proposal.id)}
              className={`w-full text-left p-3 rounded-lg transition-colors ${
                selectedProposalId === proposal.id
                  ? "bg-brand-600/20 border border-brand-500 text-brand-400"
                  : "bg-surface-2 border border-surface-3 text-zinc-300 hover:bg-surface-3"
              }`}
            >
              <div className="font-medium text-sm">方案 {index + 1}</div>
              <div className="text-xs mt-1 opacity-80 line-clamp-2">
                {proposal.name}
              </div>
            </button>
          ))}
        </div>
        
        {/* 确认按钮 */}
        <button
          onClick={handleConfirmProposal}
          disabled={!selectedProposalId || isConfirming}
          className="mt-4 w-full py-3 bg-brand-600 hover:bg-brand-700 disabled:bg-zinc-700 disabled:text-zinc-500 rounded-lg font-medium transition-colors"
        >
          {isConfirming ? "确认中..." : "✅ 确认并进入生产"}
        </button>
      </div>

      {/* 右侧：方案详情 */}
      <div className="flex-1 p-6 overflow-auto">
        {selectedProposal ? (
          <div>
            <h2 className="text-xl font-bold text-zinc-100 mb-2">
              {selectedProposal.name}
            </h2>
            <p className="text-zinc-400 mb-6">
              {selectedProposal.description}
            </p>

            {/* 字段列表 */}
            <div className="mb-4">
              <h3 className="text-sm font-medium text-zinc-400 mb-3">
                内容字段 ({currentFields.length}个)
              </h3>
              <p className="text-xs text-zinc-500 mb-4">
                点击 checkpoint 可切换是否需要人工确认
              </p>
            </div>

            <div className="space-y-3">
              {currentFields.map((field, index) => (
                <div
                  key={field.id}
                  className="bg-surface-2 border border-surface-3 rounded-lg p-4"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs bg-surface-3 px-2 py-0.5 rounded text-zinc-500">
                          {index + 1}
                        </span>
                        <span className="font-medium text-zinc-200">
                          {field.name}
                        </span>
                      </div>
                      
                      {/* 依赖关系 */}
                      {field.depends_on && field.depends_on.length > 0 && (
                        <div className="mt-2 text-xs text-zinc-500">
                          依赖: {field.depends_on.map((depId) => {
                            const depField = currentFields.find((f) => f.id === depId);
                            return depField?.name || depId;
                          }).join(", ")}
                        </div>
                      )}
                      
                      {/* AI提示词预览 */}
                      <div className="mt-2 text-xs text-zinc-500 line-clamp-2">
                        {field.ai_prompt}
                      </div>
                    </div>

                    {/* Checkpoint 开关 */}
                    <button
                      onClick={() => toggleNeedReview(field.id)}
                      className={`ml-4 px-3 py-1 text-xs rounded-full transition-colors ${
                        field.need_review
                          ? "bg-amber-500/20 text-amber-400 border border-amber-500/50"
                          : "bg-surface-3 text-zinc-500 border border-surface-3"
                      }`}
                    >
                      {field.need_review ? "🔍 需确认" : "自动"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-zinc-500">
            请选择一个方案
          </div>
        )}
      </div>
    </div>
  );
}
