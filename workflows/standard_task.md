# 标准任务工作流

## 概述
从接收委托人的任务到最终交付的完整流程。

## 流程

```
委托人下发任务
    ↓
[1] 理解任务 → 分析需求、确认范围
    ↓
[2] 评估执行方式 → exec 或 TUI，是否需要实时检查环境能力
    ↓
[3] 设计提示词 → 默认不读知识库，复杂任务才参考 prompting_patterns.md
    ↓
[4] 与委托人确认 → 展示提示词 + 配置调整计划
    ↓
[5] 准备分支 → 从 dev 拉 feature 分支，必要时创建 worktree
    ↓
[6] 执行 → tmux 启动 Codex，发送提示词
    ↓
[7] 等待 → hooks 触发通知（不轮询）
    ↓
[8] 检查输出 → capture-pane + 检查文件
    ↓
[9] 判断质量 → 满足要求？
    ├─ 否 → [9a] 向委托人汇报问题 + 修改计划 → 继续发指令 → 回到 [7]
    └─ 是 → [10] 合并到 dev → 测试 → push dev → 创建/更新 dev -> release PR
              ↓
            [11] 向委托人汇报结果
```

## 详细步骤

### [1] 理解任务

- 确认任务目标、验收标准
- 识别涉及的项目/文件/技术栈
- 不清楚时主动追问，不猜测

### [2] 评估执行方式

- 判断使用 exec（单次任务）还是 TUI（多轮、审批、长任务）
- 对 Git 项目中的代码变更，默认采用 `dev -> feature/<task-id> -> dev -> release PR`
- 同一项目同时开发多个任务时，必须使用独立 feature 分支和独立 `git worktree`
- 默认使用 Codex 当前运行环境配置
- 不默认读取 `capabilities.md`
- 任务明确依赖特定能力，或执行失败疑似环境能力缺失时，才实时检查 CLI 输出或让 Codex 自检

### [3] 设计提示词

构建提示词；复杂任务才参考 `prompting_patterns.md`：
- 明确任务描述
- 提供必要上下文（文件路径、技术约束）
- 要求 Codex 自行检查项目、完成修改、运行测试、提交 feature 分支变更、汇报变更
- 指定完成条件

### [4] 与委托人确认

向委托人展示：
- 最终提示词内容
- 执行方式（exec 或 TUI）和审批模式
- 分支计划（feature 分支名、是否使用 worktree、完成后是否创建 `dev -> release` PR）
- 如确有必要，说明任何配置调整
- 预估复杂度

等委托人确认后再执行。

### [5] 准备分支

代码变更默认不直接在 `dev` 上开发。

```bash
git fetch origin
git switch dev
git pull --ff-only origin dev
git worktree add -b feature/<task-id> ../<project>-worktrees/<task-id> dev
```

后续 Codex 在 feature worktree 中开发、测试和提交。非 Git 项目、只读分析任务或委托人明确指定其他分支策略时，可跳过或调整此步骤。

### [6] 执行

```bash
# 创建 tmux session
tmux new-session -d -s codex-<任务名> -c <工作目录>

# 启动 Codex（如需特殊配置）
tmux send-keys -t codex-<任务名> 'codex --no-alt-screen' Enter

# 等待启动完成（信任确认等）
sleep 3
tmux capture-pane -t codex-<任务名> -p -S -20

# 如需切换模型
tmux send-keys -t codex-<任务名> '/model gpt-5.2 xhigh'
sleep 1
tmux send-keys -t codex-<任务名> Enter

# 发送提示词（⚠️ 文本和 Enter 必须分两次发，中间 sleep 1s）
tmux send-keys -t codex-<任务名> '<提示词>'
sleep 1
tmux send-keys -t codex-<任务名> Enter
```

### [7] 等待

- hooks 配置 `notify` 会在 Codex 完成 turn 时触发通知
- 不需要轮询，等待被唤醒
- 如 hooks 未触发（超时），可手动 capture-pane 检查

### [8] 检查输出

```bash
# 查看 Codex 的回复
tmux capture-pane -t codex-<任务名> -p -S -200

# 检查产出文件
ls -la <工作目录>/<预期输出>
cat <关键文件>
```

### [9] 判断质量

评估标准：
- 是否完成了任务目标
- 代码质量是否合格
- 是否引入了新问题
- 测试是否通过

### [9a] 迭代修改

向委托人汇报：
1. Codex 的回复摘要
2. 发现的问题
3. 准备给 Codex 的修改指令
4. 修改原因

然后继续发送指令给 Codex。

### [10] 合并、测试、PR

OpenClaw 负责集成，不让多个 Codex 同时写 `dev`。

1. 确认 feature worktree 中测试通过。
2. 确认 feature 分支变更已提交；如 Codex 未提交，则检查 diff 后提交。
3. 获取项目级 `dev` 合并锁。
4. 在主工作目录更新 `dev`：

```bash
git switch dev
git pull --ff-only origin dev
```

5. 合并 feature 分支：

```bash
git merge --no-ff feature/<task-id>
```

6. 在 `dev` 上重新运行项目测试。
7. 测试通过后 push `dev`：

```bash
git push origin dev
```

8. 创建或更新 `dev -> release` PR：

```bash
gh pr list --base release --head dev --state open
gh pr create --base release --head dev --title "<title>" --body "<summary>"
```

如果已有打开的 PR，不重复创建；更新说明或评论即可。合并冲突、测试失败、push/PR 权限失败时停止发布步骤，让 Codex 修复或向委托人汇报。

### [11] 最终汇报

向委托人汇报：
1. 任务完成状态
2. 关键变更摘要
3. 测试结果
4. 分支、合并和 PR 状态
5. 需要注意的事项
