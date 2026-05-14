# 多项目 / 多 Codex 并行编排工作流

## 适用场景

- 委托人一次下发多个项目或多个任务
- 同一项目需要多个 Codex CLI 并行开发
- 需要 OpenClaw 统一测试、集成、push 和创建 release PR

## 职责边界

- **OpenClaw**：任务拆分、队列管理、tmux session 管理、worktree/branch 管理、合并锁、测试门禁、push、`gh` PR、状态汇报。
- **Codex CLI**：在指定 feature worktree 内完成单个任务，提交 git commit，运行测试，汇报结果。

Codex 不负责启动其他 Codex，也不负责并行调度和 release PR。

## 默认分支模型

- `dev`：开发集成分支
- `release`：发布目标分支
- `feature/<task-id>`：单任务开发分支，从最新 `dev` 拉出

规则：

1. 不直接在 `dev` 上开发。
2. 每个任务使用独立 feature 分支。
3. 同一项目并行任务必须使用独立 `git worktree`。
4. 同一项目合并到 `dev` 必须串行，并由 OpenClaw 持有项目级合并锁。
5. `dev` 测试通过后，才 push 并创建或更新 `dev -> release` PR。

## 编排流程

```
委托人下发多个任务
    ↓
OpenClaw 按项目分组，生成 task-id
    ↓
每个任务从最新 dev 创建 feature/<task-id> + worktree
    ↓
每个 worktree 启动独立 Codex CLI
    ↓
Codex 完成开发、git commit 和 feature 测试
    ↓
OpenClaw 检查结果
    ↓
同一项目串行合并 feature -> dev
    ↓
dev 测试通过后 push
    ↓
创建或更新 dev -> release PR
    ↓
汇报委托人
```

## 启动任务

```bash
git fetch origin
git switch dev
git pull --ff-only origin dev
git worktree add -b feature/<task-id> ../<project>-worktrees/<task-id> dev
bash <skill_dir>/hooks/start_codex.sh codex-<task-id> ../<project>-worktrees/<task-id> --full-auto
```

给 Codex 的提示词必须说明：

- 当前 worktree 和 feature 分支
- 任务目标和验收标准
- 必须在本分支内完成修改
- 必须运行项目测试
- 必须提交 git commit
- 完成后汇报变更、测试结果、风险

## 集成任务

同一项目同一时间只能集成一个 feature 分支。

集成前确认 feature 分支测试通过且已有 git commit。

```bash
git switch dev
git pull --ff-only origin dev
git merge --no-ff feature/<task-id>
# run project tests
git push origin dev
```

如果 merge conflict 或测试失败：

1. 不 push `dev`
2. 保留现场
3. 让 Codex 修复冲突或测试失败
4. 修复后重新运行集成流程

## Release PR

```bash
gh pr list --base release --head dev --state open
gh pr create --base release --head dev --title "<title>" --body "<summary>"
```

如果已存在 `dev -> release` PR，不重复创建；更新 PR body 或追加评论，说明本次新增的任务、测试结果和风险。

## 状态汇报

OpenClaw 汇报时包含：

1. 每个项目和任务的状态
2. 每个 feature 分支的 Codex 结果
3. 合并到 `dev` 的任务列表
4. 测试结果
5. `dev -> release` PR 链接或失败原因
6. 需要委托人决策的问题
