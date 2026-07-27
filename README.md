# Palworld-Save-Editor

<p align="center">
  <img src="icon.png" alt="Palworld-Save-Editor icon" width="144">
</p>

<p align="center">
  <a href="README.cn.md">简体中文</a> · <strong>English</strong>
</p>

<p align="center">
  <a href="https://github.com/xyuqikzz/Palworld-Save-Editor/releases/latest"><strong>Download</strong></a>
  · <a href="#features">Features</a>
  · <a href="#install-and-run">Install and run</a>
  · <a href="https://github.com/xyuqikzz/Palworld-Save-Editor/issues">Report an issue</a>
</p>

A local Palworld toolkit for offline Steam and Xbox Game Pass/WGS save editing, plus a separate capability-gated live management path for supported Windows Steam games and dedicated servers. It provides a desktop GUI, Web UI, and interactive CLI. This project is a modified version based on [KrisCris/Palworld-Pal-Editor](https://github.com/KrisCris/Palworld-Pal-Editor) and remains licensed under GPL-3.0.

## Screenshots

<p align="center">
  <img src="docs/images/world-overview.png" alt="Read-only Palworld world-save overview in the Windows desktop application" width="900">
</p>

| Save source selection | Pal editing |
| --- | --- |
| ![Steam, Game Pass, and live-management source selection](docs/images/save-source-selection.png) | ![Pal attributes, upgrades, work suitability, and skills editor](docs/images/pal-editor.png) |

| Player and inventory editing | Interactive world map |
| --- | --- |
| ![Player details and inventory slot editor](docs/images/player-inventory-editor.png) | ![Interactive Palworld map with save markers](docs/images/world-map.png) |

| Advanced save JSON | Live management overview |
| --- | --- |
| ![Risk-gated raw JSON editor for Level and player saves](docs/images/raw-json-editor.png) | ![Connected local-game runtime overview](docs/images/live-management-overview.png) |

| Live inventory | Capability-gated live operations |
| --- | --- |
| ![Live player inventory and equipment view](docs/images/live-management-inventory.png) | ![Live item, experience, and Pal operation controls](docs/images/live-management-operations.png) |

Screenshots show the packaged Windows EXE with a local test save and a local single-player bridge session. Visible operations remain capability-gated and are not proof that every command has been verified for gameplay effect, replication, or persistence.

> [!WARNING]
> Exit the game or stop the server and make an offline copy of the entire world save directory before editing. The application creates backups during writes, but automatic backups are not a substitute for your own copy.

## Support scope

- Steam-format directories and locally selected Xbox Game Pass WGS folders are supported directly. Game Pass writes are locked to the opened slot and create a verified backup outside WGS first.
- Offline save editing and live management are separate workflows. Live management is a Windows beta that requires PalEditorBridge through UE4SS on the Steam client or Windows dedicated server; in single-player or co-op, it must run on the host. A client joined to another host is rejected.
- Synthetic fixtures and a copied, user-authorized WGS sample have passed open, edit, commit, and reopen tests. Loading the result in the game and Xbox cloud synchronization have not been verified.
- The packaged EXE has connected to and displayed data from a local Windows Steam single-player session. Each live command still requires its own in-game effect, client replication, save, restart, and reload verification; a successful protocol response alone is not sufficient.
- The current data and compatibility baseline targets Palworld 1.0 / Steam build 24088745.
- Unknown versions and unverified layouts are capability-gated. Do not force unsupported fields to be written.
- This is an unofficial community project and is not affiliated with Pocketpair.

Steam saves are normally stored under:

```text
%LOCALAPPDATA%\Pal\Saved\SaveGames\<Steam ID>\<World ID>
```

Select the complete world directory containing `Level.sav` and `Players/`, not an individual `.sav` file.

For Game Pass, exit Palworld and wait for local synchronization, then choose either the WGS root or the user directory containing `containers.index`. Read the slots and explicitly select the world to open. A successful local transaction does not prove Xbox cloud synchronization.

## Features

- Open a read-only world overview with player, Pal, species, base, guild, expedition, arena, condition, and structural-reference diagnostics.
- Browse players, Pals, guilds, bases, world containers, items, and last-saved map locations.
- Edit player names, levels, technology points, attributes, missions, and supported inventories.
- Edit item quantities and supported dynamic attributes; copy, move, replace, or clear slots; expand verified ordinary backpacks and guild chests without shrinking them.
- Review the world-local arena leaderboard with the game build 24088745 NPC baseline, edit player RP, explicitly create a missing verified `ArenaRankPoint` field, or reset existing supported player records.
- Edit Pal species, variants, names, gender, trust, level, IVs, condensation, souls, work suitability, active skills, passive skills, custom/mod passive entries, and reusable presets.
- Add, duplicate, delete, and reorganize Pals across supported containers, with previews and reference checks for destructive operations.
- Rename supported guilds, increase verified Palbox levels and guild-chest capacities, and inspect bases, members, working Pals, skills, and conditions.
- Use the packaged open-world and World Tree maps to inspect players, guild bases, and verified fast-travel points; unlock supported player fast-travel flags, or explicitly clear or restore `LocalData.sav` fog-of-war masks.
- Review expedition assignments, quick-complete supported expeditions for normal in-game settlement, release Pals from invalid assignments, and run atomic Pal maintenance operations.
- Edit supported mission progress through preview tokens and explicit pending changes.
- Use the advanced Monaco JSON editor for `Level.sav` and `Players/*.sav`; only JSON syntax and supported document structure are checked, so incorrect values can still corrupt a save.
- Connect through PalEditorBridge to inspect advertised live players, guilds, inventories, Pals, and map data, and expose only operations reported by the current bridge capabilities.
- Review revision-bound pending changes and save explicitly through temporary files, validation, verified backups, conflict detection, replacement, and reopen checks, preserving recovery information on failure.
- Use the UI in English, French, Japanese, Korean, or Simplified Chinese.

## Install and run

### Release builds

Download the archive or executable for your platform from [GitHub Releases](https://github.com/xyuqikzz/Palworld-Save-Editor/releases), extract it, and run the application.

Version-specific new features, bug fixes, and other changes are documented in GitHub Releases instead of this README.

### Live management on Windows

Live management is separate from offline save editing and requires the Windows desktop EXE:

1. Install a UE4SS release compatible with the current Palworld version in the Steam client or Windows dedicated-server `Win64` directory.
2. On the source-selection screen, open **Live management**, download the bundled PalEditorBridge package, and copy its complete folder into the UE4SS `Mods` directory.
3. For single-player or co-op, install the mod on the host. For a dedicated server, also enable the administrator REST API and configure its password in `PalWorldSettings.ini`.
4. Fully restart the game or server, connect from the editor, and use only capabilities reported by the bridge.

Do not expose Palworld or bridge ports directly to the public internet. Keep non-TLS access on loopback and place remote access behind an HTTPS reverse proxy. Verify every state-changing command in the game before relying on it.

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
| `--lang en|fr|ja|ko|zh-CN` | UI language |
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
