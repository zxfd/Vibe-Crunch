# Vibe Crunch 🏋️

> **当 AI 在卷代码的时候，你也该卷腹了。**
>
> When AI is crunching code, you should be crunching too.

**简体中文** | [English](README.md)

Vibe Crunch 把 AI 编程时长时间坐在电脑前的工作流，切成一段段 **约 30 秒–3 分钟的微训练 / 活动间歇**。当你在 Codex / Claude Code 提交任务后，AI 会立即正常开始工作；Vibe Crunch 独立判断当前是否适合提醒，并在满足条件时随机给出一个短动作。

主要使用场景是 **macOS 上的 ChatGPT / Codex Desktop 客户端**。正常桌面端使用 **不需要安装 Codex CLI，也不需要摄像头**。

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
      从动作池完全随机抽 1 个动作
              │
              ├────────────────────────► AI 继续工作
              │
              ▼
      Vibe Crunch 微训练弹窗
      约 30 秒–3 分钟
      [完成了] [换一个] [跳过这次] [今天休息]
```

Hook 采用 **fail-open**：训练提醒自身出错时不能阻塞 AI 任务。成功的 `UserPromptSubmit` Hook 不向 stdout 或 stderr 输出内容，避免把无关提示注入 Codex 的模型上下文。

Vibe Crunch **不做摄像头识别、不统计姿态关键点，也不自动判断你是否真的完成动作**。动作完成由用户自己确认：点击 **完成了** 后才记入统计。

## 默认参数

- 自动提醒冷却时间：30 分钟
- **每天完成 5 次微训练**作为默认目标
- 每次新提醒都从当前动作池中 **等概率随机抽取**
- 不维护轮换顺序，也不主动避免连续两次随机到同一个动作
- **换一个**会从除当前动作以外的动作池重新随机，不算跳过、不算完成、不产生新的提醒，也不重新计算冷却时间
- **跳过这次不消耗每日目标**，冷却时间结束后仍可能再次提醒
- **今天休息**会停止当天后续自动提醒
- 并发会话共享 1 个待处理提醒
- 未处理提醒 90 分钟后过期
- 默认模式不需要摄像头、OpenCV、MediaPipe 或姿态模型
- macOS 默认中文弹窗

每日限制按**实际确认完成次数**计算，不按弹窗次数计算。手动执行 `vibe-crunch now` 后如果完成训练，也会计入当天目标。

## 当前默认动作池

当前动作池偏向 **长期久坐、近期活动量较少、基础力量正在恢复、希望对膝关节采用保守负荷** 的使用场景。没有把动态深蹲、弓步、跳跃等膝关节负荷更高或动作要求更复杂的内容放进默认随机池。

| 动作 | 默认训练量 | 主要目的 |
|---|---|---|
| 俯卧撑 | 1 × 4–6 次 | 上肢推力；避免做到力竭 |
| 靠墙静蹲 | 1 × 20–30 秒 | 下肢等长刺激；只用舒适的浅到中等膝屈曲角度 |
| 平板支撑 | 1 × 30–40 秒 | 核心抗伸展 |
| 臀桥 | 1 × 12–15 次 | 臀部 / 后链，减少久坐后髋部“关机”感 |
| 死虫式 | 1 × 每侧 6–8 次 | 核心控制 |
| 鸟狗式 | 1 × 每侧 6–8 次 | 核心稳定、腰背控制 |
| 站姿提踵 | 1 × 15–20 次 | 小腿活动、短暂离座 |
| 离座走动 | 2–3 分钟 | 直接打断久坐 |
| 墙天使 | 1 × 8–12 次 | 胸椎 / 肩胛活动，缓解长时间电脑姿势 |

这是一套 **exercise snack / 微训练**，不是完整健身课，也不替代有计划的力量训练或康复训练。

靠墙静蹲的默认提示明确要求：**不追求蹲到 90°，膝部出现疼痛、卡住或明显不适就停止**。这里的目标是逐步恢复活动，而不是测试膝盖极限。

## 中文弹窗

弹窗会显示动作、组数 / 时长、动作要点，以及四个操作按钮：

- **完成了**：记录本次训练完成
- **换一个**：立即随机换成另一个动作，当前这次提醒继续存在
- **跳过这次**：只跳过当前这一轮，冷却结束后仍可能继续提醒
- **今天休息**：当天剩余时间不再自动提醒

macOS 使用原生 `NSAlert` 作为后备弹窗；正常情况下会优先使用项目自己的轻量 UI。

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
2. 连续多次执行 `~/.local/bin/vibe-crunch now`，动作来自默认动作池且不存在固定轮换顺序。
3. `~/.local/bin/vibe-crunch now` 能弹出带四个按钮的中文训练窗口。
4. 点击 **完成了** 后，“今日完成”次数增加。
5. 点击 **换一个** 后立即随机显示另一个动作，“今日完成”和“今日自动提醒”都不增加。
6. 点击 **跳过这次** 后，“今日完成”次数保持不变。
7. Codex 普通任务在弹窗存在时仍立即开始工作，不能被训练弹窗阻塞。
8. 点击 **今天休息** 后，当天后续自动提醒停止；手动 `now` 仍可用于显式测试。
9. 默认配置显示 30 分钟冷却、每日完成目标 5 次。
10. 整个默认 Vibe Crunch 流程不会请求摄像头权限。

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

动作池配置使用 `exercise_pool`。旧版本遗留的固定轮换状态不会参与新的随机选择。

## 调度取舍

真实编码过程中会出现大量很小的 prompt。每个 prompt 都触发训练会造成通知疲劳，因此 Hook 只作为事件源，是否弹出自动提醒由状态机决定。

调度器负责冷却时间、按完成次数计算的每日目标、单一 pending、完全随机动作选择、当天休息和重复 Hook 去重。换动作只修改当前 pending，不创建新的提醒，因此不会扭曲冷却时间和当天调度计数。

## 关于仓库里的摄像头代码

仓库历史上游来自 Workout Gate，因此仍保留 `challenge.py`、`detector.py` 等摄像头 / MediaPipe 兼容代码。

**这些代码不是 Vibe Crunch 当前默认功能，也不会被 `hooks/micro_gate.py` 的正常流程调用。** Vibe Crunch 自己不依赖摄像头识别。保留这些文件只是为了上游兼容和历史代码可追溯性。

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
workout_gate/micro_plan.py    冷却 / 每日完成目标 / 随机动作池
workout_gate/micro.py         状态、统计、中文弹窗、控制命令
hooks/gate.sh                 Codex / Claude Hook 入口
hooks/session_start.sh        轻量插件初始化
vibe-crunch                   源码目录控制脚本
```

## License 与上游

MIT。Vibe Crunch 保留原 Workout Gate 的代码和许可证。历史上游架构和实现归属于 [BotchetDig/workout-gate](https://github.com/BotchetDig/workout-gate)。
