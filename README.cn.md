# Palworld-Save-Editor

<p align="center">
  <img src="icon.png" alt="Palworld-Save-Editor 图标" width="144">
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="README.md">English</a>
</p>

<p align="center">
  <a href="https://github.com/xyuqikzz/Palworld-Save-Editor/releases/latest"><strong>下载</strong></a>
  · <a href="#主要功能">主要功能</a>
  · <a href="#安装与运行">安装与运行</a>
  · <a href="https://github.com/xyuqikzz/Palworld-Save-Editor/issues">反馈问题</a>
</p>

面向《幻兽帕鲁》的本地工具：离线编辑 Steam 与 Xbox Game Pass/WGS 存档，并为 Windows Steam、PC Game Pass/XGP 游戏客户端和专用服务器提供独立、按能力门控的实时管理入口。程序提供桌面 GUI、Web UI 和交互式 CLI。本项目基于 [KrisCris/Palworld-Pal-Editor](https://github.com/KrisCris/Palworld-Pal-Editor) 二次开发，并继续使用 GPL-3.0 许可证。

## 界面预览

<p align="center">
  <img src="docs/images/world-overview.png" alt="Windows 桌面程序中的只读世界存档总览" width="900">
</p>

| 存档来源选择 | 帕鲁编辑 |
| --- | --- |
| ![选择 Steam、Game Pass 或实时管理来源](docs/images/save-source-selection.png) | ![编辑帕鲁属性、强化、工作适应性和技能](docs/images/pal-editor.png) |

| 玩家与背包编辑 | 交互式世界地图 |
| --- | --- |
| ![编辑玩家资料和背包格子](docs/images/player-inventory-editor.png) | ![显示存档标记的幻兽帕鲁交互地图](docs/images/world-map.png) |

| 高级存档 JSON | 实时管理总览 |
| --- | --- |
| ![带风险提示的 Level 与玩家存档原始 JSON 编辑器](docs/images/raw-json-editor.png) | ![已连接本地游戏的运行时总览](docs/images/live-management-overview.png) |

| 实时背包 | 按能力门控的实时操作 |
| --- | --- |
| ![实时查看玩家背包与装备](docs/images/live-management-inventory.png) | ![实时物品、经验和帕鲁操作控件](docs/images/live-management-operations.png) |

截图来自 Windows 打包 EXE、本地测试存档和本地单人游戏桥接会话。界面中可见的操作仍受能力门控，不能据此认定所有命令都已验证游戏内效果、客户端同步或重启后持久化。

> [!WARNING]
> 修改前请退出游戏或停止服务器，并手动备份整个世界存档目录。程序会在写入时创建备份，但自动备份不能代替你自己的离线副本。

## 支持范围

- 直接支持 Steam 格式目录，以及用户选择的 Xbox Game Pass WGS 文件夹或 `containers.index` 文件。Game Pass 保存目标锁定为打开时的原槽位，会先在 WGS 外创建已验证备份，并将已修改条目标记为待同步，但不宣称 Xbox 云端上传已经成功。
- 双存档迁移可以读取 Steam 或 WGS 源存档，但当前流程只允许写入另一个独立的 Steam 格式目标。全量迁移与指定角色迁移均使用绑定分析结果的计划、已验证目标备份、暂存、冲突检查、原子替换、重新打开验证和已验证恢复；WGS 目标会被明确阻止。
- 离线存档编辑与实时管理是两个独立流程。Windows Steam、PC Game Pass/XGP 客户端和专用服务器通过 UE4SS 安装 PalEditorBridge；单人游戏与监听服务器仅允许具备服务器权威的房主连接，普通联机客户端会被拒绝。
- synthetic fixture 与一份经用户授权后复制到临时目录的真实 WGS 样本已完成打开、编辑、提交和重新打开测试；真实游戏加载与 Xbox 云同步尚未验证。
- 打包 EXE 已连接并显示本地 Windows Steam 单人游戏的运行时数据；XGP 已具备 WinGDK 进程发现和安装路径支持，但尚未完成真实 XGP 游戏效果、退出重进和 Xbox 云同步验证。每条实时命令仍需分别验证游戏内效果、客户端同步、保存、重启和重新加载；仅收到成功协议响应并不足以证明功能有效。
- 当前数据与兼容性基线面向 Palworld 1.0 / Steam build 24088745。
- 未知版本或未验证的数据布局会按能力门控处理；请勿强行写入不受支持的字段。
- 本项目与 Pocketpair 无隶属或官方合作关系。

Steam 本地存档通常位于：

```text
%LOCALAPPDATA%\Pal\Saved\SaveGames\<Steam ID>\<世界 ID>
```

桌面版请选择世界中的 `Level.sav`，编辑器会把它所在的完整目录作为 Steam 存档打开；Web 模式请选择同时包含 `Level.sav` 和 `Players/` 的完整世界目录。

Game Pass 使用前请完全退出 Palworld 并等待本地同步，再选择 WGS 根目录、包含 `containers.index` 的用户目录或直接选择 `containers.index`，读取槽位后明确选择要打开的世界。本地事务成功以及待同步元数据均不代表 Xbox 云同步已经验证。

## 主要功能

- 打开只读世界总览，查看玩家、帕鲁、种类、据点、公会、远征、竞技场、健康状态和结构引用诊断。
- 浏览玩家、帕鲁、公会、据点、世界容器、物品和最后保存的地图位置。
- 修改玩家名称、等级、科技点、属性、任务和受支持的背包。
- 修改物品数量和受支持的动态属性；复制、移动、替换或清空格子；只扩容已验证的普通背包和公会仓库，不支持缩容。
- 查看和编辑所选公会据点中已验证的持久物品仓储；仓储映射不完整或有歧义时保持只读。
- 按游戏 build 24088745 的 NPC 基线查看世界内竞技场排行榜，可修改玩家 RP、为缺失玩家明确创建已验证的 `ArenaRankPoint` 字段，或重置已有且受支持的玩家记录。
- 修改帕鲁种类、特殊形态、昵称、性别、信赖度、等级、个体值、浓缩、魂强化、工作适应性、主动技能、被动技能、自定义/模组被动条目和可复用预设。魂强化保留存档等级显示，同时显示“等级 × 3%”的游戏加成；正常编辑上限为等级 20 / 60%，更高值仅在无限制模式提供。
- 新增、复制、删除和跨容器整理帕鲁；危险操作提供预览和引用检查；玩家所属帕鲁可按队伍、帕鲁箱和其他位置分组折叠，并按容器、图鉴或等级排序。
- 修改受支持的公会名称，按职位查看成员，在已知结构上安全转移会长，只增加已验证的帕鲁终端等级与公会仓库容量，并查看据点、工作帕鲁、技能和健康状态。
- 分析两个独立存档，将完整世界或指定角色迁移到 Steam 格式目标，包括受支持的玩家文件、背包、队伍/帕鲁箱和次元帕鲁仓库；遇到未知身份、不透明引用、版本不一致或源/目标变化时安全拒绝。
- 仅当保存失败已证明“有效公会关联帕鲁缺少对应公会角色 handle”时，提供范围受限且受备份保护的自动修复；有歧义或混合结构损坏仍会阻止写入。
- 使用内置大世界与世界树地图查看玩家、公会据点和已验证传送点；解锁受支持的玩家传送点，或明确清除、恢复 `LocalData.sav` 的战争迷雾遮罩。
- 查看远征分配，快速完成受支持的远征并交由游戏正常结算奖励，释放被无效远征锁定的帕鲁，以及执行原子化帕鲁维护操作。
- 通过预览令牌和明确的待保存变更编辑受支持的任务进度。
- 使用 Monaco 高级 JSON 编辑器修改 `Level.sav` 与 `Players/*.sav`；程序只检查 JSON 语法和受支持的文档结构，错误字段值仍可能损坏存档。
- 通过 PalEditorBridge 先显示在线玩家，再在后台获取短期只读玩家快照，并按 `PlayerUId` 合并全部存档玩家；可筛选全部、在线和离线玩家，并按选中玩家懒加载资料、背包、科技、任务、属性、地图进度、队伍帕鲁和帕鲁箱。
- 在实时管理的“地图”中合并在线玩家的权威 Pawn 坐标与离线玩家最近存档坐标；每个标记都会显示在线或离线状态，运行时等级无效时会保留快照中的有效等级。
- 专用服务器会在选中玩家的等级旁提供踢出、封禁和解封操作；这些管理员操作不发送可选理由、全部需要二次确认，并且只在桥接已验证 REST `userId` 时开放。本次连接中被封禁的玩家仍可直接解封。
- 只对在线玩家开放当前游戏版本已验证的权威操作，包括发放现有物品、增加经验和发放帕鲁；实时发放帕鲁时，表单与桥接层都会执行等级 20 / 60% 的正常魂强化上限。名称、槽位覆盖、任务/科技/传送点和现有帕鲁字段等未验证入口会按目标能力明确禁用。
- 实时修改不直接改写运行中的 `.sav` 文件，不提供回滚、撤销、修改前备份或离线待执行队列；成功修改会在 2 秒窗口内合并正常世界保存，连续编辑最长 10 秒触发一次保存，并显示 `clean`、`dirty`、`saving` 或 `failed` 持久化状态。
- 查看绑定会话修订的待保存变更，并通过临时文件、验证、已验证备份、冲突检测、替换和重新打开检查进行显式保存；失败时保留恢复信息。Windows 下的存档暂存、Steam 备份和重新打开验证支持扩展长度路径；若路径仍超过平台限制，程序会在写入存档数据前停止并显示明确的处理建议。
- 界面支持 English、Français、日本語、한국어 和简体中文。

## 安装与运行

### 使用发布版本

从 [GitHub Releases](https://github.com/xyuqikzz/Palworld-Save-Editor/releases) 下载对应平台的压缩包或可执行文件，解压后直接运行。

每个版本的新增功能、问题修复和其他变更仅在 GitHub Releases 中记录，不在 README 中重复维护。

### Windows 实时管理

实时存档管理与离线存档编辑互相独立，并且必须使用 Windows 桌面 EXE。Steam、PC Game Pass/XGP 客户端和专用服务器分别安装到对应的 UE4SS 目录：

1. 安装与当前 Palworld 版本兼容的 UE4SS：Steam 客户端和 Windows 专用服务器使用 `Win64`，PC Game Pass/XGP 客户端使用 `Content\Pal\Binaries\WinGDK`。
2. 在来源选择页打开“实时管理”，下载程序内置的 PalEditorBridge 压缩包，并将其中完整目录复制到 UE4SS 的 `Mods` 目录。
3. 在 `PalWorldSettings.ini` 中启用管理员 REST API 并配置管理员密码。
4. 完全重启游戏或服务器，从编辑器连接，并且只使用桥接明确声明的能力。

不要把 Palworld 或桥接端口直接暴露到公网。非 TLS 连接应仅绑定本机回环地址，远程访问应放在 HTTPS 反向代理之后。XGP 实时修改通过游戏的正常权威与保存路径完成，不直接改写运行中的 WGS 容器。任何会改变状态的命令都应分别在 Steam 与 XGP 游戏内验证，再用于实际管理。

### 从源码运行

需要 Python 3.11+ 和当前 LTS 版本的 Node.js。

```powershell
git clone https://github.com/xyuqikzz/Palworld-Save-Editor.git
cd Palworld-Save-Editor
.\setup_and_run.ps1 --lang zh-CN --mode gui
```

Linux/macOS：

```bash
git clone https://github.com/xyuqikzz/Palworld-Save-Editor.git
cd Palworld-Save-Editor
chmod +x setup_and_run.sh
./setup_and_run.sh --lang zh-CN --mode web
```

脚本会安装前后端依赖、构建 Web UI、创建本地虚拟环境并启动应用。

### Docker

复制并修改示例 Compose 文件中的端口、密码和存档挂载路径：

```bash
cp docker/sample-docker-compose.yml docker-compose.yml
docker compose up -d
```

Web 模式不要无密码暴露到公网。默认示例会把宿主机 `8080` 映射到容器；实际监听端口以 Compose 文件为准。

### 命令行参数

```bash
python -m palworld_pal_editor --help
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--lang en|fr|ja|ko|zh-CN` | 界面语言 |
| `--path <目录>` | 包含 `Level.sav` 的世界目录 |
| `--mode cli|gui|web` | 运行模式 |
| `--port <端口>` | Web UI 监听端口 |
| `--password <密码>` | Web UI 登录密码 |
| `--nocli` | GUI/Web 模式下不启动交互式 CLI |

运行配置写入程序目录旁的 `config.json`，该文件包含本机路径和 Web 配置，已被 Git 忽略。

## 开发

后端使用 Python 3.11、Flask 和内置的 `palworld_save_tools`；前端使用 Vue 3、Pinia 和 Vite。

```powershell
# Python 测试
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
.\venv\Scripts\python.exe -m pytest -q

# 前端测试与生产构建
cd frontend\palworld-pal-editor-webui
npm ci
npm test
npm run build
```

真实存档测试不会读取或修改仓库里的二进制夹具。配置方法见 [`tests/fixtures/real_saves/README.md`](tests/fixtures/real_saves/README.md)，本地 `.sav`、`.gvas` 与 `manifest.local.json` 均已加入 `.gitignore`。

## 反馈与贡献

提交问题前请先搜索 [Issues](https://github.com/xyuqikzz/Palworld-Save-Editor/issues)，并附上编辑器版本、游戏版本、复现步骤和脱敏日志。存档可能包含玩家标识等隐私信息，公开上传前请先确认内容并做好脱敏。

代码贡献请从最新 `develop` 分支创建功能分支，并在 Pull Request 中说明改动范围和实际执行的验证。

## 许可与归属

项目整体按 [GNU GPL v3](LICENSE) 发布。二次开发说明见 [NOTICE.md](NOTICE.md)；内置或派生的第三方组件许可见 [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES)。

感谢上游项目作者、`palworld-save-tools`、PalEdit 及所有翻译和测试贡献者。本仓库保留相应的版权与许可声明。
