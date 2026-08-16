## 1. 改造 AI 判题 Prompt（核心修复）

**文件**: `app/services/judge.py`

**核心改动**：将 AI 输入从"题目 + 参考答案 + 孩子作答"改为"题目 + 孩子作答"（不给参考答案），迫使 AI 独立解题。

**新 Prompt 设计（两阶段 Chain-of-Thought）**：

```
Step 1 - 独立解题（不给参考答案）:
  System: "你是严谨的批改老师。请先独立解答以下题目，给出完整解题过程和你算出的正确答案。"
  User: "题目：{question}\n孩子作答：{user_answer}"
  -> AI 必须输出 {"my_answer": "...", "child_correct": true/false, "reason": "..."}

Step 2 - 检查参考答案（仅当 child_correct=false 时）:
  System: "以下是题目存储的参考答案，请判断参考答案本身是否算错。"
  User: "题目：{question}\n你的答案：{my_answer}\n参考答案：{reference_answer}"
  -> AI 输出 {"stored_wrong": true/false, "correct_answer": "..."}
```

**关键设计变更**：
- Step 1 的输入中**完全不包含参考答案**，AI 被迫独立计算
- Step 2 只在 Step 1 判定孩子错误时才触发（省 API 调用）
- Step 2 此时引入参考答案，用于检测存储答案是否本身有误
- 输出格式保持兼容：`{correct, stored_wrong, correct_answer, reason}`

**对 `judge_wrong_items` 函数的改动**：
- 将单次 AI 调用拆分为两步调用
- Step 1 用新 prompt（不含参考答案），解析 `child_correct`
- Step 2 仅对 `child_correct=false` 的题做二次调用，检测 `stored_wrong`
- 缓存逻辑保持不变（同题+同作答被判对 -> 直接复用）
- `max_tokens` 适当增大（两步输出更多）

## 2. 手动 AI 复审按钮增加 `force` 参数

**文件**: `app/routers/grading.py` + `app/services/judge.py`

**改动**：
- `judge_wrong_items` 增加 `force: bool = False` 参数，为 True 时跳过缓存直接调用 AI
- `/api/ai/rejudge` 端点默认传 `force=True`，确保手动按钮每次都是真正的 AI 复审
- 自动复审（交卷/练习提交）保持 `force=False`（利用缓存节省 API 调用）

## 3. 为背诵模块补充 AI 复审

**文件**: `app/routers/classical/recite.py`

**改动**：
- 在 `review` 提交接口中，对 `correct=false` 的项收集起来，调用 `judge_wrong_items` 做 AI 复审
- AI 判对的项：翻转结果为 correct，更新进度时按 correct 处理
- 注意：古诗文填空题答案通常是精确匹配，AI 复审主要帮助处理"繁体字/通假字/语序不同但含义相同"等边界情况

**文件**: `web/src/logic/appOptions.js`

**改动**：
- 背诵提交后的前端反馈中，如果 AI 复审翻转了结果，显示 toast 提示"AI 复核：你的答案正确"

## 4. 确保手动复审正常工作（调试确认）

需要验证的链路：
- 前端 `aiRejudgeCurrent` / `aiRejudgeWrong` / `aiRecheckAppeal` -> POST `/api/ai/rejudge`
- 后端 `rejudge` -> `judge_wrong_items(force=True)` -> 两步 AI 调用
- AI 返回 `correct=true` -> 翻转 `is_correct`、重算分数、清除错题记录

## 5. 构建前端并部署

`cd web && npm run build`

## 测试计划

1. 用一道数学题测试：参考答案存为错误值（如 161），孩子作答为正确值（如 161.6），验证 AI 独立判对
2. 手动点击"AI 复审"按钮，确认每次都触发真正的 AI 调用（不命中缓存）
3. 背诵中答错一道题，验证 AI 复审是否触发
