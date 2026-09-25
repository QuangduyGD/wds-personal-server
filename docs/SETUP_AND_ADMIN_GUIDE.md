# Server of Dreams — Windows setup and admin guide

This guide describes the code in this checkout, not a generic private-server setup.
Example project folder: `D:\server-of-dreams\server-of-dreams-main`.
Commands run from that folder unless stated otherwise. User **6** was verified
from the private-server JWT and PostgreSQL; replace it with your verified ID.

**PostgreSQL is runtime storage.** Snapshots are import/export/backup/debug data.
The game continues to read and mutate PostgreSQL after an import. There is no
need to synchronize a pickle file after gameplay.

## 1. Prerequisites

- Windows with permission to install Python and PostgreSQL.
- Python: this checkout has no declared `requires-python`. Its `X | None` type
  syntax requires at least Python 3.10; the checked environment uses **3.13.7**.
  Use 64-bit Python 3.13 for the closest match to this tested environment.
- PostgreSQL server plus command-line tools (`psql`, `createuser`, `createdb`).
  No server minimum is declared. The checked instance is **PostgreSQL 18.6**;
  database migrations currently end at schema version **3**.
- Git if cloning. A ZIP checkout also works; this working folder has no `.git`.
- Android platform-tools/ADB and a compatible Android game installation for
  emulator use. These are not required for the admin GUI itself.
- The included launcher targets **BlueStacks**, ADB serial `127.0.0.1:5555`.
  That address is a launcher setting, not a universal emulator address.
  There is no tested LDPlayer-specific setup or Reqable integration in this repo.
- The supplied redirect addon requires **mitmproxy**, an optional dependency
  separate from `requirements.txt`. The GUI and server do not require it.

Check tools in PowerShell:

Download installers from the official [Python Windows page](https://www.python.org/downloads/windows/),
[PostgreSQL Windows page](https://www.postgresql.org/download/windows/),
[Git for Windows page](https://git-scm.com/install/windows), and
[Android platform-tools page](https://developer.android.com/tools/releases/platform-tools).
For Python select a 64-bit 3.13 installer/installation, including pip and the
launcher. For PostgreSQL install the server and command-line tools, keep note of
the selected port and store the administrator password privately. Extract
platform-tools to a stable directory; add that directory to PATH if using bare
`adb`. Install/start the emulator and enable its ADB connection in its own
settings. The repo does not distribute the game APK or install it for you.

```powershell
py --list
py -3.13 --version
git --version
psql --version
adb version
```

If a command is not found, add its installation directory to PATH or invoke its
full path. Reopen PowerShell after changing PATH. For example, PostgreSQL tools
are normally in the installed PostgreSQL version's `bin` directory; use the
actual directory on your machine, not a guessed version number.

## 2. Prepare the checkout and virtual environment

Obtain this project from the repository URL supplied to you or extract its ZIP.
This checkout does not record a Git remote, so no repository URL is invented here.

```powershell
# Only if cloning: replace this value with the repository URL you were given.
$repoUrl = 'YOUR_REPOSITORY_URL'
git clone $repoUrl server-of-dreams
# Then cd into the resulting directory. For this existing checkout:
Set-Location 'D:\server-of-dreams\server-of-dreams-main'
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, activation is optional. Use
`venv\Scripts\python.exe` explicitly in every command below. Do not recreate a
working venv merely to activate it.

Git Bash equivalents:

```bash
cd /d/server-of-dreams/server-of-dreams-main
py -3.13 -m venv venv
source venv/Scripts/activate
python -m pip install -r requirements.txt
python -m gui.main
```

`requirements.txt` includes FastAPI/Uvicorn, PostgreSQL drivers, MessagePack,
Pydantic, YAML, JWT, asset utilities and PySide6. Use the same venv for server,
CLI tools and GUI. Optional proxy tooling can be installed separately:

```powershell
venv\Scripts\python.exe -m pip install mitmproxy
```

## 3. Configure `config.yml`

On a **new** checkout only, copy `config.example.yml` to `config.yml`. Do not
overwrite a working config. Edit it locally; never paste its secrets into logs,
screenshots, bug reports or version control.

`helpers/config.py` reads `config.yml` relative to the project root and validates
the required keys at import time. Server, GUI and most CLI tools use that file.
`database_setup`, migrations and `give_present` also offer `--config`; the server
does not. Restart the server/GUI after editing config.

Important fields:

| Key | Meaning / required consistency |
|---|---|
| `host`, `port` | Uvicorn bind address/port. `0.0.0.0` listens on all IPv4 interfaces; it is not a client destination. |
| `api_endpoint` | URL handed to the client. In the supplied HTTPS redirect workflow retain `https://lb-api.wds-stellarium.com`. Emulator `127.0.0.1` refers to the emulator, not the PC. |
| `server_version` | Expected client `applicationVersion`; `/api/Environment` returns an empty result if it does not match. Example file uses `2.31.0`. |
| `asset_version` | Asset version reported to client; must correspond to the available game assets. Example file uses `1.96.0`. |
| `master_data_publish_timestamp` | Masterdata version/timestamp advertised by the server. Keep consistent with your local data. |
| `feature_maintenance_flags` | Maintenance feature flags emitted in headers. |
| `maintenance`, `maintenance_message` | Maintenance state/message. |
| `stamina_recovery_seconds` | Seconds per stamina point; example is 80. |
| `local_assets` | `true`: serve local bundles; `false`: bundle requests can redirect to the official CDN. Catalogs remain local. Offline operation needs local assets. |
| `master_data_url` | Client masterdata base URL; example points to `/master-data/production` on the intercepted asset host. |
| `static_content_url` | Client static asset base URL. |
| `asset_url` | Client bundle base URL. |
| `photo_content_url` | Photo content host. |
| `multi_real_time_server_url` | Realtime host advertised to the client; not a guarantee all realtime behavior is implemented. |
| `external_payment_url` | Advertised external payment URL; repo README explicitly excludes external payments. |
| `database.host`, `.port` | PostgreSQL instance address; separate from the HTTP server/proxy ports. |
| `database.database`, `.username`, `.password` | Database name/login; choose your own password locally. |
| `database.settings.min_size`, `.max_size` | Server connection pool limits (example 3/20). GUI uses short-lived connections. |
| `jwt_secret` | Local signing secret; generate/store privately. Changing it invalidates tokens signed with the previous secret. |

For the **included redirect addon**, these non-secret values are coherent:

```yaml
host: 0.0.0.0
port: 8123
api_endpoint: https://lb-api.wds-stellarium.com
database:
  host: 127.0.0.1
  port: 5432
  database: server_of_dreams
  username: dreams_admin
  password: "REPLACE_LOCALLY_WITH_YOUR_DATABASE_PASSWORD"
  settings:
    min_size: 3
    max_size: 20
jwt_secret: "REPLACE_LOCALLY_WITH_A_RANDOM_SECRET"
```

This is a partial example: retain all other required keys from the example file.
Use your password manager to generate secrets and paste them directly into the
local config; do not print them in terminal output.

**Port pitfall:** `config.example.yml` defaults to 8080, but
`mitm_redirect_sirius_to_local.py` sets `LOCAL_PORT = 8123`; the launcher uses
8080 for the proxy. Use server **8123**, proxy **8080**, PostgreSQL **5432**, or
deliberately change all corresponding settings. Do not bind two processes to 8080.

## 4. PostgreSQL setup and migrations

Install/start PostgreSQL. Know the administrator password you chose during
installation. Create a separate owner for this project if desired. These commands
prompt for passwords instead of placing them in command arguments:

```powershell
createuser -h 127.0.0.1 -p 5432 -U postgres -P dreams_admin
createdb -h 127.0.0.1 -p 5432 -U postgres -O dreams_admin server_of_dreams
psql -h 127.0.0.1 -p 5432 -U dreams_admin -d server_of_dreams -W
```

Use the matching credentials in `config.yml`. Creating a role/database requires
the appropriate administrator privileges. Inside `psql`, confirm the connection:

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port(), version();
\q
```

Initialize a fresh database, then apply migrations:

```powershell
venv\Scripts\python.exe -m scripts.database_setup
venv\Scripts\python.exe -m scripts.database_migration.migrate
venv\Scripts\python.exe -X utf8 -m scripts.admin_diagnostics
```

Setup creates tables using `safe=True`; it is not a substitute for migrations
on existing tables. Migration 2 → 3 adds `wireUserId` columns without resetting
data. `databaseinfo.version` records the schema version. An unfamiliar older or
newer version needs investigation; do not manually change the version number to
hide missing schema. Never use `scripts.database_reset` as a normal repair step.

For a different configuration file, setup/migrations accept
`--config path\to\config.yml`; ensure it refers to the same instance the server
and GUI will use. Diagnostics deliberately reports the live DB name, port,
PostgreSQL version and schema version, but no passwords or tokens.

PostgreSQL role creation reference: [official createuser documentation](https://www.postgresql.org/docs/16/app-createuser.html).

## 5. Masterdata, assets and starting the server

Existing caches are under `_data/masterdata` (JSON models) and `_data/assets`.
Startup calls `helpers.cache.load_master_data()`. Do not delete a working cache.
The historical README lists:

```powershell
venv\Scripts\python.exe -m scripts.download_masterdata
venv\Scripts\python.exe -m scripts.download_asset_catalogs
```

Those downloader commands contact official services; they may no longer work if
the upstream service is unavailable. `download_masterdata` supports unpacking an
existing local MasterMemory blob:

```powershell
venv\Scripts\python.exe -m scripts.download_masterdata --file 'C:\path\to\mastermemory.db'
```

The path above is a placeholder for a blob you already have. For bundle downloads,
`scripts.download_all_assets` exists and supports `--dry-run` and `--kind`; run
`--help` before a potentially large download. No admin GUI feature downloads icons.

Start the API server:

```powershell
venv\Scripts\python.exe main.py
```

Normal Uvicorn startup includes `Application startup complete` and a listening
address such as `http://0.0.0.0:8123`. The process must remain running. A startup
traceback is not a successful start. In another terminal:

```powershell
curl.exe -i http://127.0.0.1:8123/api/Environment/Ping
venv\Scripts\python.exe -X utf8 -m scripts.admin_diagnostics
```

Change 8123 if you chose another port. Ping returns a MessagePack response, not a
JSON page; HTTP 200 checks reachability, not full gameplay correctness. The GUI
Dashboard/Diagnostics probes this endpoint at the configured local server address.
The GUI can work directly with PostgreSQL even when the API server is stopped.

Stop the server with Ctrl+C. During real snapshot replacement, stop the server
or ensure no gameplay requests are in flight. Imports lock the affected entity
tables, but a request could otherwise resume using state it read before import.

## 6. Emulator, ADB and proxy

The included `.bat` launcher starts BlueStacks, sets an emulator-wide HTTP proxy,
and opens the admin GUI. The GUI then starts/stops the API server and headless
`mitmdump` without visible console windows. Inspect the launcher's `PROJECT_DIR`, `ADB_DIR`,
`BLUESTACKS_EXE`, serial and port before use. Its machine-specific paths will
not necessarily match a fresh Windows install. It does not install a CA.

Manual workflow (replace serial/IP with values confirmed on your machine):

```powershell
adb devices
adb connect 127.0.0.1:5555
adb -s 127.0.0.1:5555 get-state
ipconfig
# In another terminal, from the project folder:
venv\Scripts\mitmproxy.exe --listen-host 0.0.0.0 --listen-port 8080 -s mitm_redirect_sirius_to_local.py
# Replace PC_LAN_IP below with the PC address reachable by the emulator:
adb -s 127.0.0.1:5555 shell settings put global http_proxy PC_LAN_IP:8080
adb -s 127.0.0.1:5555 shell settings get global http_proxy
```

The addon redirects only the configured API, asset and realtime hostnames to
`IP_ADDR:LOCAL_PORT`. `IP_ADDR` is detected using a UDP socket; a VPN or multiple
adapters can make the selected address wrong. Check the addon's printed redirect
address. Its `local_assets` flag is separate from `config.yml`'s `local_assets`.
Masterdata requests are redirected regardless of the addon's asset flag.

ADB serials must come from your emulator settings / `adb devices`. Do not assume
BlueStacks settings apply to LDPlayer. The Android Studio emulator has its own
host alias `10.0.2.2`; do not assume that alias works on every emulator.
See [ADB documentation](https://developer.android.com/tools/adb) and
[Android emulator networking](https://developer.android.com/studio/run/emulator-networking-address).

### HTTPS CA trust

With the proxy active, visit `http://mitm.it` in the emulator to get the CA for
that proxy installation. Install the public CA certificate through Android's
certificate settings. Never copy/share the CA private key. Installing a user CA
does not mean the game trusts it: some Android apps only trust system CAs. A
system-CA install depends on Android version, writable system image/root and
emulator capabilities; this repo does not automate or verify that step.
Use mitmproxy's [certificate guide](https://docs.mitmproxy.org/stable/concepts/certificates/)
and [system CA emulator guide](https://docs.mitmproxy.org/stable/howto/install-system-trusted-ca-android/)
for your actual image. Successful browser HTTPS alone is not proof of game trust.

Reqable is not required by this checkout. Use an isolated emulator instance for
the game: the global proxy setting affects other apps in that emulator. Do not
set the Windows system-wide proxy just to run this workflow. Restrict firewall
access to your trusted/private network and required ports rather than disabling
the firewall. Revert the emulator proxy when finished:

```powershell
adb -s 127.0.0.1:5555 shell settings put global http_proxy :0
adb -s 127.0.0.1:5555 shell settings get global http_proxy
```

Stop the proxy after removing the setting. If you stop it first, apps may appear
offline because they are still pointing at the stopped proxy.

## 7. Authentication and choosing the right user

`helpers.auth` issues HS256 JWTs with a `uid` claim. Runtime
`helpers.user_data.current_user_id()` verifies the Authorization token and uses
that ID for DB queries. Registration creates an `accounts` row, a `hash_user_id`
mapping and default entity rows. Hash IDs are a separate public-facing mapping.

Safely verify a token from the current **private-server** client session locally:

```powershell
venv\Scripts\python.exe -c "from getpass import getpass; from helpers.auth import decode_jwt; t=getpass('Bearer token: ').strip(); print('Verified userId:', decode_jwt(t.removeprefix('Bearer ').strip()))"
```

Only the verified ID is printed. Input is hidden; do not put the token in the
command line, history or screenshots. `None` means validation failed: check
expiration, signature/config secret, issuer/audience and whether you copied the
complete token. Obtain a fresh authenticated token instead of bypassing checks.
The existing Authenticate handler deliberately accepts its login token with
expiration checking disabled, but ordinary runtime token verification checks it.

A wire `User.id`, `AuditionClear.userId` or `MissionPass.userId` inside a captured
snapshot may come from a different server. It does **not** identify the DB owner
to import into. Match the private-client verified JWT ID with an existing DB
account. A clean dry-run validates data compatibility, not your identity choice.

## 8. Verify accounts and use the admin GUI

Launch from the project root:

```powershell
venv\Scripts\python.exe -m gui.main
```

Enter a positive userId and click **Load account**. The default is 6 but other
valid IDs are supported. The persistent top panel shows userId, profile name,
player rank, platform and hashUserId. Changing the input clears the active target
until a new load succeeds. Account search requires explicit selection/loading;
choosing a backup never silently changes the active target.

Equivalent read-only SQL for a known ID:

```sql
SELECT a."userId", p.name, u."playerRank", a.platform, h."hashUserId"
FROM accounts a
LEFT JOIN user_profile p ON p."userId" = a."userId"
LEFT JOIN "user" u ON u."userId" = a."userId"
LEFT JOIN hash_user_id h ON h."userId" = a."userId"
WHERE a."userId" = 6;
```

Do not use `SELECT * FROM accounts` in shared logs: that table contains
credential/apiToken. Duplicate results in this SQL may indicate duplicate entity
rows; the account list shows at most one profile/rank per account, not a duplicate
repair tool.

GUI tabs:

| Tab | Workflow |
|---|---|
| Dashboard | Last DB status and local Ping result after Diagnostics; active account stays visible above. |
| Accounts | Search/list up to 200 accounts by ID substring or profile name; explicitly load selected row. |
| Give Present | Existing ThingType/ID/amount/message form, with Item Browser. |
| Inventory | Read-only Items, Characters, Posters, Accessories via existing getters. Click refresh for the active target. |
| Import / Export | Choose snapshot, inspect, run temporary DB round-trip plus target dry-run, then optional typed-confirmed commit. Export separately. |
| Backups | List `backups/user_*.pkl`; select a backup into the same import workflow. Backup source ID is informational, not an automatic target switch. |
| Tools / Diagnostics | Test DB/schema, local HTTP endpoint, masterdata count, asset paths and icon coverage. No secret config values displayed. |
| Guide | Read this document inside the GUI. |

DB/file operations run in a worker; controls are disabled while they run. Wait
for completion before closing the window. No automatic retry is made for writes.
The GUI does not launch/stop the server, install PostgreSQL, modify proxy/CA trust,
or verify JWTs; those explicit setup tasks remain outside the GUI.

## 9. Snapshot format and existing inspection tools

A `.pkl` snapshot has a root list. Each non-null entry is
`[unionKey, payload_array]`. Root `None` slots can occur. `models.unions.IDATA_OBJECT`
maps the union; positional field schemas come from `models.keys.KEYS`.
`helpers.account_snapshot` decodes payloads. Runtime export reads PostgreSQL using
`_USER_DATA_SQL`, `_REGISTRY`, and `_to_array` in `helpers/user_data.py`.

Use trusted captures. The newer GUI/export/import loader only allows ordinary
pickle data and MessagePack Timestamp classes; older inspection scripts still
use normal `pickle.load`, which can execute code from an untrusted file.

The existing capture in this checkout is `scripts\scraped_account.pkl`:

```powershell
venv\Scripts\python.exe -m scripts.inspect_account scripts\scraped_account.pkl --json account_report.json
venv\Scripts\python.exe -m scripts.decode_account scripts\scraped_account.pkl --output decoded_account.json
venv\Scripts\python.exe -m scripts.test_account_roundtrip scripts\scraped_account.pkl
venv\Scripts\python.exe -m scripts.dry_run_import_account scripts\scraped_account.pkl
venv\Scripts\python.exe -m scripts.test_db_roundtrip scripts\scraped_account.pkl
```

| Script | What it does |
|---|---|
| `inspect_account` | Reports shape, null slots, union/schema/getter/importer coverage; optional JSON report. |
| `decode_account` | Decodes wire arrays into readable named fields; writes JSON. This is a debugging artifact, not a DB backup or restore input. |
| `test_account_roundtrip` | Decode → `_to_array` comparison without DB writes. |
| `dry_run_import_account` | Temporary account, inserts every object, then rollback. Successful INSERTs alone do not prove a lossless export. |
| `test_db_roundtrip` | Temporary account, import → runtime DB export → semantic multiset comparison → rollback. |
| `import_account` | Shared validated replacement service; default dry-run; explicit commit flags required. It now automatically performs temporary DB validation and target dry-run, then backs up before a requested commit. |
| `export_account` | Read-consistent DB export to a timestamped pickle plus metadata; optional readable JSON. |

Decoded debugging files can contain private game payloads. Keep them local; do
not paste decoded payloads or legacy mismatch dumps into logs. Use the newer GUI
summaries/diagnostics for secret-free operational reporting.

### Validation rules and special cases

- Unknown unions, unsupported importers and wrong positional lengths are rejected.
- In-memory round-trip checks every object with the existing serializer.
- DB semantic comparison counts duplicates with a multiset; it ignores ordering.
- Success requires **Missing objects = 0** and **Extra objects = 0**. Do not
  perform a real import on INSERT-only success.
- The known capture has 5,557 slots, 5,550 objects, 88 types and seven root nulls.
  Those numbers describe this file, not every account. Other valid snapshots
  have different counts.
- Root null slots are not entity rows and are not recreated by DB export.
- `AlbumPage.items` is wire `bytes`; the decoder uses a list for the JSON DB
  field, and `_to_array` restores MessagePack bytes.
- `msgpack.Timestamp` is stored as integer epoch microseconds. Sub-microsecond
  precision is truncated; comparison deliberately tolerates only that loss.
- DB owner `userId` stays an account FK. AuditionClear's wire userId is stored in
  nullable TEXT `wireUserId`; MissionPass's in nullable BIGINT `wireUserId`.
  Existing rows cannot recover historically discarded IDs without a snapshot.
- Currency is authoritative. `get_users()` joins `currency`; expected snapshot
  User balances are normalized from Currency only for validation. No duplicate
  balance columns/source of truth are introduced.

## 10. Export, backups and safe restore

Export the verified account before changing it:

```powershell
venv\Scripts\python.exe -m scripts.export_account --user-id 6 --json
```

Default directory is project `backups`. Names are
`user_<ID>_<UTC-date>_<time>_<microseconds>Z_<random-suffix>.pkl`, with a matching
`.meta.json`. Files are created exclusively, not overwritten. `--directory`
chooses another folder. `--json` additionally writes readable JSON with explicit
timestamp/byte tags; JSON is **not** accepted for restore.

The exporter uses a repeatable-read transaction and the runtime serializer.
It excludes `accounts`, credential, apiToken and `hash_user_id` tables. Embedded
secret fields such as Photo SAS tokens are redacted and recorded in metadata.
Thus this is a **game-entity backup**, not an authentication/database disaster
recovery backup; redacted fields are not recoverable from it. It requires an
existing destination account and preserves that account's login/hash mapping.
Runtime-only tables outside the exporter registry are not included.

Keep the `.pkl` and `.meta.json` together. Metadata stores source ID, UTC time,
SHA-256, entity count, redactions and controlled types including empty tables.
This lets restore clear entity types that were empty at backup time. Deleting
the sidecar changes semantics: an ordinary external pickle replaces only the
types actually present. The hash detects accidental changes, not authenticity
against an attacker who can replace both files. Store backups privately and
copy them to a separate drive if they matter.

Safe sequence in GUI:

1. Verify/load the target ID and profile.
2. Export/backup its current state.
3. Choose a trusted capture or choose a local backup from Backups.
4. Inspect: view object/type/null counts and file hash.
5. Run **Dry-run + DB round-trip**. This tests a temporary account and the
   selected target, rolling both back. Wait for PASS and Missing/Extra 0.
6. With game activity stopped, click Import and type exactly `IMPORT 6`
   (substitute the displayed active ID).
7. The service rechecks ID/path/file and metadata hashes, acquires locks, creates
   a new pre-import backup, replaces controlled entity rows, checks row counts,
   re-exports and semantically compares, checks account/hash preservation, then
   commits. Errors before commit roll back; a successful backup may remain.

Changing the target, file path or watched file/metadata invalidates the GUI
validation. Hashes are checked again by the service, so editing/replacing a file
cannot reuse an old PASS. An invalid confirmation does not write anything.

Equivalent CLI workflow:

```powershell
# Safe default: temporary DB round-trip + target replacement dry-run, all rolled back
venv\Scripts\python.exe -m scripts.import_account scripts\scraped_account.pkl --user-id 6 --dry-run
# Only when you intend to replace that verified account:
venv\Scripts\python.exe -m scripts.import_account scripts\scraped_account.pkl --user-id 6 --commit --confirm-user-id 6
```

For restore, replace the input path with the selected backup `.pkl`, leaving its
sidecar next to it. The same pipeline is used. It never deletes the account row.
No operation silently changes the target to the backup's source ID.

## 11. Give Present and Item Browser

Giving a present inserts an **unclaimed inbox row**. It does not directly mutate
the owned item table or Currency; the player claims it in-game. The shared
`helpers/admin.py` service is used by GUI and CLI, with account existence checked
inside the transaction. The message becomes title and description.

```powershell
venv\Scripts\python.exe -m scripts.give_present --user 6 --type Coin --amount 100 -m "Admin present"
venv\Scripts\python.exe -m scripts.give_present --user 6 --type Item --thing-id 140000 --amount 1 -m "Admin present"
```

These commands **commit real presents**. They are examples, not diagnostic tests.
The CLI accepts case-insensitive ThingTypes names or enum numbers and keeps its
`--config` option. GUI/CLI validate positive amounts and required IDs; they do not
validate every Character/Poster/etc ID against its master table.

Coin (12), Jewel (13), Stamina (15) need no thingId; GUI disables that field and
sends 0. Other supported types are Item, Character, Poster, Accessory, Costume,
Trophy, Stamp, Nameplate, NameColor, Bomb, Note, Music, Decoration, AlbumTheme,
NameBaseColor, IconFrame and HomeSkin. Use their respective **master IDs**, not
owned-instance IDs.

**Browse Items…** loads all `cache.item_master` rows dynamically (currently
1,984). Search Japanese full/partial names or numeric IDs. Select/double-click
sets ThingType=Item and the ItemMaster ID. Other ThingTypes keep manual ID entry.

All 49 requested names were found. The complete mapping is in
[the ItemMaster report](../gui/ITEM_MASTER_REPORT.md), including:

| Sanity item | ID |
|---|---|
| ジュゴン像 | 140000 |
| 金の額縁 | 130063 |
| 明星の額縁 | 130064 |

Local diagnostics:

```powershell
venv\Scripts\python.exe -X utf8 -m scripts.list_items --search "ジュゴン"
venv\Scripts\python.exe -X utf8 -m scripts.report_item_catalogue --output gui/ITEM_MASTER_REPORT.md
```

Output columns are `ID | Japanese name | category | icon path`.

### Icons: what is actually available

Current ItemMaster has no icon path field. The local Android catalog points to
`SpriteAtlases/Items` / `Assets/AddressableAssets/Icons/Items` / `Icon_Items.spriteatlas`
in `2d-assets/android/spriteatlases_assets_spriteatlases/items.bundle`.
The bundle's sprite-name mapping has not been decoded/verified. The local
`_data/assets/static-assets/Resources/Textures` contains no loose item PNGs, so
the current catalogue reports zero resolved item icons.

`IconResolver.resolve_item_icon(item)` returns a local `Path` or `None`. It
supports explicit local asset path fields when present and optional loose-PNG
layouts `Textures/Items/<ID>.png` or `Textures/Icons/Items/<ID>.png`. These are
supported admin layouts, not a claimed Unity atlas convention. It rejects URLs,
paths outside Textures and unrelated banner-ID matches. QPixmap loads/scales
icons to 48 pixels, caches them, and uses a neutral placeholder for missing or
invalid images. No image download/hotlink is implemented.

## 12. Troubleshooting

| Symptom | Likely cause | Diagnose | Fix |
|---|---|---|---|
| Password authentication failed | Wrong DB login/password or instance | `psql -h 127.0.0.1 -p 5432 -U dreams_admin -d server_of_dreams -W` | Correct local config; reset password using authorized PostgreSQL administration, never paste it into logs. |
| Connection refused / wrong DB | Service stopped, wrong port/instance | `Get-Service *postgres*`; `Test-NetConnection 127.0.0.1 -Port 5432`; `scripts.admin_diagnostics` | Start the intended service and match its port/database. Do not reset data. |
| Database does not exist | Wrong name or not created | Connect to `postgres` database with psql and run `\l` | Create the intended database with the correct owner or fix config. |
| Missing `wireUserId` / schema mismatch | Setup run without migration | `SELECT version FROM databaseinfo;` | Run registered migrations against the same instance; investigate unsupported versions. |
| Server/GUI sees different accounts | Different config/process/instance | `scripts.admin_diagnostics`; inspect any CLI `--config` argument | Use the root config consistently and restart long-running processes. |
| Address already in use | Proxy/server port conflict or old server | `Get-NetTCPConnection -State Listen -LocalPort 8123,8080` | Keep server/proxy ports distinct; stop the known old process normally. |
| JWT decode gives None | Expired token, wrong signing config, incomplete token | Hidden-input verification command in section 7 | Obtain a fresh private-server token, use the correct config; do not skip signature checks. |
| Malformed JWT / Not enough segments | Copied a partial token or wrong field | Same hidden-input verifier; never print input | Copy the complete Authorization token, not credential/hash ID. |
| Wrong-user risk | Using capture ID or guessing ID | Verify JWT ID and load same account in GUI | Use displayed ID/profile; revalidate import after any target change. |
| Proxy not working | Wrong serial/IP/port; stopped proxy | `adb devices`; `adb ... shell settings get global http_proxy`; inspect redirect address | Correct the emulator proxy/PC address and server LOCAL_PORT; reset proxy with `:0` when finished. |
| Emulator cannot reach PC | Loopback confusion, firewall, wrong NIC/VPN | PC Ping endpoint; emulator browser to PC address; `ipconfig` | Use reachable PC IP and scoped firewall rule; `0.0.0.0` is bind-only. |
| HTTPS CA trust error | CA missing, different proxy CA, user CA ignored | Check Android trusted credentials and proxy TLS error | Install correct public CA; follow version-specific system trust guide if necessary. No universal root script is provided here. |
| Game cannot initialize/masterdata update | Empty cache, incompatible version, asset redirect error | `scripts.admin_diagnostics`; check `_data/masterdata`; Ping | Restore matching cached data; align server_version/asset URLs; inspect relevant request, without exposing auth headers. |
| Snapshot mismatch | Wrong schema, unsupported entity, changed serialization | The three round-trip commands; GUI validation | Fix cause; require Missing/Extra 0. Do not bypass comparison or commit. |
| INSERT/duplicate failure | Importers are INSERTs; reused owner rows; schema divergence | Transactional dry-run and schema checks | Use validated replacement pipeline; never assume `upsert_*` means ON CONFLICT; never delete accounts. |
| Missing static assets / icon | Cache incomplete or icon only exists inside bundle | `scripts.list_items --search ...`; Diagnostics | Restore local matching assets. Missing item PNG is expected with this cache; placeholder is not a DB failure. |
| No ItemMaster rows | Missing/empty local JSON | `scripts.list_items`; inspect `_data/masterdata/ItemMaster.json` | Restore cached masterdata or use documented downloader with an available source. |
| No module named PySide6 | Wrong interpreter/venv | `venv\Scripts\python.exe -m pip show PySide6` | Install requirements using that exact interpreter, then `-m gui.main`. |
| Japanese terminal text garbled | Console encoding/font | Run commands with `-X utf8` | Use a Unicode-capable terminal/font; GUI uses system font fallback. |
| GUI import remains disabled | No PASS, changed target/file/sidecar | Read snapshot status and log | Reselect file if needed and repeat dry-run; do not fabricate validation metadata. |
| Export says schema/serializer error | Existing DB entity cannot round-trip | In-memory/DB tests; schema migration check | Fix inconsistency first. Do not treat an incomplete export as a safe backup. |

`adb ...` in the table abbreviates `adb -s YOUR_VERIFIED_SERIAL`; use the complete
commands from section 6. Never include config passwords, JWTs or request auth
headers in diagnostic reports. Diagnostics only prints an allowlisted summary.

## 13. Compact PowerShell command reference

All commands start in the project folder. Replace file paths and verified user ID
as appropriate. Commands marked COMMIT change data.

```powershell
py -3.13 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m scripts.database_setup
venv\Scripts\python.exe -m scripts.database_migration.migrate
venv\Scripts\python.exe main.py
venv\Scripts\python.exe -m gui.main
venv\Scripts\python.exe -X utf8 -m scripts.admin_diagnostics
venv\Scripts\python.exe -m scripts.inspect_account scripts\scraped_account.pkl
venv\Scripts\python.exe -m scripts.decode_account scripts\scraped_account.pkl --output decoded_account.json
venv\Scripts\python.exe -m scripts.test_account_roundtrip scripts\scraped_account.pkl
venv\Scripts\python.exe -m scripts.dry_run_import_account scripts\scraped_account.pkl
venv\Scripts\python.exe -m scripts.test_db_roundtrip scripts\scraped_account.pkl
venv\Scripts\python.exe -m scripts.export_account --user-id 6 --json
venv\Scripts\python.exe -m scripts.import_account scripts\scraped_account.pkl --user-id 6 --dry-run
# COMMIT only after verifying intent and target:
venv\Scripts\python.exe -m scripts.import_account scripts\scraped_account.pkl --user-id 6 --commit --confirm-user-id 6
# COMMIT a present:
venv\Scripts\python.exe -m scripts.give_present --user 6 --type Item --thing-id 140000 --amount 1 -m "Admin present"
venv\Scripts\python.exe -X utf8 -m scripts.list_items --search "ジュゴン"
venv\Scripts\python.exe -m scripts.smoke_admin_gui
venv\Scripts\python.exe -X utf8 -m scripts.smoke_item_browser
venv\Scripts\python.exe -m scripts.test_import_account
venv\Scripts\python.exe -X utf8 -m scripts.smoke_admin_operations
```

In Git Bash activate with `source venv/Scripts/activate`, use `python` for the
venv interpreter, and change file separators to `/`, e.g.
`python -m scripts.import_account scripts/scraped_account.pkl --user-id 6 --dry-run`.
In PowerShell an executable path containing spaces needs `& 'C:\full path\tool.exe'`.

## 14. Limits and validation scope

This is a first practical admin panel, not a replacement for PostgreSQL tools or
a complete implementation of all game features. Inventory is read-only; account
search is capped at 200; no account deletion/reset, inventory editor, server
process manager, CA/proxy installer or token-input GUI is provided. The item
catalogue is complete for the local cache; item artwork remains placeholder
until matching local PNGs are available. Backups exclude auth and secret fields.

Automated checks cover existing capture round-trips, temporary-account import
and rollback, backup/export/restore safety, GUI widgets offscreen, and existing
Give Present behavior. They do not certify fresh-machine installation, emulator
certificate trust, official download availability or end-to-end gameplay on a
new Android image. A local HTTP Ping check is reported separately from these tests.
