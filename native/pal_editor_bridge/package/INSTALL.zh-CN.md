# PalEditorBridge UE4SS 模组安装

## 前置条件

- Windows Steam 版 Palworld 客户端或 Palworld Dedicated Server。
- 与当前 Palworld 版本匹配的 UE4SS。
- 专用服务器还需要在 `PalWorldSettings.ini` 设置
  `RESTAPIEnabled=True`、`RESTAPIPort=8212` 和 `AdminPassword`。
- 防火墙不得把 `8212` 或 `8213` 直接暴露到公网。

## 安装

1. 完全停止游戏客户端或专用服务器。
2. 安装或解压 UE4SS 到游戏可执行文件所在目录：
   - Windows 客户端：`<Palworld>\Pal\Binaries\Win64`
   - Windows 专用服务器：`<PalServer>\Pal\Binaries\Win64`
3. 找到 UE4SS 的 `Mods` 目录。它通常位于以下其中一个位置：
   - `Pal\Binaries\Win64\ue4ss\Mods`
   - `Pal\Binaries\Win64\Mods`
4. 把压缩包中的 `PalEditorBridge` 文件夹复制到该 `Mods` 目录。
5. 如果该 UE4SS 安装使用 `mods.txt`，加入：

   ```text
   PalEditorBridge : 1
   ```

6. 启动服务器，在服务器本机执行：

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8213/v1/health
   ```

   专服返回的 `bridgeVersion` 应为 `0.6.0`。客户端使用动态回环端口，
   无需手工探测端口。

## EXE 连接

### 单机或联机房主

1. 给 Steam 游戏客户端安装本模组并启动游戏。
2. 进入单机世界，或者由当前客户端创建联机世界并成为房主。
3. 在编辑器选择“实时管理”，点击“连接本机游戏”。

模组会使用 Windows DPAPI 为当前进程登记一次性本机凭据。EXE 会核对
进程 ID、启动时间和游戏路径，不需要输入管理员密码。加入其他房主的普通
联机客户端没有服务器权威，会被明确拒绝。

### 专用服务器

服务器与 EXE 在同一台电脑时，地址填写：

```text
http://127.0.0.1:8213
```

管理员密码填写服务器配置中的 `AdminPassword`，输入后会为当前 Windows
账户安全保存。

远程连接必须在服务器同机配置 HTTPS 反向代理，只把 HTTPS 代理到
`127.0.0.1:8213`。不要直接开放 `8212` 或 `8213`。

## 能力说明

- `player.list`：模组在游戏线程直接读取在线 `PalPlayerState`，不调用
  REST 玩家列表。
- `guild.list`：直接枚举运行中的游戏当前已加载公会，并合并在线成员；
  它不是离线存档中的完整历史公会数据库。
- `map.read`：在游戏线程读取在线玩家 Pawn 的世界坐标，并与运行时公会归属
  一起返回给实时地图；单个玩家没有可用 Pawn 时只会标记该位置不可用。
- `player.details`：仅在管理员选中在线玩家后读取玩家等级、经验等可解析字段。
- `inventory.read`：仅在管理员打开背包标签时，通过游戏反射枚举实际背包类型和
  物品槽，不使用固定偏移。
- `pal.list`：仅在管理员打开帕鲁标签时分页读取所选在线玩家的帕鲁箱、帕鲁详情、
  词条、个体值和强化字段；默认每次最多读取 12 个槽位。无法解析的条目会明确
  显示为部分数据，不会猜测字段。
- `inventory.grant`：给在线玩家添加物品或装备。
- `player.experience.add`：给在线玩家添加经验。
- `pal.grant`：通过服务器权威角色管理器给在线玩家添加帕鲁；支持最多 4 个
  被动技能 ID，以及可持久化的生命、远程攻击、防御个体值、浓缩等级和生命、
  攻击、防御、工作速度强化。
- `world.save`：调用游戏正常保存接口。

当前游戏版本把 `Talent_Melee` 标记为 `Transient`，不会写入存档，因此模组会
明确拒绝近战个体值，避免表面成功但重启后丢失。`pal.grant` 成功响应表示服务
器权威角色管理器已经接受请求并创建 Handle；响应中的 `effectVerified` 与
`persistenceVerified` 仍为 `false`，不能因为后续客户端请求超时就自动重试。

模组会检查当前游戏反射函数签名。某项能力不匹配当前游戏版本时，EXE 不会
显示对应操作，避免按旧版函数盲目写入。

单机与房主模式的真实游戏效果、复制和退出重进后的持久化需要分别验证；
仅成功构建 DLL 不代表这些运行时验证已经完成。
