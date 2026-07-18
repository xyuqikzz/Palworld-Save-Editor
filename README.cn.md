# Palworld-Save-Editor

<p align="center">
  <img src="icon.png" alt="Palworld-Save-Editor 图标" width="144">
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="README.md">English</a>
</p>

面向《幻兽帕鲁》Steam 存档的本地编辑器，提供桌面 GUI、Web UI 和交互式 CLI。本项目基于 [KrisCris/Palworld-Pal-Editor](https://github.com/KrisCris/Palworld-Pal-Editor) 二次开发，并继续使用 GPL-3.0 许可证。

> [!WARNING]
> 修改前请退出游戏或停止服务器，并手动备份整个世界存档目录。程序会在写入时创建备份，但自动备份不能代替你自己的离线副本。

## 支持范围

- 目前只直接支持 Steam 格式存档；Xbox Game Pass 存档需先转换为 Steam 格式。
- 当前数据与兼容性基线面向 Palworld 1.0 / Steam build 24088745。
- 未知版本或未验证的数据布局会按能力门控处理；请勿强行写入不受支持的字段。
- 本项目与 Pocketpair 无隶属或官方合作关系。

Steam 本地存档通常位于：

```text
%LOCALAPPDATA%\Pal\Saved\SaveGames\<Steam ID>\<世界 ID>
```

选择包含 `Level.sav` 和 `Players/` 的完整世界目录，不要只选择单个 `.sav` 文件。

## 主要功能

- 浏览玩家、帕鲁、世界容器和物品目录。
- 修改玩家名称、等级、科技和玩家背包。
- 修改帕鲁种类、特殊形态、昵称、性别、等级、个体值、浓缩、魂强化、工作适应性、主动技能和被动技能。
- 新增、复制、删除和跨容器整理帕鲁；危险操作提供预览和引用检查。
- 编辑物品数量、物品栏布局和已支持的动态物品属性。
- 提供批量编辑、预设预览/应用、待保存变更统计和显式保存。
- 写入采用临时文件、验证、备份和替换流程，失败时保留恢复信息。
- 界面支持 English、日本語、简体中文和 Français。

## 安装与运行

### 使用发布版本

从 [GitHub Releases](https://github.com/xyuqikzz/Palworld-Save-Editor/releases) 下载对应平台的压缩包或可执行文件，解压后直接运行。

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
| `--lang en|ja|zh-CN|fr` | 界面语言 |
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
