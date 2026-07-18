# Palworld-Save-Editor

<p align="center">
  <img src="icon.png" alt="Palworld-Save-Editor icon" width="144">
</p>

<p align="center">
  <a href="README.cn.md">简体中文</a> · <strong>English</strong>
</p>

A local editor for Palworld Steam saves with a desktop GUI, Web UI, and interactive CLI. This project is a modified version based on [KrisCris/Palworld-Pal-Editor](https://github.com/KrisCris/Palworld-Pal-Editor) and remains licensed under GPL-3.0.

> [!WARNING]
> Exit the game or stop the server and make an offline copy of the entire world save directory before editing. The application creates backups during writes, but automatic backups are not a substitute for your own copy.

## Support scope

- Steam-format saves are supported directly. Xbox Game Pass saves must first be converted to Steam format.
- The current data and compatibility baseline targets Palworld 1.0 / Steam build 24088745.
- Unknown versions and unverified layouts are capability-gated. Do not force unsupported fields to be written.
- This is an unofficial community project and is not affiliated with Pocketpair.

Steam saves are normally stored under:

```text
%LOCALAPPDATA%\Pal\Saved\SaveGames\<Steam ID>\<World ID>
```

Select the complete world directory containing `Level.sav` and `Players/`, not an individual `.sav` file.

## Features

- Browse players, Pals, world containers, and the item catalog.
- Edit player names, levels, technologies, and player inventories.
- Edit Pal species, variants, names, gender, level, IVs, condensation, souls, work suitability, active skills, and passive skills.
- Add, duplicate, delete, and reorganize Pals across supported containers, with previews and reference checks for destructive operations.
- Edit item quantities, inventory layouts, and supported dynamic item attributes.
- Preview and apply batch operations and presets, review pending changes, and save explicitly.
- Write through temporary files, validation, backup creation, and replacement, preserving recovery information on failure.
- Use the UI in English, Japanese, Simplified Chinese, or French.

## Install and run

### Release builds

Download the archive or executable for your platform from [GitHub Releases](https://github.com/xyuqikzz/Palworld-Save-Editor/releases), extract it, and run the application.

### Run from source

Python 3.11+ and a current Node.js LTS release are required.

```powershell
git clone https://github.com/xyuqikzz/Palworld-Save-Editor.git
cd Palworld-Save-Editor
.\setup_and_run.ps1 --lang en --mode gui
```

Linux/macOS:

```bash
git clone https://github.com/xyuqikzz/Palworld-Save-Editor.git
cd Palworld-Save-Editor
chmod +x setup_and_run.sh
./setup_and_run.sh --lang en --mode web
```

The setup scripts install the frontend and backend dependencies, build the Web UI, create a local virtual environment, and launch the application.

### Docker

Copy the sample Compose file, then update its ports, password, and save-directory mount:

```bash
cp docker/sample-docker-compose.yml docker-compose.yml
docker compose up -d
```

Never expose Web mode to the public internet without a strong password. The sample maps host port `8080`; consult the Compose file for the actual container port.

### Command-line options

```bash
python -m palworld_pal_editor --help
```

Common options:

| Option | Description |
| --- | --- |
| `--lang en|ja|zh-CN|fr` | UI language |
| `--path <directory>` | World directory containing `Level.sav` |
| `--mode cli|gui|web` | Runtime mode |
| `--port <port>` | Web UI listening port |
| `--password <password>` | Web UI login password |
| `--nocli` | Disable the interactive CLI in GUI/Web mode |

Runtime settings are written to `config.json` beside the application. The file can contain local paths and Web settings and is ignored by Git.

## Development

The backend uses Python 3.11, Flask, and the bundled `palworld_save_tools`; the frontend uses Vue 3, Pinia, and Vite.

```powershell
# Python tests
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
.\venv\Scripts\python.exe -m pytest -q

# Frontend tests and production build
cd frontend\palworld-pal-editor-webui
npm ci
npm test
npm run build
```

Real-save tests never use committed binary fixtures or modify their source files. See [`tests/fixtures/real_saves/README.md`](tests/fixtures/real_saves/README.md) for local setup. Local `.sav`, `.gvas`, and `manifest.local.json` files are ignored by Git.

## Issues and contributions

Search [existing issues](https://github.com/xyuqikzz/Palworld-Save-Editor/issues) before reporting a problem. Include the editor version, game version, reproduction steps, and sanitized logs. Save files may contain player identifiers and other private data; inspect and sanitize them before uploading publicly.

For code contributions, branch from the latest `develop` branch and describe the change scope and commands actually used for verification in the pull request.

## License and attribution

The project is distributed under the [GNU GPL v3](LICENSE). See [NOTICE.md](NOTICE.md) for the derivative-work notice and [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES) for bundled or derived third-party components.

Thanks to the upstream maintainers, `palworld-save-tools`, PalEdit, and all translation and testing contributors. Their applicable copyright and license notices are preserved in this repository.
