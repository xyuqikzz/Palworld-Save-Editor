# Real-save fixture contract

Real Palworld saves are intentionally not committed here. Tests read the optional
`PALWORLD_EDITOR_REAL_FIXTURES` environment variable and always copy a selected
fixture to a temporary directory before executing any command or save.

Every local fixture must have a matching entry in `manifest.local.json` with:

- a stable `fixture_id` and relative path;
- game/save version and platform/source type;
- SHA-256 for `Level.sav` and every included player `.sav`;
- legal/privacy provenance and sanitisation notes;
- observed `InventoryInfo` alias, dynamic kinds and expected capabilities;
- optional manifest-approved dynamic attribute candidates for write tests;
- any known invariant exception.

Only the current top-level `.sav` files and current `Players/*.sav` files are
hashed and copied. Game/editor history backup directories are excluded.

`manifest.local.json` and binary saves must remain untracked. The committed
`manifest.json` documents the schema and currently records that no redistributable
real fixture has been supplied. A skipped real-save test is not a passing
round-trip test.

## Game Pass / Xbox WGS fixtures

Set `PALWORLD_EDITOR_REAL_XGP_FIXTURES` to a user-authorized directory that
contains one or more complete WGS user directories. A user directory must keep
its original `<16 hex>_<32 hex>` name and contain `containers.index`, every
referenced container directory, each `container.N`, and all payload files.

The WGS integration test:

- copies the selected user directory to a private temporary root before parsing;
- opens the copied world through `XgpWgsAdapter`;
- changes only the copied synthetic GVAS timestamp field;
- commits, reopens, and verifies the resulting logical payload;
- never writes the source fixture or the live `%LOCALAPPDATA%` WGS directory.

Absence of this environment variable is reported as a skip, not as real-WGS
validation. Real-game loading and Xbox cloud synchronization are separate
manual evidence levels and are never inferred from this test.
