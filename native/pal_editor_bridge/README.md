# Pal Editor Bridge

`PalEditorBridge` is a headless UE4SS mod. It has no in-game UI. The desktop
Palworld Pal Editor connects to the bridge protocol and all gameplay mutations
are executed by an authoritative dedicated server, single-player world, or
multiplayer host.

## Implemented capabilities

The repository currently contains:

- the versioned bridge protocol and short-lived session-token implementation;
- administrator credential verification through the Palworld REST API on
  `127.0.0.1` for dedicated servers;
- per-process local credentials protected with Windows DPAPI, dynamic loopback
  ports, and automatic EXE discovery for Steam `Win64` and PC Game Pass
  `WinGDK` game clients;
- fail-closed runtime authority detection that exposes gameplay operations only
  for single-player and multiplayer-host instances;
- a UE4SS C++ mod lifecycle entry point with no ImGui registration;
- live server metadata, announcements, player kick/ban/unban, normal
  world-save requests, and save-before-shutdown scheduling through the
  official Palworld REST API;
- online-player listing on the game thread through
  `PalUtility:GetAllPlayerStates`; dedicated servers enrich matching runtime
  rows with the REST player `userId` required by moderation without exposing
  IP addresses;
- loaded-guild, selected-player profile, inventory-container, and paged Palbox
  snapshots read lazily on the game thread, without the REST player endpoint;
- dedicated-server read-only player snapshots that resolve the active world
  from the process directory and authenticated `worldGuid`, copy `Level.sav`
  and `Players/*.sav` only after size, timestamp, and SHA-256 stability checks,
  and expose opaque file IDs for streamed download;
- at most two read-only snapshots retained for ten minutes, with one capture
  job at a time; snapshots are short-lived parser input and are not backups or
  recovery sources;
- live player-Pawn positions and guild associations exposed as one
  game-thread map snapshot, reusing the same player enumeration for both map
  and guild data;
- a bounded 64-command game-thread queue that processes at most four commands
  or two milliseconds of work per engine tick and reports its current depth;
- game-thread inventory/equipment grants and player experience grants through
  reflected server-authoritative Palworld functions;
- server-authoritative Pal grants through
  `PalUtility:GetInitializedCharacterSaveParemter`,
  `PalCharacterManager:CreateIndividual`, and the normal
  `PalPlayerState:OnCreatedGrantedIndividualHandle_ServerInternal` callback;
- runtime signature checks that hide an operation when the installed game
  build no longer matches its expected reflected function contract;
- a persistence coordinator that marks successful and partial gameplay
  mutations dirty, coalesces the normal `world.save` path after two seconds,
  forces a save within ten seconds of continuous edits, and reports
  `clean`, `dirty`, `saving`, or `failed` without rolling mutations back;
- independently buildable bridge-core tests.

Dedicated servers must set `RESTAPIEnabled=True`. The official REST API must
remain firewalled from the public Internet. The bridge calls it only on the
server loopback interface to verify the configured Palworld administrator
credential. Local single-player and host connections do not use the REST API.

## Security invariant

The current non-TLS build refuses to bind outside `127.0.0.1` or `::1`. It is
safe for local protocol development and for use behind a same-host HTTPS
reverse proxy. Do not expose ports `8212` or `8213` to the LAN or Internet.

For a remote deployment, terminate TLS on the dedicated-server host and proxy
only the public HTTPS endpoint to `127.0.0.1:8213`. For example, a Caddy site
can use:

```caddyfile
bridge.example.com {
    request_body {
        max_size 64KB
    }
    reverse_proxy 127.0.0.1:8213
}
```

Only the TLS endpoint (normally TCP 443) should be allowed through the
firewall. The EXE can connect to `https://bridge.example.com:443`. A private
certificate must be pinned by its SHA-256 fingerprint in the EXE.

## Build the core tests

Use a Visual Studio developer shell:

```powershell
cmake -S native/pal_editor_bridge -B build/pal_editor_bridge -A x64
cmake --build build/pal_editor_bridge --config Release
ctest --test-dir build/pal_editor_bridge -C Release --output-on-failure
```

## Build as an UE4SS C++ mod

The `ue4ss` directory is designed to be added by an RE-UE4SS monorepo build
where the `UE4SS` target already exists:

```cmake
add_subdirectory("/absolute/path/to/Palworld-Pal-Editor/native/pal_editor_bridge/ue4ss")
```

Palworld currently requires a compatible Palworld UE4SS build and matching
member-variable layout. A compiled DLL alone is not evidence that it loads in
the dedicated server.

The built DLL is installed in the UE4SS Mods directory of either the game
client or dedicated server. Steam clients and dedicated servers use `Win64`;
PC Game Pass clients use `Content/Pal/Binaries/WinGDK`:

```text
Pal/Binaries/Win64/Mods/PalEditorBridge/dlls/main.dll
Content/Pal/Binaries/WinGDK/Mods/PalEditorBridge/dlls/main.dll
```

Enable it with `PalEditorBridge : 1` in UE4SS `Mods/mods.txt`. This repository
does not copy files into the game automatically.

After building the UE4SS target, create the installable package with:

```powershell
.\package_pal_editor_bridge.ps1
```

For a reproducible core-test, UE4SS, and package build, use:

```powershell
.\build_pal_editor_bridge.ps1
```

The script pins the UE4SS source revision used by GitHub Actions. The Mod
version has one packaging source in `native/pal_editor_bridge/VERSION`; the
runtime version strings are checked against it before a release is published.

RE-UE4SS's `UEPseudo` source is access-gated by Epic Games and cannot be cloned
by a public GitHub-hosted runner. Release workflows therefore use
`build_pal_editor_bridge.ps1 -UseVerifiedPrebuilt`: the core is rebuilt and
tested, and the committed DLL is accepted only when its version, size, SHA-256,
UE4SS revision, and a hash of every build-relevant bridge source file match
`prebuilt/manifest.json`. Any bridge source change makes the release fail until
an authorized local source build refreshes the verified DLL:

```powershell
.\build_pal_editor_bridge.ps1 `
  -UE4SSRoot C:\path\to\RE-UE4SS `
  -RefreshVerifiedPrebuilt
```

The package is written to
`mod/PalEditorBridge-UE4SS-Mod-0.6.3.zip`. It contains the required
`PalEditorBridge/dlls/main.dll` layout, an `enabled.txt`, and Chinese
installation instructions.

## Protocol v1

The bridge surface is deliberately small:

- `POST /v1/auth/login`
- `POST /v1/auth/logout`
- `GET /v1/health`
- `GET /v1/status`
- `GET /v1/players`
- `GET /v1/guilds`
- `GET /v1/map`
- `GET /v1/player-details?playerId=...`
- `GET /v1/player-inventory?playerId=...`
- `GET /v1/player-pals?playerId=...&page=0&pageSize=12`
- `POST /v1/snapshots`
- `GET /v1/snapshots/{snapshotId}`
- `GET /v1/snapshots/{snapshotId}/files/{fileId}`
- `POST /v1/commands`

Protocol capabilities are:

- `server.status`
- `player.list`
- `guild.list`
- `map.read`
- `player.details`
- `inventory.read`
- `pal.list`
- `inventory.grant`
- `player.experience.add`
- `pal.grant`
- `save.snapshot.read` (dedicated server only)
- `player.directory.read` (dedicated server snapshot)
- `player.saved.details` (dedicated server snapshot)
- `inventory.saved.read` (dedicated server snapshot)
- `pal.saved.list` (dedicated server snapshot)
- `server.announce` (dedicated server only)
- `player.kick` (dedicated server only)
- `player.ban` (dedicated server only)
- `player.unban` (dedicated server only)
- `world.save`
- `world.shutdown` (dedicated server only)

Gameplay capabilities are advertised only when the current game build exposes
the complete reflected signature expected by that operation. A build and
static signature check do not replace separate dedicated-server,
single-player, listen-server replication, save, restart, and reload tests.

The dedicated-server administrator capabilities come from the official
Palworld REST adapter and are not advertised by a local single-player or
listen-server bridge. Kick and ban accept only a REST `userId` that is present
in a freshly fetched online-player list. Unban uses a previously verified REST
`userId` because banned players are no longer present in that list. The
management UI sends no optional reason and requires a second confirmation for
all three actions. `world.shutdown` calls `world.save` first and does not
schedule shutdown if that save request fails.

In a Steam or PC Game Pass game-client process, the bridge continually
determines whether the active world is `single_player`, `listen_server`, or
`client`. A joining client advertises no player-list or mutation capabilities.
The local EXE connection also rejects that mode, so only the host can use live
management. PC Game Pass runtime mutations use the game's normal authoritative
and save paths; the bridge never edits an active WGS container directly.

`player.list` and `guild.list` are lightweight overview reads. `map.read`
samples each online player Pawn through `Actor:K2_GetActorLocation` and
returns those positions with the current runtime guild associations. A
player without a valid Pawn is reported as position-unavailable without
failing the rest of the snapshot.
`player.details` is requested only for the selected online player and contains
isolated `inventory` and `pals` sections. If a reflected field or container
cannot be resolved, that section reports an unavailable or partial state
instead of guessing offsets or returning save-file data. Guild discovery
reflects only guild objects currently loaded in the running game; it is not an
offline complete guild database.

The desktop module merges runtime rows over the read-only snapshot by
`PlayerUId`, so the online list is available immediately while saved online
and offline profiles load in the background. Snapshot reads include profile,
inventory, technology, missions, attributes, fast-travel summary, Party, and
Palbox data. The desktop map keeps authoritative Pawn coordinates for online
players and adds last-saved positions for offline players. Positive runtime
levels remain authoritative; missing or zero runtime levels retain the saved
value. Offline targets and unverified field-level mutations are explicitly
capability-gated; the bridge does not queue changes for a later login.

Live mutation never writes a running `Level.sav` or player `.sav` directly.
There is no rollback, undo, pre-mutation backup, or automatic retry after a
failed save. A failed coalesced save leaves the already-applied runtime values
visible and reports them as not yet persisted.

`pal.grant` supports up to four passive-skill IDs; the persistent HP,
ranged-attack, and defense individual values; condensation rank; and HP,
attack, defense, and work-speed soul enhancements. The current game build
marks `Talent_Melee` as transient, so the bridge rejects a melee individual
value instead of silently losing it on save. A successful command response
means that the authoritative character manager accepted the request and
created a handle. The response deliberately reports `effectVerified=false`
and `persistenceVerified=false`; it is not safe to retry the mutation merely
because a later client-side request times out.
