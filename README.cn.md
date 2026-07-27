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

面向《幻兽帕鲁》的本地工具：离线编辑 Steam 与 Xbox Game Pass/WGS 存档，并为受支持的 Windows Steam 游戏和专用服务器提供独立、按能力门控的实时管理入口。程序提供桌面 GUI、Web UI 和交互式 CLI。本项目基于 [KrisCris/Palworld-Pal-Editor](https://github.com/KrisCris/Palworld-Pal-Editor) 二次开发，并继续使用 GPL-3.0 许可证。

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

- 直接支持 Steam 格式目录和用户选择的 Xbox Game Pass WGS 文件夹。Game Pass 保存目标锁定为打开时的原槽位，并会先在 WGS 外创建已验证备份。
- 离线存档编辑与实时管理是两个独立流程。实时管理目前属于 Windows Beta，需要通过 UE4SS 在 Steam 客户端或 Windows 专用服务器安装 PalEditorBridge；单人游戏或联机合作只能由主机运行，加入其他主机的客户端会被拒绝。
- synthetic fixture 与一份经用户授权后复制到临时目录的真实 WGS 样本已完成打开、编辑、提交和重新打开测试；真实游戏加载与 Xbox 云同步尚未验证。
- 打包 EXE 已连接并显示本地 Windows Steam 单人游戏的运行时数据。每条实时命令仍需分别验证游戏内效果、客户端同步、保存、重启和重新加载；仅收到成功协议响应并不足以证明功能有效。
- 当前数据与兼容性基线面向 Palworld 1.0 / Steam build 24088745。
- 未知版本或未验证的数据布局会按能力门控处理；请勿强行写入不受支持的字段。
- 本项目与 Pocketpair 无隶属或官方合作关系。

Steam 本地存档通常位于：

```text
%LOCALAPPDATA%\Pal\Saved\SaveGames\<Steam ID>\<世界 ID>
```

选择包含 `Level.sav` 和 `Players/` 的完整世界目录，不要只选择单个 `.sav` 文件。

Game Pass 使用前请完全退出 Palworld 并等待本地同步，再选择 WGS 根目录或包含 `containers.index` 的用户目录，读取槽位后明确选择要打开的世界。本地事务成功不代表 Xbox 云同步已经验证。

## 主要功能

- 打开只读世界总览，查看玩家、帕鲁、种类、据点、公会、远征、竞技场、健康状态和结构引用诊断。
- 浏览玩家、帕鲁、公会、据点、世界容器、物品和最后保存的地图位置。
- 修改玩家名称、等级、科技点、属性、任务和受支持的背包。
- 修改物品数量和受支持的动态属性；复制、移动、替换或清空格子；只扩容已验证的普通背包和公会仓库，不支持缩容。
- 按游戏 build 24088745 的 NPC 基线查看世界内竞技场排行榜，可修改玩家 RP、为缺失玩家明确创建已验证的 `ArenaRankPoint` 字段，或重置已有且受支持的玩家记录。
- 修改帕鲁种类、特殊形态、昵称、性别、信赖度、等级、个体值、浓缩、魂强化、工作适应性、主动技能、被动技能、自定义/模组被动条目和可复用预设。
- 新增、复制、删除和跨容器整理帕鲁；危险操作提供预览和引用检查。
- 修改受支持的公会名称，只增加已验证的帕鲁终端等级与公会仓库容量，并查看据点、成员、工作帕鲁、技能和健康状态。
- 使用内置大世界与世界树地图查看玩家、公会据点和已验证传送点；解锁受支持的玩家传送点，或明确清除、恢复 `LocalData.sav` 的战争迷雾遮罩。
- 查看远征分配，快速完成受支持的远征并交由游戏正常结算奖励，释放被无效远征锁定的帕鲁，以及执行原子化帕鲁维护操作。
- 通过预览令牌和明确的待保存变更编辑受支持的任务进度。
- 使用 Monaco 高级 JSON 编辑器修改 `Level.sav` 与 `Players/*.sav`；程序只检查 JSON 语法和受支持的文档结构，错误字段值仍可能损坏存档。
- 通过 PalEditorBridge 查看桥接能力声明的在线玩家、公会、背包、帕鲁和地图数据，并且只显示当前桥接明确支持的操作。
- 查看绑定会话修订的待保存变更，并通过临时文件、验证、已验证备份、冲突检测、替换和重新打开检查进行显式保存；失败时保留恢复信息。
- 界面支持 English、Français、日本語、한국어 和简体中文。

## 安装与运行

### 使用发布版本

从 [GitHub Releases](https://github.com/xyuqikzz/Palworld-Save-Editor/releases) 下载对应平台的压缩包或可执行文件，解压后直接运行。

每个版本的新增功能、问题修复和其他变更仅在 GitHub Releases 中记录，不在 README 中重复维护。

### Windows 实时管理

实时管理与离线存档编辑互相独立，并且必须使用 Windows 桌面 EXE：

1. 在 Steam 客户端或 Windows 专用服务器的 `Win64` 目录安装与当前 Palworld 版本兼容的 UE4SS。
2. 在来源选择页打开“实时管理”，下载程序内置的 PalEditorBridge 压缩包，并将其中完整目录复制到 UE4SS 的 `Mods` 目录。
3. 单人游戏或联机合作应在主机安装；专用服务器还需在 `PalWorldSettings.ini` 中启用管理员 REST API 并配置管理员密码。
4. 完全重启游戏或服务器，从编辑器连接，并且只使用桥接明确声明的能力。

不要把 Palworld 或桥接端口直接暴露到公网。非 TLS 连接应仅绑定本机回环地址，远程访问应放在 HTTPS 反向代理之后。任何会改变状态的命令都应先在游戏内独立验证，再用于实际管理。

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
