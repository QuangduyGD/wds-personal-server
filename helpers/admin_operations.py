"""Account administration and snapshot workflows shared by desktop and CLI."""

import hashlib
import io
import json
import pickle
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import msgpack

from db.account import create_account
from helpers.admin import AdminService
from helpers.account_snapshot import decode_payload, object_key
from helpers.snapshot_db import export_objects, prepare, replace_snapshot
from helpers.user_data import _REGISTRY, _to_array
from models.keys import KEYS
from models.unions import IDATA_OBJECT

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = ROOT / "backups"


class SnapshotUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) in (("msgpack.ext", "Timestamp"), ("msgpack", "Timestamp")):
            return msgpack.Timestamp
        raise ValueError("Snapshot contains an unsupported pickle class")


@dataclass(frozen=True)
class Snapshot:
    path: Path
    sha256: str
    metadata_sha256: str
    root: list
    scope: tuple | None
    objects: int
    types: int
    nulls: int


@dataclass(frozen=True)
class Validation:
    user_id: int
    path: Path
    sha256: str
    metadata_sha256: str
    objects: int


def load_snapshot(path):
    path = Path(path).resolve()
    try:
        data = path.read_bytes()
        root = SnapshotUnpickler(io.BytesIO(data)).load()
        digest = hashlib.sha256(data).hexdigest()
        sidecar = path.with_suffix(".meta.json")
        metadata = sidecar.read_bytes() if sidecar.exists() else b""
        scope = None
        if metadata:
            meta = json.loads(metadata)
            if meta["sha256"] != digest or meta["format"] != "server-of-dreams-account-v1":
                raise ValueError("Backup metadata does not match snapshot")
            scope = tuple(meta["controlled_types"])
            registry = {name for name, *_ in _REGISTRY}
            if not scope or not set(scope).issubset(registry):
                raise ValueError("Invalid backup scope")
        decoded, importers, _ = prepare(root, allow_empty=bool(scope))
        if scope is not None and not set(importers).issubset(scope):
            raise ValueError("Invalid backup scope")
        for obj in root:
            if obj is None:
                continue
            key, payload = obj
            name = IDATA_OBJECT[key]
            rebuilt = [key, _to_array(name, decode_payload(name, payload))]
            if object_key(obj) != object_key(rebuilt):
                raise ValueError("In-memory round-trip mismatch")
        return Snapshot(path, digest, hashlib.sha256(metadata).hexdigest(), root, scope,
                        len(decoded), len(importers), sum(x is None for x in root))
    except Exception:
        raise ValueError("Snapshot inspection failed: unsupported data, schema/serializer mismatch, or invalid backup metadata.") from None


def _redact_model(name, payload, redacted):
    payload = list(payload)
    for index, attr, base, array, kind, _ in KEYS[name]:
        if index >= len(payload):
            continue
        if any(word in attr.lower() for word in ("password", "credential", "token")):
            payload[index] = None
            redacted.add(f"{name}.{attr}")
        elif kind == "model" and payload[index] is not None:
            if array:
                payload[index] = [_redact_model(base, value, redacted) if value is not None else None
                                  for value in payload[index]]
            else:
                payload[index] = _redact_model(base, payload[index], redacted)
    return payload


def write_backup(objects, user_id, directory=BACKUPS, readable_json=False):
    """Exclusive timestamped files, sidecar scope includes empty entity tables."""
    redacted = set()
    safe = [[key, _redact_model(IDATA_OBJECT[key], payload, redacted)] for key, payload in objects]
    for key, payload in safe:
        name = IDATA_OBJECT[key]
        if object_key([key, _to_array(name, decode_payload(name, payload))]) != object_key([key, payload]):
            raise ValueError("Export serializer validation failed")
    prepare(safe, allow_empty=True)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S_%fZ")
    path = directory / f"user_{user_id}_{stamp}_{uuid.uuid4().hex[:8]}.pkl"
    data = pickle.dumps(safe, protocol=pickle.HIGHEST_PROTOCOL)
    metadata = {"format": "server-of-dreams-account-v1", "user_id": user_id,
                "created_utc": stamp, "sha256": hashlib.sha256(data).hexdigest(),
                "objects": len(safe), "controlled_types": [name for name, *_ in _REGISTRY],
                "redacted_fields": sorted(redacted), "account_auth_included": False}
    # Complete metadata before exposing the final .pkl in the Backups browser.
    with path.with_suffix(".meta.json").open("x", encoding="utf-8") as output:
        json.dump(metadata, output, indent=2)
    with path.open("xb") as output:
        output.write(data)
    if readable_json:
        def readable(value):
            if isinstance(value, msgpack.Timestamp):
                return {"timestamp_seconds": value.seconds, "nanoseconds": value.nanoseconds}
            if isinstance(value, bytes):
                return {"bytes_hex": value.hex()}
            raise TypeError("Unsupported JSON export value")
        with path.with_suffix(".json").open("x", encoding="utf-8") as output:
            json.dump(safe, output, default=readable, ensure_ascii=False, indent=2)
    return path


class OperationsService(AdminService):
    async def accounts(self, search=""):
        async with self.connection() as conn:
            rows = await conn.conn.fetch('''SELECT a."userId", p.name, u."playerRank", a.platform,
                h."hashUserId" FROM accounts a
                LEFT JOIN LATERAL (SELECT name FROM user_profile WHERE "userId"=a."userId" LIMIT 1) p ON true
                LEFT JOIN LATERAL (SELECT "playerRank" FROM "user" WHERE "userId"=a."userId" LIMIT 1) u ON true
                LEFT JOIN hash_user_id h ON h."userId"=a."userId"
                WHERE strpos(a."userId"::text, $1)>0 OR strpos(lower(COALESCE(p.name,'')),lower($1))>0
                ORDER BY a."userId" LIMIT 200''', search)
            return [dict(row) for row in rows]

    async def inventory(self, user_id, kind):
        from db import user as db_user
        getters = {"Items": db_user.get_items, "Characters": db_user.get_characters,
                   "Posters": db_user.get_posters, "Accessories": db_user.get_accessorys}
        if kind not in getters:
            raise ValueError("Unsupported inventory type")
        async with self.connection() as conn:
            rows = await conn.fetch(getters[kind](user_id))
            return [row.model_dump() for row in rows]

    async def export_account(self, user_id, directory=BACKUPS, readable_json=False):
        async with self.connection() as conn:
            async with conn.conn.transaction(isolation="repeatable_read", readonly=True):
                if not await conn.conn.fetchval('SELECT 1 FROM accounts WHERE "userId"=$1', user_id):
                    raise ValueError("Account does not exist")
                objects = await export_objects(conn.conn, user_id)
                return write_backup(objects, user_id, directory, readable_json)

    async def validate_import(self, user_id, path, progress=lambda _: None):
        snapshot = load_snapshot(path)
        async with self.connection() as conn:
            outer = conn.conn.transaction(isolation="serializable")
            await outer.start()
            try:
                temp_id = await conn.conn.fetchval('SELECT COALESCE(MAX("userId"),0)+1000000 FROM accounts')
                query = create_account(temp_id, f"__gui_validation_{uuid.uuid4().hex}__")
                await conn.conn.execute(query.sql, *query.args)
                progress("Temporary account DB round-trip...")
                await replace_snapshot(conn.conn, temp_id, snapshot.root,
                                       controlled_types=snapshot.scope, progress=progress)
            finally:
                await outer.rollback()
            progress(f"Target user {user_id} dry-run...")
            await replace_snapshot(conn.conn, user_id, snapshot.root,
                                   controlled_types=snapshot.scope, progress=progress)
        return Validation(user_id, snapshot.path, snapshot.sha256, snapshot.metadata_sha256, snapshot.objects)

    async def commit_import(self, user_id, path, validation, confirmation, progress=lambda _: None):
        snapshot = load_snapshot(path)
        expected = Validation(user_id, snapshot.path, snapshot.sha256, snapshot.metadata_sha256, snapshot.objects)
        if validation != expected or confirmation != f"IMPORT {user_id}":
            raise ValueError("Import validation/confirmation is stale or does not match the target and file")
        backup = None
        async def before_replace(objects):
            nonlocal backup
            backup = write_backup(objects, user_id)
            progress(f"Pre-import backup created: {backup.name}")
        async with self.connection() as conn:
            await replace_snapshot(conn.conn, user_id, snapshot.root, commit=True,
                                   confirm_user_id=user_id, controlled_types=snapshot.scope,
                                   before_replace=before_replace, progress=progress)
        return backup

    async def diagnostics(self):
        from helpers.config import config
        from gui.services.item_catalogue import load_items
        from gui.services.icons import IconResolver, TEXTURES
        import urllib.request
        report = {"config_path": str(ROOT / "config.yml")}
        try:
            async with self.connection() as conn:
                row = await conn.conn.fetchrow('SELECT current_database() AS database, inet_server_port() AS port, version() AS version')
                report.update(dict(row))
                report["schema_version"] = await conn.conn.fetchval('SELECT version FROM databaseinfo')
                report["db"] = "Connected"
        except Exception as exc:
            report["db"] = f"FAILED ({type(exc).__name__}); check config and PostgreSQL"
        try:
            items = load_items()
            resolver = IconResolver()
            report["item_master_rows"] = len(items)
            report["local_item_pngs"] = sum(resolver.resolve_item_icon(i) is not None for i in items)
        except Exception as exc:
            report["masterdata"] = f"FAILED ({type(exc).__name__})"
        report["textures_path"] = str(TEXTURES)
        report["textures_exist"] = TEXTURES.is_dir()
        host = str(config["host"])
        host = "127.0.0.1" if host == "0.0.0.0" else "[::1]" if host == "::" else host
        url = f'http://{host}:{int(config["port"])}/api/Environment/Ping'
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=2) as response:
                report["server"] = f"HTTP {response.status} at configured local Ping endpoint (not a gameplay test)"
        except Exception:
            report["server"] = "Not reachable at configured local Ping endpoint"
        return report


def list_backups(directory=BACKUPS):
    result = []
    for path in sorted(Path(directory).glob("user_*.pkl"), reverse=True):
        try:
            meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
            result.append({"file": path.name, "userId": meta["user_id"], "UTC": meta["created_utc"],
                           "objects": meta["objects"], "path": str(path)})
        except (OSError, ValueError, KeyError):
            result.append({"file": path.name, "userId": "?", "UTC": "?", "objects": "?", "path": str(path)})
    return result
