# Vibe Crunch → Apple 健康同步

Vibe Crunch 运行在 Mac 上，而 Apple Health 最终必须由能够访问 HealthKit 数据库的设备写入。当前方案不需要服务器，也不要求日常再操作 iPhone：你在 Mac 上点击 **“完成了”** 后，Vibe Crunch 保存完整事件，再通过 Mac 快捷指令打开一个专用 Focus；iOS 27 上的 `Vibe Crunch → Health` 快捷指令被该 Focus 触发，写入 HealthKit 后立即关闭 Focus。

## 已验证的数据流

```text
Mac / Vibe Crunch
  点击“完成了”
      │
      ├─ 保存完整事件 JSON 到 iCloud Drive
      │    VibeCrunch/HealthSync/events/<event-id>.json
      │
      └─ shortcuts run "Vibe Crunch Health Sync" -i <event.json>
                 │
                 ▼
           Mac 快捷指令读取 signal_focus
                 │
                 ▼
           打开对应共享 Focus
                 │
                 ▼
      iPhone：Vibe Crunch → Health
      顶部 Focus 自动化触发器命中
                 │
                 ├─ Log Workout → Apple 健康
                 └─ 关闭对应 Focus
```

iPhone **不需要在触发时读取 iCloud JSON**。JSON 是源事件账本，用于审计、故障排查、未来回填和 companion app；Health 写入由 Focus 类别信号驱动。

## 四类 Workout 映射

| Vibe Crunch 动作 | Apple 健康 Workout | Focus 信号 | 写入时长 |
|---|---|---|---:|
| 俯卧撑、靠墙静蹲、臀桥、侧卧抬腿、提踵 | 功能性力量训练 | `Vibe Sync Strength` | 1 分钟 |
| 平板支撑、死虫式、鸟狗式 | 核心训练 | `Vibe Sync Core` | 1 分钟 |
| 离座走动 | 步行 | `Vibe Sync Walk` | 2 分 30 秒 |
| 墙天使 | 柔韧度训练 | `Vibe Sync Mobility` | 1 分钟 |

当前 iOS 27 国区版的 `记录锻炼 / Log Workout` 不允许把“大卡”和“距离”真正留空，因此两项固定写 **0**。它们只是 Shortcuts 强制字段的占位值，不代表真实消耗或真实距离；后续分析不能把这些 0 当作运动强度证据。

完整 JSON 仍保存：动作名、目标次数/时间、event ID、完成时间、Health 类别、Focus 信号，以及按动作范围截断后的 `duration_seconds`。

---

# 一次性设置

## 1. 创建四个专用 Focus

在 iPhone：`设置 → 专注模式 → + → 自定`，创建：

```text
Vibe Sync Strength
Vibe Sync Core
Vibe Sync Walk
Vibe Sync Mobility
```

名称必须完全一致。**不要在名称前后留空格**；实机验收时已经出现过前导空格导致 If 条件无法命中的问题。

确认 iPhone 和 Mac 的 **跨设备共享 Focus** 都已开启。

## 2. 创建 iPhone 快捷指令 `Vibe Crunch → Health`

新建快捷指令：

```text
Vibe Crunch → Health
```

主体先加入：

```text
获取当前专注模式
```

然后使用 4 个彼此独立的 If；条件都比较 **当前专注模式 → 名称**。

### Strength

```text
如果 名称 是 Vibe Sync Strength
  当前日期
  从日期减去 1 分钟
  记录锻炼：功能性力量训练
    日期 = 调整后的日期
    持续时间 = 1 分钟
    大卡 = 0
    距离 = 0
  关闭 Vibe Sync Strength 专注模式
结束如果
```

### Core

```text
如果 名称 是 Vibe Sync Core
  当前日期
  从日期减去 1 分钟
  记录锻炼：核心训练
    日期 = 调整后的日期
    持续时间 = 1 分钟
    大卡 = 0
    距离 = 0
  关闭 Vibe Sync Core 专注模式
结束如果
```

### Walk

```text
如果 名称 是 Vibe Sync Walk
  当前日期
  从日期减去 2.5 分钟
  记录锻炼：步行
    日期 = 调整后的日期
    持续时间 = 150 秒
    大卡 = 0
    距离 = 0
  关闭 Vibe Sync Walk 专注模式
结束如果
```

### Mobility

```text
如果 名称 是 Vibe Sync Mobility
  当前日期
  从日期减去 1 分钟
  记录锻炼：柔韧度训练
    日期 = 调整后的日期
    持续时间 = 1 分钟
    大卡 = 0
    距离 = 0
  关闭 Vibe Sync Mobility 专注模式
结束如果
```

### iOS 27：把 4 个 Focus 触发器直接加到这个快捷指令顶部

本项目已经在 iOS 27 国区版实机验证：**一个快捷指令可以手动添加多个自动化触发器，并以“或”连接。**

在 `Vibe Crunch → Health` 编辑器中，从底部动作面板进入 **「自动化」** 类别，手动添加：

```text
Vibe Sync Strength 打开时
或
Vibe Sync Core 打开时
或
Vibe Sync Walk 打开时
或
Vibe Sync Mobility 打开时
```

这些触发器是**用户手动添加**的，不是系统自动生成。

因此 iOS 27 的首选结构不是“4 条独立自动化再运行另一个快捷指令”，而是：

```text
[4 个 Focus 打开触发器，OR]
          ↓
Vibe Crunch → Health 主体
```

实机已验证：手动打开 Strength / Core Focus 后，快捷指令能够后台执行、写入对应 Workout，并自动关闭 Focus。

## 3. 创建 Mac 桥接快捷指令 `Vibe Crunch Health Sync`

这一条必须能被 macOS `shortcuts` CLI 静默运行。

名称必须为：

```text
Vibe Crunch Health Sync
```

它接收 Vibe Crunch 通过 `-i <event.json>` 传入的 **文件输入**，逻辑为：

```text
获取“快捷指令输入”的文本
从输入中获取字典
获取字典值：signal_focus

如果 signal_focus 是 "Vibe Sync Strength"
  打开 Vibe Sync Strength
否则如果 signal_focus 是 "Vibe Sync Core"
  打开 Vibe Sync Core
否则如果 signal_focus 是 "Vibe Sync Walk"
  打开 Vibe Sync Walk
否则如果 signal_focus 是 "Vibe Sync Mobility"
  打开 Vibe Sync Mobility
结束如果
```

不要添加通知、菜单、询问输入或任何需要人工确认的动作。

Apple 官方支持在 macOS 终端使用：

```sh
shortcuts run "Vibe Crunch Health Sync" -i /path/to/event.json
```

## 4. Mac 自检

代码更新后运行：

```sh
vibe-crunch health-sync status
```

应能看到类似：

```text
Apple 健康同步：未开启
事件账本目录：...
iCloud Drive：已找到
Mac 触发快捷指令：Vibe Crunch Health Sync
快捷指令检测：已找到
Mac 端桥接：已就绪
```

只有显示 **`Mac 端桥接：已就绪`** 后，才开启：

```sh
vibe-crunch health-sync on
```

---

# 最终验收

开启同步后：

```sh
vibe-crunch now
```

完成动作并点击 **“完成了”**，验证：

1. `iCloud Drive/VibeCrunch/HealthSync/events/` 新增 `<event-id>.json`；
2. 对应 `Vibe Sync ...` Focus 短暂打开；
3. iPhone 的 `Vibe Crunch → Health` 被触发；
4. Focus 自动关闭；
5. Apple 健康出现对应 Workout；
6. `vibe-crunch status` 显示健康同步已开启和事件账本数量。

只有 **完成了** 会发送 Health 事件；换一个 / 跳过 / 今天休息都不会写 Workout。

## 当前 MVP 边界

Focus 是状态信号，不是带 ACK 的消息队列。如果 iPhone 长时间离线，而同一个 Focus 一直保持打开，再次“打开”同一个 Focus 可能没有新的状态转换。源 JSON 事件仍会保留，但当前 MVP 不承诺 HealthKit 端事务级 exactly-once。

因此当前保证的是：

- Vibe Crunch 本地完成记录不被 Health 故障阻塞；
- 源事件保存在 iCloud JSON 账本；
- 正常在线场景下自动写 Apple 健康；
- 不伪造心率、卡路里或距离。

若实际使用发现 Focus 传输可靠性不足，再升级为原生 iPhone companion：读取 event ID → 写 HealthKit → 回传 ACK → 幂等重试。

## 关闭

```sh
vibe-crunch health-sync off
```

不会删除本地统计，也不会删除已经写入 Apple 健康的 Workout。
