(globalThis.TURBOPACK || (globalThis.TURBOPACK = [])).push([typeof document === "object" ? document.currentScript : undefined,
"[project]/components/layout/workspace-layout.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "WorkspaceLayout",
    ()=>WorkspaceLayout
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
// frontend/components/layout/workspace-layout.tsx
// 功能: 工作台三栏布局
// 主要组件: WorkspaceLayout
"use client";
;
function WorkspaceLayout({ leftPanel, centerPanel, rightPanel }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "flex h-screen bg-surface-0",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("aside", {
                className: "w-64 flex-shrink-0 border-r border-surface-3 bg-surface-1 overflow-y-auto",
                children: leftPanel
            }, void 0, false, {
                fileName: "[project]/components/layout/workspace-layout.tsx",
                lineNumber: 23,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
                className: "flex-1 overflow-y-auto bg-surface-0",
                children: centerPanel
            }, void 0, false, {
                fileName: "[project]/components/layout/workspace-layout.tsx",
                lineNumber: 28,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("aside", {
                className: "w-96 flex-shrink-0 border-l border-surface-3 bg-surface-1 flex flex-col",
                children: rightPanel
            }, void 0, false, {
                fileName: "[project]/components/layout/workspace-layout.tsx",
                lineNumber: 33,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/layout/workspace-layout.tsx",
        lineNumber: 21,
        columnNumber: 5
    }, this);
}
_c = WorkspaceLayout;
var _c;
__turbopack_context__.k.register(_c, "WorkspaceLayout");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/lib/utils.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "PHASE_NAMES",
    ()=>PHASE_NAMES,
    "PHASE_STATUS",
    ()=>PHASE_STATUS,
    "cn",
    ()=>cn,
    "formatDate",
    ()=>formatDate
]);
// frontend/lib/utils.ts
// 功能: 通用工具函数
// 主要函数: cn, formatDate
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/clsx/dist/clsx.mjs [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/tailwind-merge/dist/bundle-mjs.mjs [app-client] (ecmascript)");
;
;
function cn(...inputs) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$tailwind$2d$merge$2f$dist$2f$bundle$2d$mjs$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__["twMerge"])((0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$clsx$2f$dist$2f$clsx$2e$mjs__$5b$app$2d$client$5d$__$28$ecmascript$29$__["clsx"])(inputs));
}
function formatDate(dateString) {
    if (!dateString) return "";
    const date = new Date(dateString);
    return date.toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit"
    });
}
const PHASE_NAMES = {
    intent: "意图分析",
    research: "消费者调研",
    design_inner: "内涵设计",
    produce_inner: "内涵生产",
    design_outer: "外延设计",
    produce_outer: "外延生产",
    simulate: "消费者模拟",
    evaluate: "评估"
};
const PHASE_STATUS = {
    pending: {
        label: "未开始",
        color: "text-zinc-500"
    },
    in_progress: {
        label: "进行中",
        color: "text-yellow-500"
    },
    completed: {
        label: "已完成",
        color: "text-green-500"
    }
};
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/components/progress-panel.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ProgressPanel",
    ()=>ProgressPanel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/utils.ts [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
// frontend/components/progress-panel.tsx
// 功能: 左栏项目进度面板，支持中间4阶段拖拽排序
// 主要组件: ProgressPanel
// 固定阶段: 意图分析、消费者调研在顶部；消费者模拟、评估在底部
// 可拖拽阶段: 内涵设计、内涵生产、外延设计、外延生产
"use client";
;
;
// 固定阶段定义
const FIXED_TOP_PHASES = [
    "intent",
    "research"
];
const DRAGGABLE_PHASES = [
    "design_inner",
    "produce_inner",
    "design_outer",
    "produce_outer"
];
const FIXED_BOTTOM_PHASES = [
    "simulate",
    "evaluate"
];
function ProgressPanel({ project, onPhaseClick, onPhaseReorder }) {
    _s();
    const allPhases = project?.phase_order || [];
    const phaseStatus = project?.phase_status || {};
    const currentPhase = project?.current_phase || "intent";
    // 分离固定和可拖拽阶段
    const topPhases = allPhases.filter((p)=>FIXED_TOP_PHASES.includes(p));
    const middlePhases = allPhases.filter((p)=>DRAGGABLE_PHASES.includes(p));
    const bottomPhases = allPhases.filter((p)=>FIXED_BOTTOM_PHASES.includes(p));
    // 拖拽状态
    const [draggedPhase, setDraggedPhase] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const [dragOverPhase, setDragOverPhase] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const dragCounter = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRef"])(0);
    const handleDragStart = (e, phase)=>{
        setDraggedPhase(phase);
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", phase);
    };
    const handleDragEnd = ()=>{
        setDraggedPhase(null);
        setDragOverPhase(null);
        dragCounter.current = 0;
    };
    const handleDragEnter = (e, phase)=>{
        e.preventDefault();
        dragCounter.current++;
        if (DRAGGABLE_PHASES.includes(phase)) {
            setDragOverPhase(phase);
        }
    };
    const handleDragLeave = ()=>{
        dragCounter.current--;
        if (dragCounter.current === 0) {
            setDragOverPhase(null);
        }
    };
    const handleDragOver = (e)=>{
        e.preventDefault();
    };
    const handleDrop = (e, targetPhase)=>{
        e.preventDefault();
        if (!draggedPhase || draggedPhase === targetPhase) {
            handleDragEnd();
            return;
        }
        // 重新排序中间阶段
        const newMiddle = [
            ...middlePhases
        ];
        const dragIdx = newMiddle.indexOf(draggedPhase);
        const dropIdx = newMiddle.indexOf(targetPhase);
        if (dragIdx !== -1 && dropIdx !== -1) {
            newMiddle.splice(dragIdx, 1);
            newMiddle.splice(dropIdx, 0, draggedPhase);
            // 重建完整顺序
            const newOrder = [
                ...topPhases,
                ...newMiddle,
                ...bottomPhases
            ];
            onPhaseReorder?.(newOrder);
        }
        handleDragEnd();
    };
    const renderPhaseItem = (phase, isDraggable)=>{
        const status = phaseStatus[phase] || "pending";
        const statusInfo = __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["PHASE_STATUS"][status] || __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["PHASE_STATUS"].pending;
        const isCurrent = phase === currentPhase;
        const isDragging = draggedPhase === phase;
        const isDragOver = dragOverPhase === phase;
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            draggable: isDraggable,
            onDragStart: isDraggable ? (e)=>handleDragStart(e, phase) : undefined,
            onDragEnd: isDraggable ? handleDragEnd : undefined,
            onDragEnter: isDraggable ? (e)=>handleDragEnter(e, phase) : undefined,
            onDragLeave: isDraggable ? handleDragLeave : undefined,
            onDragOver: isDraggable ? handleDragOver : undefined,
            onDrop: isDraggable ? (e)=>handleDrop(e, phase) : undefined,
            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("relative transition-all duration-150", isDragging && "opacity-50", isDragOver && "before:absolute before:inset-x-0 before:-top-1 before:h-0.5 before:bg-brand-500"),
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                onClick: ()=>onPhaseClick?.(phase),
                className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors", isCurrent ? "bg-brand-600/20 text-brand-400" : "hover:bg-surface-3 text-zinc-300", isDraggable && "cursor-grab active:cursor-grabbing"),
                children: [
                    isDraggable && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "text-zinc-600 text-xs select-none",
                        children: "⋮⋮"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 134,
                        columnNumber: 13
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("w-2 h-2 rounded-full flex-shrink-0", status === "completed" && "bg-green-500", status === "in_progress" && "bg-yellow-500", status === "pending" && "bg-zinc-600")
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 138,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: "flex-1 text-sm",
                        children: __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["PHASE_NAMES"][phase] || phase
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 148,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("text-xs", statusInfo.color),
                        children: statusInfo.label
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 153,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 122,
                columnNumber: 9
            }, this)
        }, phase, false, {
            fileName: "[project]/components/progress-panel.tsx",
            lineNumber: 107,
            columnNumber: 7
        }, this);
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "p-4",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "mb-6",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                        className: "text-lg font-semibold text-zinc-100",
                        children: project?.name || "未选择项目"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 165,
                        columnNumber: 9
                    }, this),
                    project && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-sm text-zinc-500 mt-1",
                        children: [
                            "版本 ",
                            project.version
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 169,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 164,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "space-y-1",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                        className: "text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3",
                        children: "流程进度"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 177,
                        columnNumber: 9
                    }, this),
                    topPhases.map((phase)=>renderPhaseItem(phase, false)),
                    middlePhases.length > 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "py-1",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "text-xs text-zinc-600 px-3 mb-1 flex items-center gap-1",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "↕"
                                    }, void 0, false, {
                                        fileName: "[project]/components/progress-panel.tsx",
                                        lineNumber: 188,
                                        columnNumber: 15
                                    }, this),
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                        children: "可拖拽调整顺序"
                                    }, void 0, false, {
                                        fileName: "[project]/components/progress-panel.tsx",
                                        lineNumber: 189,
                                        columnNumber: 15
                                    }, this)
                                ]
                            }, void 0, true, {
                                fileName: "[project]/components/progress-panel.tsx",
                                lineNumber: 187,
                                columnNumber: 13
                            }, this),
                            middlePhases.map((phase)=>renderPhaseItem(phase, true))
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 186,
                        columnNumber: 11
                    }, this),
                    bottomPhases.map((phase)=>renderPhaseItem(phase, false))
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 176,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "my-6 border-t border-surface-3"
            }, void 0, false, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 200,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "space-y-2",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                        className: "text-xs font-medium text-zinc-500 uppercase tracking-wider mb-3",
                        children: "快捷操作"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 204,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors",
                        children: "+ 新建版本"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 208,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors",
                        children: "查看历史版本"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 212,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        className: "w-full px-3 py-2 text-sm text-left text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 rounded-lg transition-colors",
                        children: "导出内容"
                    }, void 0, false, {
                        fileName: "[project]/components/progress-panel.tsx",
                        lineNumber: 216,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/progress-panel.tsx",
                lineNumber: 203,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/progress-panel.tsx",
        lineNumber: 162,
        columnNumber: 5
    }, this);
}
_s(ProgressPanel, "706y8Wk888lpJ5fidmwWMtXSsOY=");
_c = ProgressPanel;
var _c;
__turbopack_context__.k.register(_c, "ProgressPanel");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/components/content-panel.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ContentPanel",
    ()=>ContentPanel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/utils.ts [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
// frontend/components/content-panel.tsx
// 功能: 中栏内容展示面板
// 主要组件: ContentPanel
"use client";
;
;
function ContentPanel({ projectId, currentPhase, fields, onFieldUpdate }) {
    const phaseFields = fields.filter((f)=>f.phase === currentPhase);
    if (!projectId) {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "flex items-center justify-center h-full text-zinc-500",
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "text-center",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-lg mb-2",
                        children: "请选择或创建一个项目"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 30,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-sm",
                        children: "在左侧选择项目开始工作"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 31,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 29,
                columnNumber: 9
            }, this)
        }, void 0, false, {
            fileName: "[project]/components/content-panel.tsx",
            lineNumber: 28,
            columnNumber: 7
        }, this);
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "p-6 max-w-4xl mx-auto",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "mb-8",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                        className: "text-2xl font-bold text-zinc-100",
                        children: __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["PHASE_NAMES"][currentPhase] || currentPhase
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 41,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-zinc-500 mt-1",
                        children: getPhaseDescription(currentPhase)
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 44,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 40,
                columnNumber: 7
            }, this),
            phaseFields.length > 0 ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "space-y-6",
                children: phaseFields.map((field)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(FieldCard, {
                        field: field,
                        onUpdate: (content)=>onFieldUpdate?.(field.id, content)
                    }, field.id, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 53,
                        columnNumber: 13
                    }, this))
            }, void 0, false, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 51,
                columnNumber: 9
            }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "text-center py-12 text-zinc-500",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: "当前阶段暂无内容"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 62,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-sm mt-2",
                        children: "在右侧与 AI Agent 对话开始生产内容"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 63,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 61,
                columnNumber: 9
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/content-panel.tsx",
        lineNumber: 38,
        columnNumber: 5
    }, this);
}
_c = ContentPanel;
function FieldCard({ field, onUpdate }) {
    _s();
    const [isEditing, setIsEditing] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(false);
    const [content, setContent] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(field.content);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "FieldCard.useEffect": ()=>{
            setContent(field.content);
        }
    }["FieldCard.useEffect"], [
        field.content
    ]);
    const handleSave = ()=>{
        onUpdate?.(content);
        setIsEditing(false);
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "bg-surface-2 rounded-xl border border-surface-3 overflow-hidden",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "px-4 py-3 border-b border-surface-3 flex items-center justify-between",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h3", {
                                className: "font-medium text-zinc-200",
                                children: field.name
                            }, void 0, false, {
                                fileName: "[project]/components/content-panel.tsx",
                                lineNumber: 95,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "text-xs text-zinc-500",
                                children: field.status === "completed" ? "已生成" : field.status === "generating" ? "生成中..." : "待生成"
                            }, void 0, false, {
                                fileName: "[project]/components/content-panel.tsx",
                                lineNumber: 96,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 94,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex gap-2",
                        children: isEditing ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["Fragment"], {
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: handleSave,
                                    className: "px-3 py-1 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors",
                                    children: "保存"
                                }, void 0, false, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 108,
                                    columnNumber: 15
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                    onClick: ()=>{
                                        setContent(field.content);
                                        setIsEditing(false);
                                    },
                                    className: "px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors",
                                    children: "取消"
                                }, void 0, false, {
                                    fileName: "[project]/components/content-panel.tsx",
                                    lineNumber: 114,
                                    columnNumber: 15
                                }, this)
                            ]
                        }, void 0, true) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            onClick: ()=>setIsEditing(true),
                            className: "px-3 py-1 text-sm bg-surface-3 hover:bg-surface-4 rounded-lg transition-colors",
                            children: "编辑"
                        }, void 0, false, {
                            fileName: "[project]/components/content-panel.tsx",
                            lineNumber: 125,
                            columnNumber: 13
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 105,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 93,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "p-4",
                children: isEditing ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("textarea", {
                    value: content,
                    onChange: (e)=>setContent(e.target.value),
                    className: "w-full min-h-[200px] bg-surface-1 border border-surface-3 rounded-lg p-3 text-zinc-200 resize-y focus:outline-none focus:ring-2 focus:ring-brand-500"
                }, void 0, false, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 138,
                    columnNumber: 11
                }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                    className: "prose prose-invert max-w-none",
                    children: field.content ? /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "whitespace-pre-wrap text-zinc-300",
                        children: field.content
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 146,
                        columnNumber: 15
                    }, this) : /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-zinc-500 italic",
                        children: "暂无内容"
                    }, void 0, false, {
                        fileName: "[project]/components/content-panel.tsx",
                        lineNumber: 150,
                        columnNumber: 15
                    }, this)
                }, void 0, false, {
                    fileName: "[project]/components/content-panel.tsx",
                    lineNumber: 144,
                    columnNumber: 11
                }, this)
            }, void 0, false, {
                fileName: "[project]/components/content-panel.tsx",
                lineNumber: 136,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/content-panel.tsx",
        lineNumber: 91,
        columnNumber: 5
    }, this);
}
_s(FieldCard, "sr2QOAZsh+rTK/TOTm1VlWgkN1I=");
_c1 = FieldCard;
function getPhaseDescription(phase) {
    const descriptions = {
        intent: "澄清内容生产的核心意图和目标",
        research: "调研目标用户，了解痛点和需求",
        design_inner: "设计内容生产方案和大纲",
        produce_inner: "生产核心内容",
        design_outer: "设计外延传播方案",
        produce_outer: "为各渠道生产营销内容",
        simulate: "模拟用户体验，收集反馈",
        evaluate: "全面评估内容质量"
    };
    return descriptions[phase] || "";
}
var _c, _c1;
__turbopack_context__.k.register(_c, "ContentPanel");
__turbopack_context__.k.register(_c1, "FieldCard");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/components/agent-panel.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AgentPanel",
    ()=>AgentPanel
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/utils.ts [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
// frontend/components/agent-panel.tsx
// 功能: 右栏AI Agent对话面板
// 主要组件: AgentPanel
"use client";
;
;
function AgentPanel({ projectId, onSendMessage, isLoading = false }) {
    _s();
    const [messages, setMessages] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])([]);
    const [input, setInput] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("");
    const [sending, setSending] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(false);
    const messagesEndRef = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useRef"])(null);
    // 自动滚动到底部
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "AgentPanel.useEffect": ()=>{
            messagesEndRef.current?.scrollIntoView({
                behavior: "smooth"
            });
        }
    }["AgentPanel.useEffect"], [
        messages
    ]);
    const handleSend = async ()=>{
        if (!input.trim() || !projectId || sending) return;
        const userMessage = input.trim();
        setInput("");
        setSending(true);
        // 添加用户消息
        setMessages((prev)=>[
                ...prev,
                {
                    role: "user",
                    content: userMessage
                }
            ]);
        try {
            // 调用API
            const response = await onSendMessage?.(userMessage);
            if (response) {
                setMessages((prev)=>[
                        ...prev,
                        {
                            role: "assistant",
                            content: response
                        }
                    ]);
            }
        } catch (error) {
            setMessages((prev)=>[
                    ...prev,
                    {
                        role: "assistant",
                        content: `抱歉，发生了错误：${error instanceof Error ? error.message : "未知错误"}`
                    }
                ]);
        } finally{
            setSending(false);
        }
    };
    const handleKeyDown = (e)=>{
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "flex flex-col h-full",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "px-4 py-3 border-b border-surface-3",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h2", {
                        className: "font-semibold text-zinc-100",
                        children: "AI Agent"
                    }, void 0, false, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 80,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        className: "text-xs text-zinc-500",
                        children: projectId ? "与 Agent 对话推进内容生产" : "请先选择项目"
                    }, void 0, false, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 81,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 79,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex-1 overflow-y-auto p-4 space-y-4",
                children: [
                    messages.length === 0 && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "text-center text-zinc-500 py-8",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                children: "开始对话吧！"
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 90,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                                className: "text-sm mt-2",
                                children: '你可以说 "开始" 来启动内容生产流程'
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 91,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 89,
                        columnNumber: 11
                    }, this),
                    messages.map((msg, idx)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(MessageBubble, {
                            message: msg
                        }, idx, false, {
                            fileName: "[project]/components/agent-panel.tsx",
                            lineNumber: 98,
                            columnNumber: 11
                        }, this)),
                    sending && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center gap-2 text-zinc-500",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                className: "w-2 h-2 bg-brand-500 rounded-full animate-pulse"
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 103,
                                columnNumber: 13
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                className: "text-sm",
                                children: "Agent 正在思考..."
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 104,
                                columnNumber: 13
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 102,
                        columnNumber: 11
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        ref: messagesEndRef
                    }, void 0, false, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 108,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 87,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "p-4 border-t border-surface-3",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex gap-2",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                type: "text",
                                value: input,
                                onChange: (e)=>setInput(e.target.value),
                                onKeyDown: handleKeyDown,
                                placeholder: projectId ? "输入消息... 使用 @ 引用字段" : "请先选择项目",
                                disabled: !projectId || sending,
                                className: "flex-1 px-4 py-2 bg-surface-2 border border-surface-3 rounded-lg text-zinc-200 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 114,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                onClick: handleSend,
                                disabled: !projectId || !input.trim() || sending,
                                className: "px-4 py-2 bg-brand-600 hover:bg-brand-700 disabled:bg-surface-3 disabled:cursor-not-allowed rounded-lg transition-colors",
                                children: "发送"
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 123,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 113,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex gap-2 mt-2",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(QuickAction, {
                                label: "继续",
                                onClick: ()=>{
                                    setInput("继续");
                                    handleSend();
                                },
                                disabled: !projectId || sending
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 134,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(QuickAction, {
                                label: "开始调研",
                                onClick: ()=>{
                                    setInput("开始消费者调研");
                                    handleSend();
                                },
                                disabled: !projectId || sending
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 142,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(QuickAction, {
                                label: "评估",
                                onClick: ()=>{
                                    setInput("评估当前内容");
                                    handleSend();
                                },
                                disabled: !projectId || sending
                            }, void 0, false, {
                                fileName: "[project]/components/agent-panel.tsx",
                                lineNumber: 150,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/components/agent-panel.tsx",
                        lineNumber: 133,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 112,
                columnNumber: 7
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/components/agent-panel.tsx",
        lineNumber: 77,
        columnNumber: 5
    }, this);
}
_s(AgentPanel, "Ses8pDRlbHEuSMMJuYjZv7Tb/cc=");
_c = AgentPanel;
function MessageBubble({ message }) {
    const isUser = message.role === "user";
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("flex", isUser ? "justify-end" : "justify-start"),
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$utils$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["cn"])("max-w-[85%] px-4 py-2 rounded-2xl", isUser ? "bg-brand-600 text-white rounded-br-md" : "bg-surface-3 text-zinc-200 rounded-bl-md"),
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "whitespace-pre-wrap text-sm",
                children: message.content
            }, void 0, false, {
                fileName: "[project]/components/agent-panel.tsx",
                lineNumber: 182,
                columnNumber: 9
            }, this)
        }, void 0, false, {
            fileName: "[project]/components/agent-panel.tsx",
            lineNumber: 174,
            columnNumber: 7
        }, this)
    }, void 0, false, {
        fileName: "[project]/components/agent-panel.tsx",
        lineNumber: 168,
        columnNumber: 5
    }, this);
}
_c1 = MessageBubble;
function QuickAction({ label, onClick, disabled }) {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
        onClick: onClick,
        disabled: disabled,
        className: "px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 hover:bg-surface-3 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors",
        children: label
    }, void 0, false, {
        fileName: "[project]/components/agent-panel.tsx",
        lineNumber: 200,
        columnNumber: 5
    }, this);
}
_c2 = QuickAction;
var _c, _c1, _c2;
__turbopack_context__.k.register(_c, "AgentPanel");
__turbopack_context__.k.register(_c1, "MessageBubble");
__turbopack_context__.k.register(_c2, "QuickAction");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/lib/api.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "agentAPI",
    ()=>agentAPI,
    "fieldAPI",
    ()=>fieldAPI,
    "projectAPI",
    ()=>projectAPI,
    "settingsAPI",
    ()=>settingsAPI
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$polyfills$2f$process$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = /*#__PURE__*/ __turbopack_context__.i("[project]/node_modules/next/dist/build/polyfills/process.js [app-client] (ecmascript)");
// frontend/lib/api.ts
// 功能: API客户端，封装后端API调用
// 主要函数: fetchAPI, streamAPI
// 数据结构: Project, Field, ChatMessage
const API_BASE = ("TURBOPACK compile-time value", "http://localhost:8000") || "http://localhost:8000";
// ============== API Functions ==============
async function fetchAPI(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...options.headers
        }
    });
    if (!response.ok) {
        const error = await response.json().catch(()=>({
                detail: "Unknown error"
            }));
        // 处理Pydantic验证错误格式 (detail可能是数组)
        let errorMessage;
        if (typeof error.detail === "string") {
            errorMessage = error.detail;
        } else if (Array.isArray(error.detail)) {
            errorMessage = error.detail.map((e)=>e.msg || e.message || JSON.stringify(e)).join("; ");
        } else {
            errorMessage = `API error: ${response.status}`;
        }
        throw new Error(errorMessage);
    }
    return response.json();
}
const projectAPI = {
    list: ()=>fetchAPI("/api/projects/"),
    get: (id)=>fetchAPI(`/api/projects/${id}`),
    create: (data)=>fetchAPI("/api/projects/", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    update: (id, data)=>fetchAPI(`/api/projects/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    delete: (id)=>fetchAPI(`/api/projects/${id}`, {
            method: "DELETE"
        }),
    createVersion: (id, version_note)=>fetchAPI(`/api/projects/${id}/versions`, {
            method: "POST",
            body: JSON.stringify({
                version_note
            })
        })
};
const fieldAPI = {
    listByProject: (projectId, phase)=>{
        const query = phase ? `?phase=${phase}` : "";
        return fetchAPI(`/api/fields/project/${projectId}${query}`);
    },
    get: (id)=>fetchAPI(`/api/fields/${id}`),
    create: (data)=>fetchAPI("/api/fields/", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    update: (id, data)=>fetchAPI(`/api/fields/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    delete: (id)=>fetchAPI(`/api/fields/${id}`, {
            method: "DELETE"
        }),
    generate: (id, pre_answers = {})=>fetchAPI(`/api/fields/${id}/generate`, {
            method: "POST",
            body: JSON.stringify({
                pre_answers
            })
        })
};
const agentAPI = {
    chat: (projectId, message, currentPhase)=>fetchAPI("/api/agent/chat", {
            method: "POST",
            body: JSON.stringify({
                project_id: projectId,
                message,
                current_phase: currentPhase
            })
        }),
    advance: (projectId)=>fetchAPI("/api/agent/advance", {
            method: "POST",
            body: JSON.stringify({
                project_id: projectId,
                message: "继续"
            })
        }),
    stream: async function*(projectId, message, currentPhase) {
        const response = await fetch(`${API_BASE}/api/agent/stream`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                project_id: projectId,
                message,
                current_phase: currentPhase
            })
        });
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        if (!reader) return;
        while(true){
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            const lines = text.split("\n");
            for (const line of lines){
                if (line.startsWith("data: ")) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        yield data;
                    } catch  {
                    // Ignore parse errors
                    }
                }
            }
        }
    }
};
const settingsAPI = {
    // System Prompts
    listSystemPrompts: ()=>fetchAPI("/api/settings/system-prompts"),
    updateSystemPrompt: (id, data)=>fetchAPI(`/api/settings/system-prompts/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    // Creator Profiles
    listCreatorProfiles: ()=>fetchAPI("/api/settings/creator-profiles"),
    createCreatorProfile: (data)=>fetchAPI("/api/settings/creator-profiles", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateCreatorProfile: (id, data)=>fetchAPI(`/api/settings/creator-profiles/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteCreatorProfile: (id)=>fetchAPI(`/api/settings/creator-profiles/${id}`, {
            method: "DELETE"
        }),
    // Field Templates
    listFieldTemplates: ()=>fetchAPI("/api/settings/field-templates"),
    createFieldTemplate: (data)=>fetchAPI("/api/settings/field-templates", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateFieldTemplate: (id, data)=>fetchAPI(`/api/settings/field-templates/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteFieldTemplate: (id)=>fetchAPI(`/api/settings/field-templates/${id}`, {
            method: "DELETE"
        }),
    // Channels
    listChannels: ()=>fetchAPI("/api/settings/channels"),
    createChannel: (data)=>fetchAPI("/api/settings/channels", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateChannel: (id, data)=>fetchAPI(`/api/settings/channels/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteChannel: (id)=>fetchAPI(`/api/settings/channels/${id}`, {
            method: "DELETE"
        }),
    // Simulators
    listSimulators: ()=>fetchAPI("/api/settings/simulators"),
    createSimulator: (data)=>fetchAPI("/api/settings/simulators", {
            method: "POST",
            body: JSON.stringify(data)
        }),
    updateSimulator: (id, data)=>fetchAPI(`/api/settings/simulators/${id}`, {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    deleteSimulator: (id)=>fetchAPI(`/api/settings/simulators/${id}`, {
            method: "DELETE"
        }),
    // Agent Settings
    getAgentSettings: ()=>fetchAPI("/api/settings/agent"),
    updateAgentSettings: (data)=>fetchAPI("/api/settings/agent", {
            method: "PUT",
            body: JSON.stringify(data)
        }),
    // Logs
    listLogs: (projectId)=>{
        const query = projectId ? `?project_id=${projectId}` : "";
        return fetchAPI(`/api/settings/logs${query}`);
    },
    exportLogs: (projectId)=>{
        const query = projectId ? `?project_id=${projectId}` : "";
        return fetchAPI(`/api/settings/logs/export${query}`);
    }
};
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/app/workspace/page.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>WorkspacePage
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$layout$2f$workspace$2d$layout$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/layout/workspace-layout.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$progress$2d$panel$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/progress-panel.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$content$2d$panel$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/content-panel.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$components$2f$agent$2d$panel$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/components/agent-panel.tsx [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/api.ts [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature();
// frontend/app/workspace/page.tsx
// 功能: 内容生产工作台主页面
// 主要组件: WorkspacePage
"use client";
;
;
;
;
;
;
function WorkspacePage() {
    _s();
    const [projects, setProjects] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])([]);
    const [currentProject, setCurrentProject] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const [fields, setFields] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])([]);
    const [loading, setLoading] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(true);
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    // 加载项目列表
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "WorkspacePage.useEffect": ()=>{
            loadProjects();
        }
    }["WorkspacePage.useEffect"], []);
    // 加载当前项目的字段
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "WorkspacePage.useEffect": ()=>{
            if (currentProject) {
                loadFields(currentProject.id);
            }
        }
    }["WorkspacePage.useEffect"], [
        currentProject?.id
    ]);
    const loadProjects = async ()=>{
        try {
            const data = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["projectAPI"].list();
            setProjects(data);
            // 自动选择第一个项目
            if (data.length > 0 && !currentProject) {
                setCurrentProject(data[0]);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "加载项目失败");
        } finally{
            setLoading(false);
        }
    };
    const loadFields = async (projectId)=>{
        try {
            const data = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["fieldAPI"].listByProject(projectId);
            setFields(data);
        } catch (err) {
            console.error("加载字段失败:", err);
        }
    };
    const handlePhaseClick = (phase)=>{
        if (currentProject) {
            setCurrentProject({
                ...currentProject,
                current_phase: phase
            });
        }
    };
    const handlePhaseReorder = async (newPhaseOrder)=>{
        if (!currentProject) return;
        try {
            // 更新本地状态
            setCurrentProject({
                ...currentProject,
                phase_order: newPhaseOrder
            });
            // 保存到服务器
            await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["projectAPI"].update(currentProject.id, {
                phase_order: newPhaseOrder
            });
        } catch (err) {
            console.error("更新阶段顺序失败:", err);
        }
    };
    const handleFieldUpdate = async (fieldId, content)=>{
        try {
            await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["fieldAPI"].update(fieldId, {
                content
            });
            // 重新加载字段
            if (currentProject) {
                loadFields(currentProject.id);
            }
        } catch (err) {
            console.error("更新字段失败:", err);
        }
    };
    const handleSendMessage = async (message)=>{
        if (!currentProject) {
            throw new Error("请先选择项目");
        }
        const response = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["agentAPI"].chat(currentProject.id, message, currentProject.current_phase);
        // 更新项目状态
        if (response.phase_status) {
            setCurrentProject({
                ...currentProject,
                phase_status: response.phase_status
            });
        }
        // 重新加载字段
        loadFields(currentProject.id);
        return response.message;
    };
    const handleCreateProject = async ()=>{
        const name = prompt("请输入项目名称:");
        if (!name) return;
        try {
            const project = await __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["projectAPI"].create({
                name
            });
            setProjects([
                ...projects,
                project
            ]);
            setCurrentProject(project);
        } catch (err) {
            alert("创建项目失败: " + (err instanceof Error ? err.message : "未知错误"));
        }
    };
    if (loading) {
        return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
            className: "flex items-center justify-center h-screen bg-surface-0",
            children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "text-zinc-400",
                children: "加载中..."
            }, void 0, false, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 138,
                columnNumber: 9
            }, this)
        }, void 0, false, {
            fileName: "[project]/app/workspace/page.tsx",
            lineNumber: 137,
            columnNumber: 7
        }, this);
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
        className: "h-screen flex flex-col",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("header", {
                className: "h-14 flex-shrink-0 border-b border-surface-3 bg-surface-1 flex items-center justify-between px-4",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center gap-4",
                        children: [
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                                className: "text-lg font-semibold bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent",
                                children: "内容生产系统"
                            }, void 0, false, {
                                fileName: "[project]/app/workspace/page.tsx",
                                lineNumber: 148,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("select", {
                                value: currentProject?.id || "",
                                onChange: (e)=>{
                                    const project = projects.find((p)=>p.id === e.target.value);
                                    setCurrentProject(project || null);
                                },
                                className: "px-3 py-1.5 bg-surface-2 border border-surface-3 rounded-lg text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-brand-500",
                                children: [
                                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                        value: "",
                                        children: "选择项目"
                                    }, void 0, false, {
                                        fileName: "[project]/app/workspace/page.tsx",
                                        lineNumber: 161,
                                        columnNumber: 13
                                    }, this),
                                    projects.map((p)=>/*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("option", {
                                            value: p.id,
                                            children: [
                                                p.name,
                                                " (v",
                                                p.version,
                                                ")"
                                            ]
                                        }, p.id, true, {
                                            fileName: "[project]/app/workspace/page.tsx",
                                            lineNumber: 163,
                                            columnNumber: 15
                                        }, this))
                                ]
                            }, void 0, true, {
                                fileName: "[project]/app/workspace/page.tsx",
                                lineNumber: 153,
                                columnNumber: 11
                            }, this),
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                                onClick: handleCreateProject,
                                className: "px-3 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors",
                                children: "+ 新建项目"
                            }, void 0, false, {
                                fileName: "[project]/app/workspace/page.tsx",
                                lineNumber: 169,
                                columnNumber: 11
                            }, this)
                        ]
                    }, void 0, true, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 147,
                        columnNumber: 9
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                        className: "flex items-center gap-4",
                        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("a", {
                            href: "/settings",
                            className: "text-sm text-zinc-400 hover:text-zinc-200 transition-colors",
                            children: "后台设置"
                        }, void 0, false, {
                            fileName: "[project]/app/workspace/page.tsx",
                            lineNumber: 178,
                            columnNumber: 11
                        }, this)
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 177,
                        columnNumber: 9
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 146,
                columnNumber: 7
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "flex-1 overflow-hidden",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$layout$2f$workspace$2d$layout$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["WorkspaceLayout"], {
                    leftPanel: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$progress$2d$panel$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["ProgressPanel"], {
                        project: currentProject,
                        onPhaseClick: handlePhaseClick,
                        onPhaseReorder: handlePhaseReorder
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 191,
                        columnNumber: 13
                    }, void 0),
                    centerPanel: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$content$2d$panel$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["ContentPanel"], {
                        projectId: currentProject?.id || null,
                        currentPhase: currentProject?.current_phase || "intent",
                        fields: fields,
                        onFieldUpdate: handleFieldUpdate
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 198,
                        columnNumber: 13
                    }, void 0),
                    rightPanel: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$components$2f$agent$2d$panel$2e$tsx__$5b$app$2d$client$5d$__$28$ecmascript$29$__["AgentPanel"], {
                        projectId: currentProject?.id || null,
                        onSendMessage: handleSendMessage
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 206,
                        columnNumber: 13
                    }, void 0)
                }, void 0, false, {
                    fileName: "[project]/app/workspace/page.tsx",
                    lineNumber: 189,
                    columnNumber: 9
                }, this)
            }, void 0, false, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 188,
                columnNumber: 7
            }, this),
            error && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "fixed bottom-4 right-4 px-4 py-2 bg-red-600 text-white rounded-lg",
                children: [
                    error,
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                        onClick: ()=>setError(null),
                        className: "ml-2 text-red-200 hover:text-white",
                        children: "✕"
                    }, void 0, false, {
                        fileName: "[project]/app/workspace/page.tsx",
                        lineNumber: 218,
                        columnNumber: 11
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/app/workspace/page.tsx",
                lineNumber: 216,
                columnNumber: 9
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/app/workspace/page.tsx",
        lineNumber: 144,
        columnNumber: 5
    }, this);
}
_s(WorkspacePage, "Y3IQhrhYnXjsNEvyluVj2k8TwHw=");
_c = WorkspacePage;
var _c;
__turbopack_context__.k.register(_c, "WorkspacePage");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
]);

//# sourceMappingURL=_7df1c9ed._.js.map