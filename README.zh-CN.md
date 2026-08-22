# Vibe Crunch 🏋️

> **当 AI 在卷代码的时候，你也该卷腹了。**
>
> When AI is crunching code, you should be crunching too.

**简体中文** | [English](README.md)

Vibe Crunch 把 AI 编程时的等待时间变成 **2–4 分钟的微型阻力训练**。当你在 Codex / Claude Code 提交任务后，AI 会立即正常开始工作；Vibe Crunch 独立判断当前是否适合训练，并在满足条件时弹出短时训练提醒。

主要使用场景是 **macOS 上的 ChatGPT / Codex Desktop 客户端**。正常桌面端使用 **不需要安装 Codex CLI**。

当前插件版本：**v2.0.6**。

## 工作方式

```text
提交 AI 任务
      │
      ▼
UserPromptSubmit
      │
      ├── 是否超过冷却时间？
      ├── 今天是否还没完成训练目标？
      ├── 是否没有待处理提醒？
      └── 今天是否没有选择休息？
              │
              ▼
        轮换训练动作
              │
              ├────────────────────────► AI 继续工作
              │
              ▼
      Vibe Crunch 微训练弹窗
      训练约 2–4 分钟
      [完成了] [换一个] [跳过这次] [今天休息]
```

Hook 采用 **fail-open**：训练提醒自身出错时不能阻塞 AI 任务。成功的 `UserPromptSubmit` Hook 不向 stdout 或 stderr 输出内容，避免把无关提示注入 Codex 的模型上下文。

## 默认参数

- 自动提醒冷却时间：30 分钟
- **每天完成 5 次微训练**作为默认目标
- **换一个**会立即把当前动作换成下一个动作，不算跳过、不算完成、不产生新的提醒，也不重新计算冷却时间
- **跳过这次不消耗每日目标**，冷却时间结束后仍可能再次提醒
- **今天休息**会停止当天后续自动提醒
- 并发会话共享 1 个待处理提醒
- 未处理提醒 90 分钟后过期
- 动作按固定顺序轮换
- 每组大约保留 2–4 次余力
- 默认模式不需要摄像头、OpenCV、MediaPipe 或姿态模型
- macOS 默认中文弹窗

每日限制按**实际完成次数**计算，不按弹窗次数计算。手动执行 `vibe-crunch now` 后如果完成训练，也会计入当天目标，因为实际训练量已经发生。

| 顺序 | 动作 | 训练量 |
|---|---|---|
| A | 俯卧撑 | 2 × 8–12 |
| B | 弹力带 / 背包划船 | 2 × 12–15 |
| C | 椅子深蹲 | 2 × 10–15 |
| D | 臀桥 | 2 × 12–20 |
| E | 死虫式 | 2 × 8–10 / 侧 |

这是一套 **exercise snack / 微训练**，不是完整健身课。

## 中文弹窗

弹窗会显示动作、组数、次数、动作要点，以及四个操作按钮：

- **完成了**：记录本次训练完成
- **换一个**：立即换成下一个训练动作，当前这次提醒继续存在
- **跳过这次**：只跳过当前这一轮，冷却结束后仍可能继续提醒
- **今天休息**：当天剩余时间不再自动提醒

macOS 使用原生 `NSAlert` 显示四个响应按钮。

内部 exercise key 保持稳定，避免破坏已有状态和统计。

## Codex Desktop 安装

正常 macOS 使用方式通过 **ChatGPT / Codex Desktop 的 Plugins 界面**完成，不需要安装 `codex` 终端命令。

插件名：

```text
vibe-crunch
```

仓库：

```text
https://github.com/zxfd/Vibe-Crunch
```

安装或更新插件后：

1. 如果 Codex 要求 Hook 信任，批准 `UserPromptSubmit`；
2. 完全退出 ChatGPT / Codex Desktop 后重新打开；
3. 新建一个 Codex 会话；
4. 在 Terminal 验证控制脚本。

`SessionStart` 会安装：

```text
~/.local/bin/vibe-crunch
```

## 常用命令

这些是普通 shell 命令，不是 Codex CLI 命令。

```sh
~/.local/bin/vibe-crunch status
~/.local/bin/vibe-crunch on
~/.local/bin/vibe-crunch off
~/.local/bin/vibe-crunch now
~/.local/bin/vibe-crunch done
~/.local/bin/vibe-crunch skip
~/.local/bin/vibe-crunch rest

~/.local/bin/vibe-crunch set cooldown 30
~/.local/bin/vibe-crunch set daily-goal 5
```

如果 `~/.local/bin` 已经在 `PATH`：

```sh
vibe-crunch status
vibe-crunch now
```

在源码目录中：

```sh
./vibe-crunch status
./vibe-crunch now
```

立即关闭自动提醒：

```sh
~/.local/bin/vibe-crunch off
```

重新开启：

```sh
~/.local/bin/vibe-crunch on
```

## 验收

已经看到训练弹窗，说明核心 Hook 链路已经工作：

```text
Codex Desktop
→ UserPromptSubmit
→ hooks/gate.sh
→ hooks/micro_gate.py
→ 独立 Vibe Crunch 弹窗
```

完整验收：

1. `~/.local/bin/vibe-crunch status` 能正常输出。
2. `~/.local/bin/vibe-crunch now` 能弹出带四个按钮的中文训练窗口。
3. 点击 **完成了** 后，“今日完成”次数增加。
4. 点击 **换一个** 后立即显示下一个动作，“今日完成”和“今日自动提醒”都不增加。
5. 点击 **跳过这次** 后，“今日完成”次数保持不变。
6. Codex 普通任务在弹窗存在时仍立即开始工作，不能被训练弹窗阻塞。
7. 点击 **今天休息** 后，当天后续自动提醒停止；手动 `now` 仍可用于显式测试。
8. 默认配置显示 30 分钟冷却、每日完成目标 5 次。

## 数据和统计

运行时数据位于：

```text
~/.workout-gate/
```

Vibe Crunch 使用独立文件：

```text
vibe-crunch.json
vibe-crunch-state.json
vibe-crunch-stats.json
```

这样微训练调度和统计不会与仓库中保留的上游摄像头模式混用。

## 调度取舍

真实编码过程中会出现大量很小的 prompt。每个 prompt 都触发训练会造成通知疲劳，因此 Hook 只作为事件源，是否弹出自动提醒由状态机决定。

调度器负责冷却时间、按完成次数计算的每日目标、单一 pending、动作轮换、当天休息和重复 Hook 去重。换动作只修改当前 pending，不创建新的提醒，因此不会扭曲冷却时间和当天调度计数。

## 上游摄像头模式

仓库继续保留 Workout Gate 的摄像头实现以维持上游兼容，但它不是 Vibe Crunch 默认流程。

如果明确需要该模式，可在源码目录执行：

```sh
./bootstrap.sh
```

这条路径会安装 OpenCV、MediaPipe 和姿态模型。

## 开发

运行核心单测：

```sh
python3 -m unittest tests.test_micro_plan
python3 -m unittest tests.test_micro_gate
python3 -m unittest tests.test_micro_ui
```

主要结构：

```text
hooks/micro_gate.py           非阻塞 UserPromptSubmit Hook
workout_gate/micro_plan.py    冷却 / 每日完成目标 / 动作轮换
workout_gate/micro.py         状态、统计、中文弹窗、控制命令
hooks/gate.sh                 Codex / Claude Hook 入口
hooks/session_start.sh        轻量插件初始化
vibe-crunch                   源码目录控制脚本
```

## License 与上游

MIT。Vibe Crunch 保留原 Workout Gate 的代码和许可证。上游摄像头挑战架构和实现归属于 [BotchetDig/workout-gate](https://github.com/BotchetDig/workout-gate)。
