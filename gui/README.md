# Desktop admin panel

From the project root on Windows:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m gui.main
```

The GUI reads the existing project `config.yml` through `helpers.config`.
PostgreSQL must be running; the game server does not need to be running.
No credentials are embedded in the GUI. It defaults to the verified test ID **6**.

1. Click **Load account** to connect and display the account summary.
2. Choose a ThingType. Coin, Jewel and Stamina use ID 0; other types require a
   positive master ID. This version does not validate IDs against master data.
   For Item, click **Browse Items…** to load all rows from the existing local
   ItemMaster cache. Search by Japanese name/substring or ID; double-click a row
   or click **Use selected item** to set ThingType=Item and its master ID.
   Character, Poster and other ThingTypes still accept manual IDs as before.
3. Set amount and optional message, then click **Give Present to user 6**.
4. Check the activity log. Success means a committed, unclaimed inbox present;
   the player still claims it in-game.

Changing userId clears the loaded target and disables grants until another
successful load. The service checks that the account exists again inside the
write transaction. Database operations run on a worker thread; controls are
disabled until completion. There is no automatic retry of a grant.

The Dashboard manages the local API server and headless `mitmdump` proxy. They
run as child processes with Windows `CREATE_NO_WINDOW`; stdout/stderr are shown
in Process Logs. The tray menu can open the admin, toggle either process,
restart both, show logs or exit. Settings control automatic startup,
minimize-to-tray and cleanup on exit. The GUI does not hide processes from Task
Manager; it only removes unnecessary console windows.

`helpers/admin.py` holds the shared operations. `scripts/give_present.py` keeps
its CLI flags, including `--config`; it calls the same service directly.
Game server routes are unchanged. The panel now includes Accounts, read-only Inventory, safe Import / Export, Backups, Diagnostics and an embedded Guide. See [the full setup and admin guide](../docs/SETUP_AND_ADMIN_GUIDE.md). Import defaults to validation/dry-run, requires `IMPORT <userId>`, binds PASS to user/file hashes, and saves a backup before replacement.

Smoke test:

```powershell
venv\Scripts\python.exe -m scripts.smoke_admin_gui
```

This reads account 6, tests grants on a temporary account in a transaction that
is always rolled back, checks CLI delegation and runs Qt offscreen with a fake
service. It does not send a real present to account 6.

Item Browser checks and ID report:

```powershell
venv\Scripts\python.exe -X utf8 -m scripts.smoke_item_browser
venv\Scripts\python.exe -X utf8 -m scripts.report_item_catalogue --output gui/ITEM_MASTER_REPORT.md
```

See [ITEM_MASTER_REPORT.md](ITEM_MASTER_REPORT.md) for all requested Japanese
names/IDs and the inspected asset paths. Icons are local PNGs only. The current
assets contain an Items Unity atlas but no loose item PNGs, so placeholders are
expected. No images are downloaded. IconResolver accepts explicit local paths
when available or optional `Textures/Items/<ID>.png` and
`Textures/Icons/Items/<ID>.png` files. It never guesses from unrelated images.
Scaled QPixmaps are loaded lazily and kept in a bounded cache across searches.
