[url=https://github.com/xyuqikzz/Palworld-Save-Editor][b]GitHub / Source Code: https://github.com/xyuqikzz/Palworld-Save-Editor[/b][/url]

[center][size=6][b]Palworld Save Editor[/b][/size]

[b]Standalone • Local • Offline[/b]

Steam • Dedicated Server • Xbox Game Pass / WGS Beta

Offline save editing • Separate Windows live management beta[/center]

[size=5][b]Description[/b][/size]

Palworld Save Editor is a local toolkit for inspecting and editing supported Palworld save data. It provides a desktop GUI, Web UI, and interactive CLI for players, Pals, guilds, inventories, missions, expeditions, maps, and other verified save structures.

Offline editing does not require an in-game mod or mod loader. A separate capability-gated live management path is available for Windows Steam and PC Game Pass/XGP clients and Windows dedicated servers through PalEditorBridge and UE4SS.

This project is based on KrisCris/Palworld-Pal-Editor and includes a redesigned multilingual interface, current game data, safer transactional save handling, expanded editing tools, and clearer workflows for large worlds.

[quote][b]Important workflow boundary[/b]

Offline save editing and live management are separate workflows. Never edit an offline save while Palworld or its dedicated server is still using it. Live management must go through PalEditorBridge on the authoritative host or server and only exposes capabilities advertised by the connected bridge.[/quote]

[size=5][b]Supported Save Sources[/b][/size]

[size=4][b]Steam and Dedicated Server Saves[/b][/size]

[list]
[*]Local Steam world saves
[*]Compatible Steam-format dedicated server world saves
[*]Complete world directories containing [b]Level.sav[/b] and the [b]Players[/b] directory
[/list]

Default Steam save location:

[code]%LOCALAPPDATA%\Pal\Saved\SaveGames\<Steam ID>\<World ID>[/code]

In the desktop app, choose the world's [b]Level.sav[/b]; the editor opens its containing directory as the complete Steam save. In Web mode, select the complete world directory.

[size=4][b]Xbox Game Pass / WGS Beta[/b][/size]

The editor can discover, open, edit, and write back a locally selected Xbox Game Pass/WGS world.

[list]
[*]In the desktop system picker, select the intended Xbox user folder or a folder inside its WGS container tree; the editor resolves it back to the owning [b]containers.index[/b]
[*]In the Web or in-app browser, select a WGS root, an Xbox user directory containing [b]containers.index[/b], or [b]containers.index[/b] itself
[*]Read the available local world slots and explicitly choose the intended world
[*]Keep saving locked to the exact WGS slot opened at the start of the session
[*]Create and verify a complete backup outside WGS before writeback
[*]Detect source changes, stage and validate the transaction, preserve recovery details on failure, and reopen the final WGS result
[*]Clear the previous cloud revision identifier and mark changed entries as pending synchronization without claiming that Xbox cloud upload succeeded
[*]Export a separate Steam-format copy without treating that export as WGS writeback
[/list]

[b]Important:[/b] Local WGS transactions have passed fixture tests and copied-sample round trips. Loading an edited result in the Game Pass game and Xbox cloud synchronization have not been fully verified.

Close Palworld completely and wait for local Xbox synchronization activity to stop before opening or saving a WGS world.

[size=4][b]Two-save Migration[/b][/size]

The editor can analyze two independent saves and migrate either the complete source world or selected source characters into a separate Steam-format target.

[list]
[*]Read a Steam or WGS source through the existing normalized storage adapters
[*]Keep full migration and selected-character migration as explicit, separate modes
[*]Migrate supported player files, inventories, Party and Palbox data, and dimensional Pal storage
[*]Bind execution to the analyzed source and target snapshots
[*]Create and verify a target backup, stage the complete active tree, detect conflicts, replace atomically, reopen the result, and verify recovery after failure
[*]Reject unknown identities, opaque references, version mismatches, duplicate mappings, and changed sources or targets
[/list]

The current migration workflow does not write results into a WGS target. WGS targets are explicitly blocked because safe complete logical-file replacement is not yet supported. Automated validation covers fixtures and offline reopen checks; real game loading, restart persistence, and Xbox cloud synchronization remain unverified.

[size=4][b]Windows Live Management Beta[/b][/size]

Live management is a separate Windows workflow. Steam and PC Game Pass/XGP clients may connect only while running an authoritative single-player world or listen-server host; joined clients are rejected. Dedicated servers remain the fully documented server-management target.

[list]
[*]Connect through PalEditorBridge installed with UE4SS on the authoritative host or server
[*]Discover both Steam [b]Palworld-Win64-Shipping.exe[/b] and PC Game Pass/XGP [b]Palworld-WinGDK-Shipping.exe[/b] local Bridge instances
[*]Show a localized recovery message when automatic local connection cannot find the running game or Bridge
[*]Show online players first, then merge all saved players from a short-lived read-only snapshot by PlayerUId
[*]Filter all, online, and offline players and lazily inspect profile, inventory, technology, missions, attributes, map progress, Party, and Palbox data
[*]Combine authoritative online Pawn positions with last-saved offline player positions on the Map, label every marker as online or offline, and keep the saved level when a runtime level is invalid
[*]Place dedicated-server kick, ban, and unban controls beside the selected player's level; all three omit the optional reason, require a second confirmation, and require a REST-verified userId
[*]Show only target-level operations reported by the connected bridge; the verified live mutations are granting an existing item, adding experience, and granting a Pal to an online player
[*]Show stored Soul ranks with their rank × 3% game bonus and enforce the normal rank 20 / 60% limit in both the live Pal grant form and Bridge
[*]Keep unverified identity, slot replacement, mission, technology, fast-travel, and existing-Pal mutation controls disabled
[*]Use authenticated, revision-bound, idempotent command handling
[*]Coalesce normal world saves after two seconds and force one within ten seconds of continuous editing
[/list]

The snapshot is not a backup: it keeps at most two captures for ten minutes and never writes the active save files. Live management has no rollback, undo, pre-change backup, or deferred offline command queue. A save failure leaves already-applied runtime changes visible and marks them as not yet persisted.

Every state-changing command still requires its own in-game effect, replication, save, restart, and reload verification. XGP also requires separate Xbox cloud synchronization verification. A successful protocol response alone is not proof of gameplay effect, persistence, or cloud synchronization.

[size=5][b]Main Features[/b][/size]

[size=4][b]World Overview, Players, and Guilds[/b][/size]

[list]
[*]Open a read-only world overview with player, Pal, species, base, guild, expedition, arena, condition, and structural-reference diagnostics
[*]Browse local save sources through system pickers where available or a root-aware in-app browser with search, natural sorting, modified times, complete-save markers, and offline file-type icons
[*]Browse players through guilds, bases, members, working Pals, and unmatched records
[*]Edit supported player names, levels, technology points, attributes, missions, inventories, and equipment, including Remedy and Elixir bonus ranks capped by each attribute's official combined total
[*]Review the world-local arena leaderboard, edit supported player RP records, explicitly create a missing verified RP field, or reset supported player entries
[*]Rename supported guilds, inspect role-sorted members, and safely transfer Guild Master ownership on known layouts
[*]Inspect and edit verified persistent item storage for a selected guild base; incomplete or ambiguous mappings remain read-only
[*]Offer a narrowly scoped, backup-protected repair only for proven missing guild character handles; ambiguous or mixed structural damage remains blocked
[*]Edit verified Palbox levels within the official 1–35 range, with a Palbox-Pal warning before confirming reductions, and expand guild-chest capacities without shrinking existing structures
[/list]

[size=4][b]Pal Editing[/b][/size]

[list]
[*]Add, duplicate, delete, move, and reorganize Pals across supported containers
[*]Edit species, supported variants, nickname, gender, trust, level, and experience
[*]Edit IVs, condensation, Soul upgrades, work suitability, active skills, and passive skills; Soul controls show both stored rank and the rank × 3% game bonus, with a normal rank 20 / 60% cap
[*]Manage supported custom or mod passive entries
[*]Create, edit, pin, reuse, and quickly apply passive-skill presets
[*]Apply supported maximum Pal and work-suitability settings
[*]Heal or revive Pals and remove supported negative effects
[*]Preview destructive operations and check affected references before applying them
[*]Group player-owned Pals by Party, Palbox, and other locations with collapsible sections
[*]Sort and filter large Pal collections by container order, Paldeck order, level, species, element, gender, boss/Lucky state, and location
[/list]

[size=4][b]Inventories and Batch Tools[/b][/size]

[list]
[*]Edit supported item quantities, inventory slots, and dynamic item attributes
[*]Copy, move, replace, clear, and arrange supported slots
[*]Expand verified ordinary backpacks and guild chests without shrinking them
[*]Import and export supported inventory and Pal presets
[*]Preview multi-target changes before applying them
[*]Apply supported batch operations atomically
[*]Review pending changes before saving
[/list]

[size=4][b]Missions and Expeditions[/b][/size]

[list]
[*]Search and filter supported main, side, hidden, and test missions
[*]Preview mission changes before adding them to pending changes
[*]Complete, reset, or restart supported mission progress
[*]Apply supported mission operations in atomic batches
[*]Validate expedition assignments against expedition objects stored in the world
[*]Identify valid, invalid, and unknown expedition references
[*]Release Pals from supported expedition assignments
[*]Quick-complete supported active expedition timers so the game can perform normal settlement after loading
[/list]

[b]Mission warning:[/b] Editing mission completion data does not grant or revoke rewards, replay story events, trigger achievements, or automatically roll back related world state.

[size=4][b]Maps and World Progress[/b][/size]

[list]
[*]Use packaged open-world and World Tree maps
[*]Inspect saved player locations, guild bases, and verified fast-travel points
[*]Unlock supported player fast-travel flags
[*]Explicitly clear or restore supported [b]LocalData.sav[/b] fog-of-war masks
[*]Keep fast-travel flags, fog of war, missions, and unrelated world progress as separate operations
[/list]

[size=4][b]Advanced JSON Editing[/b][/size]

The advanced Monaco JSON editor can open [b]Level.sav[/b] and [b]Players/*.sav[/b] documents in the current session. It checks JSON syntax and supported document structure, but it cannot prove that arbitrary values are valid for the game.

[b]Use this feature only if you understand the save structure.[/b] Incorrect values can still corrupt a save.

[size=4][b]Safety and Save Integrity[/b][/size]

[list]
[*]Bind edits to the opened save session and its expected revision
[*]Stage writes through temporary files before replacing save data
[*]Validate and reopen supported saves before completing a transaction
[*]Create verified backups for supported save operations
[*]Support extended-length Windows paths during save staging, Steam backup creation, and reopen verification; paths that still exceed platform limits are blocked before save data is written and report a specific recovery action
[*]Detect source changes and reject stale writes
[*]Preserve recovery information when a write fails
[*]Keep WGS writes locked to the original selected slot
[*]Keep migration execution bound to analyzed source and target snapshots and block WGS migration targets
[*]Reject unsupported or unknown structures instead of silently guessing
[/list]

[size=4][b]Languages and Application Modes[/b][/size]

[b]Interface languages[/b]

[list]
[*]English
[*]French
[*]Japanese
[*]Korean
[*]Simplified Chinese
[/list]

Confirmations, prompts, success messages, and errors use focus-managed in-app dialogs in every supported interface language, with technical details available when needed.

[b]Application modes[/b]

[list]
[*]Desktop GUI
[*]Web UI
[*]Interactive CLI
[*]Docker deployment for advanced users
[/list]

[size=5][b]Installation[/b][/size]

[size=4][b]Offline Save Editing[/b][/size]

[list=1]
[*]Download the latest file from the Nexus Files tab.
[*]Extract the archive if required.
[*]Close Palworld completely or stop the dedicated server.
[*]Create your own offline backup of the complete world save directory.
[*]Run the included application.
[*]Choose Steam or Xbox Game Pass/WGS as the save source.
[*]Select the complete Steam-format world directory or explicitly select a discovered WGS world slot.
[*]Load the save, review your changes, and save.
[*]Start the game or server and verify players, Pals, containers, missions, maps, and bases before continuing normal play.
[/list]

No Python installation is required when using the prebuilt Windows application.

[size=4][b]Live Management on Windows[/b][/size]

[list=1]
[*]Install a UE4SS release compatible with the current Palworld game: use [b]Win64[/b] for Steam clients and Windows dedicated servers, or [b]Content\Pal\Binaries\WinGDK[/b] for PC Game Pass/XGP clients.
[*]Open [b]Live management[/b] in the Windows desktop application and download the bundled PalEditorBridge package.
[*]Copy the complete PalEditorBridge folder into the UE4SS [b]Mods[/b] directory.
[*]Enable the dedicated-server administrator REST API and configure its password.
[*]Fully restart the game or server, connect from the editor, and use only the capabilities reported by the bridge.
[/list]

[b]Network safety:[/b] Do not expose Palworld or bridge ports directly to the public internet. Keep non-TLS bridge access on loopback and put remote access behind an HTTPS reverse proxy.

[size=5][b]Important Safety Information[/b][/size]

[list]
[*]Close Palworld before editing a local save.
[*]Stop the dedicated server before editing a server save.
[*]Wait for Xbox synchronization activity to stop before editing a WGS save.
[*]Back up the complete world save directory before making changes.
[*]Automatic backups are not a substitute for your own offline copy.
[*]Do not force unsupported fields, unknown layouts, or unverified game data to be written.
[*]Experimental or extreme values may produce unexpected game behavior.
[*]Load the edited world and verify the result before continuing normal play.
[/list]

[size=5][b]Requirements[/b][/size]

[list]
[*]A supported Steam save, compatible Steam-format server save, or locally available Xbox Game Pass/WGS save
[*]Write access to the selected save and backup locations
[*]No UE4SS or other mod loader for offline save editing
[*]UE4SS and the bundled PalEditorBridge for Windows live management
[/list]

[size=5][b]Known Limitations[/b][/size]

[list]
[*]Xbox cloud synchronization has not been verified.
[*]Real Game Pass in-game loading may behave differently from fixture or copied-sample round trips.
[*]Unknown game versions and unverified save layouts may be capability-gated or blocked for safety.
[*]A bridge command reported as completed is not automatically proven to have replicated, persisted, or produced the intended gameplay result.
[*]The full saved-player directory and read-only snapshot workflow is a Windows dedicated-server first-phase feature; other live instance modes are not release-supported in this phase.
[*]Offline players are read-only unless a future game build exposes a verified authoritative runtime write path.
[*]Mission edits do not reproduce game-side rewards, achievements, story triggers, or related world-state changes.
[*]The advanced JSON editor cannot validate arbitrary game values.
[*]Some experimental values may not be accepted by the game.
[/list]

[size=5][b]Credits and License[/b][/size]

Based on [url=https://github.com/KrisCris/Palworld-Pal-Editor]KrisCris/Palworld-Pal-Editor[/url].

Thanks to the original Palworld Pal Editor contributors, MagicBear, palworld-save-tools, PalEdit, translators, testers, and everyone who contributed to the related projects.

Japanese translation by Take-Me1010.

Developed by yuqikzz.

Licensed under the GNU General Public License.

[i]Palworld Save Editor is an unofficial community project and is not affiliated with Pocketpair.[/i]
