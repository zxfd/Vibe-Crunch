# Vibe Crunch → Apple 健康同步

Vibe Crunch 运行在 Mac 上，而 Apple Health 数据库只能由支持 HealthKit 数据访问的平台写入。当前方案不安装服务器、不要求每天操作 iPhone，也不伪造卡路里或心率：Mac 在你点击 **“完成了”** 后发送一个跨设备 Focus 信号，由 iPhone 的“快捷指令”自动写入 HealthKit。

## 数据流

```text
Mac / Vibe Crunch
  点击“完成了”
      │
      ├─ 1. 保存完整事件 JSON 到 iCloud Drive
      │      ~/Library/Mobile Documents/com~apple~CloudDocs/
      │      VibeCrunch/HealthSync/events/<event-id>.json
      │
      └─ 2. shortcuts run "Vibe Crunch Health Sync" -i <event.json>
                 │
                 ▼
        Mac 快捷指令读取 signal_focus
                 │
                 ▼
        打开对应的共享 Focus
                 │  Apple 账号跨设备同步
                 ▼
        iPhone 个人自动化（立即运行）
                 │
                 ▼
        “Vibe Crunch → Health”快捷指令
                 │
                 ├─ Log Workout → Apple 健康
                 └─ 关闭本次 Focus
```

Health 写入**不依赖 iPhone 在触发时读取 iCloud 文件**。事件 JSON 是完整账本，主要用于审计、故障排查和未来更精确的 companion app / 回填。

## 第一版写入精度

Vibe Crunch 的 10 个动作映射到四类 Apple Health Workout：

| Vibe Crunch 动作 | Health 类别 | Focus 信号 |
|---|---|---|
| 俯卧撑、靠墙静蹲、臀桥、侧卧抬腿、提踵 | Functional Strength Training | `Vibe Sync Strength` |
| 平板支撑、死虫式、鸟狗式 | Core Training | `Vibe Sync Core` |
| 离座走动 | Walking | `Vibe Sync Walk` |
| 墙天使 | Flexibility | `Vibe Sync Mobility` |

第一版 iPhone 快捷指令使用保守固定时长：

| Focus | 写入 Health 的时长 |
|---|---:|
| `Vibe Sync Strength` | 1 分钟 |
| `Vibe Sync Core` | 1 分钟 |
| `Vibe Sync Walk` | 2 分 30 秒 |
| `Vibe Sync Mobility` | 1 分钟 |

不要在快捷指令里填写卡路里、距离或心率。没有传感器数据时，这些值不应被猜测。

完整事件 JSON 仍保存 Vibe Crunch 的动作名、目标次数/时间、完成时间、事件 ID，以及基于弹窗开启时间计算并按动作范围截断的 `duration_seconds`。因此未来更换成原生 iPhone companion 时，不需要改变 Mac 侧数据格式。

## 一次性设置

### 1. 创建四个专用 Focus

在 iPhone：`设置 → 专注模式 → + → 自定`，创建下面四个 Focus，名称请保持完全一致：

```text
Vibe Sync Strength
Vibe Sync Core
Vibe Sync Walk
Vibe Sync Mobility
```

这些 Focus 只是机器间信号，不是为了屏蔽通知。可以把允许通知设置得尽量宽松，并关闭它们的“共享专注模式状态”。

确认 `设置 → 专注模式 → 跨设备共享` 已开启。Mac 的 `系统设置 → 专注模式 → 跨设备共享` 也应开启。

### 2. 在 iPhone 创建一个真正写 Health 的快捷指令

新建快捷指令，命名：

```text
Vibe Crunch → Health
```

第一步加入 **Get Current Focus / 获取当前专注模式**。

然后用 `If / 如果` 按当前 Focus 分四个分支。每个分支执行两件事：先写 Workout，再关闭对应 Focus。

#### Strength 分支

```text
如果 Current Focus 是 Vibe Sync Strength
  调整“当前日期”：减去 1 分钟
  记录锻炼：Functional Strength Training
    日期 = 调整后的日期
    时长 = 1 分钟
    卡路里 = 留空
    距离 = 留空
  设置专注模式 Vibe Sync Strength：关闭
```

#### Core 分支

```text
如果 Current Focus 是 Vibe Sync Core
  调整“当前日期”：减去 1 分钟
  记录锻炼：Core Training
    日期 = 调整后的日期
    时长 = 1 分钟
    卡路里 = 留空
    距离 = 留空
  设置专注模式 Vibe Sync Core：关闭
```

#### Walk 分支

```text
如果 Current Focus 是 Vibe Sync Walk
  调整“当前日期”：减去 150 秒
  记录锻炼：Walking
    日期 = 调整后的日期
    时长 = 2 分 30 秒
    卡路里 = 留空
    距离 = 留空
  设置专注模式 Vibe Sync Walk：关闭
```

#### Mobility 分支

```text
如果 Current Focus 是 Vibe Sync Mobility
  调整“当前日期”：减去 1 分钟
  记录锻炼：Flexibility
    日期 = 调整后的日期
    时长 = 1 分钟
    卡路里 = 留空
    距离 = 留空
  设置专注模式 Vibe Sync Mobility：关闭
```

第一次测试 `Log Workout / 记录锻炼` 时，iOS 会要求“快捷指令”获得写入健康数据的权限。只授予本方案实际需要的 Workout 写入权限即可。

### 3. 为四个 Focus 各建一个 iPhone 个人自动化

在 `快捷指令 → 自动化` 中分别创建四条：

```text
当 Vibe Sync Strength 打开时 → 运行“Vibe Crunch → Health”
当 Vibe Sync Core 打开时     → 运行“Vibe Crunch → Health”
当 Vibe Sync Walk 打开时     → 运行“Vibe Crunch → Health”
当 Vibe Sync Mobility 打开时 → 运行“Vibe Crunch → Health”
```

每条都设置为 **立即运行 / 不询问确认**。不要为“关闭时”建立自动化。

### 4. 在 Mac 创建桥接快捷指令

新建快捷指令，名称必须为：

```text
Vibe Crunch Health Sync
```

让快捷指令接受 **Files / 文件** 输入。Vibe Crunch 会通过 macOS 的 `shortcuts` 命令把本次事件 JSON 作为文件输入传进来。

动作逻辑：

```text
获取“快捷指令输入”的文本
从输入中获取字典
获取字典值：signal_focus

如果 signal_focus 是 "Vibe Sync Strength"
  设置专注模式 Vibe Sync Strength：打开
否则如果是 "Vibe Sync Core"
  设置专注模式 Vibe Sync Core：打开
否则如果是 "Vibe Sync Walk"
  设置专注模式 Vibe Sync Walk：打开
否则如果是 "Vibe Sync Mobility"
  设置专注模式 Vibe Sync Mobility：打开
结束如果
```

不要在这个 Mac 快捷指令里加通知、菜单或“询问输入”；它必须能从命令行静默运行。

## 启用与验收

代码升级后先检查：

```sh
vibe-crunch health-sync status
```

预期至少看到：

```text
Apple 健康同步：未开启
传输：Mac Shortcut → 共享 Focus → iPhone Shortcut → HealthKit
Mac 触发快捷指令：Vibe Crunch Health Sync
快捷指令检测：已找到
```

确认一次性设置完成后：

```sh
vibe-crunch health-sync on
vibe-crunch now
```

完成弹出的动作并点击 **“完成了”**。随后验证：

1. Mac 的 `iCloud Drive/VibeCrunch/HealthSync/events/` 出现对应 `<event-id>.json`；
2. 对应 `Vibe Sync ...` Focus 短暂出现并由 iPhone 自动化关闭；
3. iPhone `健康 → 浏览 → 活动 → 锻炼` 中出现一条对应类型的 Workout；
4. `vibe-crunch status` 显示 Apple 健康同步已开启，并显示累计事件账本数量。

若第 1 步成功而 Health 没有记录，Vibe Crunch 的完成数据仍然没有丢失；先不要重复手工写入 Health，以免产生重复 Workout，使用事件 JSON 排查 Focus / 自动化链路。

## 关闭

随时可以停止向 Apple 健康发送新事件：

```sh
vibe-crunch health-sync off
```

这不会删除 Vibe Crunch 本地统计，也不会删除已经写入 Apple 健康的 Workout。

## 为什么不用 Mac 直接写 HealthKit

Apple 在 macOS 上提供 HealthKit framework 主要用于代码兼容，但 Mac 本身没有可供 App 访问的 Health 数据库；`HKHealthStore.isHealthDataAvailable()` 在 macOS 上为 false。因此必须由 iPhone、iPad、Apple Watch 等可访问 Health 数据的平台完成最终写入。

参考：

- Apple HealthKit：`HKHealthStore.isHealthDataAvailable()`
- Apple Shortcuts：从命令行运行快捷指令（`shortcuts run ... -i <file>`）
- Apple Shortcuts：Focus 设置触发条件与无需确认的个人自动化
- Apple Focus：跨设备共享
