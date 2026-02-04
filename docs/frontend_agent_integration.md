# 前端 Agent @ 引用功能集成规划

**创建时间**: 2026-02-04  
**状态**: 已完成

---

## 一、现状分析

### 1.1 前端已有功能

| 功能 | 状态 | 位置 |
|------|------|------|
| @ 引用 UI（下拉选择） | ✅ 已实现 | `agent-panel.tsx` L81-111 |
| 字段名插入到输入框 | ✅ 已实现 | `insertMention()` |
| @ 高亮显示 | ✅ 已实现 | `renderContent()` |
| 字段列表传入 | ✅ 已实现 | `fields` prop |

### 1.2 缺失的功能

| 功能 | 缺失位置 | 影响 |
|------|----------|------|
| `references` 参数未传递 | `agentAPI.chat()` | 后端无法识别引用 |
| 输入中的 @ 解析 | `handleSend()` | 无法提取字段名 |
| 修改成功反馈 | 响应处理 | 用户不知道修改是否成功 |
| 字段刷新 | `onContentUpdate` | 修改后中间栏不更新 |

### 1.3 后端已就绪

- `ChatRequest.references: List[str]` 已定义
- API 层解析引用并查询内容
- `modify_node` / `query_node` 已实现
- 字段修改后自动保存

---

## 二、修改基准 (Benchmark)

### 2.1 功能验收标准

| 场景 | 用户操作 | 期望结果 |
|------|----------|----------|
| @ 引用修改 | 输入 "@做什么 修改成一句话" | 字段被修改，中间栏刷新，对话区显示确认 |
| @ 引用查询 | 输入 "@消费者调研 总结一下" | 对话区显示总结，字段不变 |
| 多字段引用 | 输入 "@做什么 和 @给谁看 对比" | 对话区显示对比分析 |
| 无引用对话 | 输入 "这个项目怎么样" | 正常对话，不影响字段 |

### 2.2 UI 反馈标准

| 事件 | 反馈类型 | 内容 |
|------|----------|------|
| 修改成功 | Toast 或 对话消息 | "已修改【字段名】" |
| 修改失败 | Error 提示 | 具体错误原因 |
| 查询成功 | 对话消息 | 分析结果 |

### 2.3 性能标准

- 输入 @ 后 50ms 内显示下拉菜单
- 发送后 3s 内返回响应（正常网络）
- 刷新字段后 500ms 内 UI 更新

---

## 三、详细修改步骤

### Phase 1: API 层修改

#### 1.1 修改 `agentAPI.chat()` 接口
- 添加 `references` 参数
- 确保与后端 `ChatRequest` 一致

#### 1.2 修改 `ChatResponse` 类型
- 添加 `field_updated` 字段
- 添加 `action` 字段标识操作类型

### Phase 2: AgentPanel 核心逻辑

#### 2.1 实现 `parseReferences()` 函数
- 从输入文本中提取所有 `@xxx` 引用
- 返回字段名数组

#### 2.2 修改 `handleSend()` 函数
- 调用 `parseReferences()` 提取引用
- 传递 `references` 给 `agentAPI.chat()`
- 处理响应中的 `field_updated`

#### 2.3 增强响应处理
- 如果 `field_updated` 存在，显示修改成功提示
- 调用 `onContentUpdate()` 刷新字段

### Phase 3: UI 增强

#### 3.1 添加操作反馈
- 修改成功时显示 Toast
- 失败时显示错误信息

#### 3.2 优化 @ 引用显示
- 在消息中高亮已修改的字段
- 添加"已修改"标记

### Phase 4: 测试验证

#### 4.1 核心场景测试
- 测试 @ + 修改
- 测试 @ + 查询
- 测试普通对话
- 测试多字段引用

---

## 四、关联影响分析

### 4.1 受影响的组件

| 组件 | 修改类型 | 影响范围 |
|------|----------|----------|
| `lib/api.ts` | 接口定义 | 全局 |
| `agent-panel.tsx` | 核心逻辑 | 右栏 |
| `content-panel.tsx` | 刷新触发 | 中间栏 |
| `workspace/page.tsx` | 状态管理 | 整体协调 |

### 4.2 数据流向

```
用户输入 "@做什么 修改成xxx"
        ↓
parseReferences() → ["做什么"]
        ↓
agentAPI.chat(projectId, message, references)
        ↓
后端 modify_node → 修改字段
        ↓
响应 { field_updated: {...}, message: "已修改" }
        ↓
onContentUpdate() → 刷新字段列表
        ↓
中间栏显示更新后的内容
```

---

## 五、执行检查清单

### 5.1 修改前检查
- [ ] 确认后端 API 正常运行
- [ ] 确认 `ChatRequest.references` 定义正确
- [ ] 确认 `field_updated` 在响应中返回

### 5.2 修改后检查
- [ ] TypeScript 编译无错误
- [ ] 控制台无运行时错误
- [ ] @ 引用 UI 正常工作
- [ ] 修改操作正确保存
- [ ] 刷新后字段内容更新

---

## 六、完成总结

**完成时间**: 2026-02-04

### 6.1 已实现功能

1. **API 层修改**
   - `agentAPI.chat()` 新增 `references` 参数
   - `ChatResponse` 新增 `field_updated` 字段
   - 新增 `parseReferences()` 辅助函数

2. **AgentPanel 修改**
   - `handleSend()` 自动提取 @ 引用并传递
   - `handleSaveEdit()` 同样支持 @ 引用
   - 添加 Toast 通知显示修改结果

3. **数据流完整**
   ```
   用户输入 "@字段名 修改成xxx"
           ↓
   parseReferences() → ["字段名"]
           ↓
   agentAPI.chat(projectId, message, { references })
           ↓
   后端 modify_node → 修改字段
           ↓
   响应 { field_updated: {...} }
           ↓
   Toast 显示 "已修改【字段名】"
           ↓
   onContentUpdate() → 中间栏刷新
   ```

### 6.2 测试场景

| 场景 | 操作 | 期望结果 |
|------|------|----------|
| @ 修改 | "@做什么 修改成一句话" | Toast显示成功，中间栏刷新 |
| @ 查询 | "@消费者调研 总结一下" | Agent返回分析结果 |
| 普通对话 | "项目进展如何" | 正常对话，无字段变化 |

### 6.3 关键文件修改

- `frontend/lib/api.ts`: 新增 parseReferences、修改 chat 接口
- `frontend/components/agent-panel.tsx`: handleSend、Toast 组件
- `backend/api/agent.py`: FieldUpdatedInfo、ChatResponseSchema
