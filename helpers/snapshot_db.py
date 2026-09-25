"""Replace snapshot entity tables atomically; dry-run unless --commit is given.

Run while the server is stopped to avoid requests based on pre-import state.
Only load trusted pickle files. Accounts and hash mappings are never replaced.
"""

import json
from collections import Counter

from db import user as db_user
from helpers.account_snapshot import decode_payload, normalize_user_currency, object_key
from helpers.user_data import _REGISTRY, _REGISTRY_MAP, _USER_DATA_SQL, _table, _to_array
from models.keys import KEYS
from models.unions import IDATA_OBJECT


def prepare(root, *, allow_empty=False):
    """Validate and decode everything before deleting any database rows."""
    if not isinstance(root, list):
        raise TypeError("Snapshot root must be a list")
    objects, decoded, importers = [], [], {}
    for index, obj in enumerate(root):
        if obj is None:
            continue
        if not isinstance(obj, (list, tuple)) or len(obj) != 2:
            raise ValueError(f"Invalid object at slot {index}")
        key, payload = obj
        name = IDATA_OBJECT.get(key)
        if name not in _REGISTRY_MAP:
            raise ValueError(f"Unsupported union at slot {index}: {key}")
        if not isinstance(payload, (list, tuple)) or len(payload) != max(k[0] for k in KEYS[name]) + 1:
            raise ValueError(f"Invalid payload shape for {name} at slot {index}")
        table = _table(name)
        if table in ("accounts", "hash_user_id"):
            raise ValueError(f"Protected table: {table}")
        importer = getattr(db_user, f"upsert_{table}", None)
        if importer is None:
            raise ValueError(f"No importer for {name}")
        importers[name] = importer
        objects.append(obj)
        decoded.append((name, decode_payload(name, payload)))
    if not objects and not allow_empty:
        raise ValueError("Empty snapshot")
    # User balances are defined by Currency, so require both for replacement.
    if ("User" in importers) != ("Currency" in importers):
        raise ValueError("User and Currency must be imported together")
    expected = Counter(map(object_key, normalize_user_currency(objects)))
    return decoded, importers, expected


async def export_objects(raw, user_id):
    record = await raw.fetchrow(_USER_DATA_SQL, user_id)
    result = []
    for name, key, _get in _REGISTRY:
        rows = record[name]
        if isinstance(rows, str):
            rows = json.loads(rows)
        result.extend([key, _to_array(name, row)] for row in rows or [])
    return result


def validate_confirmation(user_id, commit, confirm_user_id):
    if user_id <= 0:
        raise ValueError("user-id must be positive")
    if commit and confirm_user_id != user_id:
        raise ValueError("Commit requires --confirm-user-id matching --user-id")
    if not commit and confirm_user_id is not None:
        raise ValueError("--confirm-user-id requires --commit")


async def replace_snapshot(raw, user_id, root, *, commit=False, confirm_user_id=None,
                           controlled_types=None, before_replace=None, progress=print):
    validate_confirmation(user_id, commit, confirm_user_id)
    decoded, importers, expected = prepare(root, allow_empty=bool(controlled_types))
    if controlled_types is not None:
        if not set(importers).issubset(controlled_types):
            raise ValueError("Backup scope omits snapshot types")
        for name in controlled_types:
            if name not in _REGISTRY_MAP or _table(name) in ("accounts", "hash_user_id"):
                raise ValueError("Invalid backup table scope")
            importer = getattr(db_user, f"upsert_{_table(name)}", None)
            if importer is None:
                raise ValueError("Unsupported backup table scope")
            importers[name] = importer
    keys = {_REGISTRY_MAP[name][0] for name in importers}
    tables = sorted(_table(name) for name in importers)
    transaction = raw.transaction(isolation="serializable")
    await transaction.start()
    try:
        # Block concurrent writes to replaced tables until validation finishes.
        await raw.execute("LOCK TABLE " + ", ".join(f'"{t}"' for t in tables)
                          + " IN SHARE ROW EXCLUSIVE MODE")
        account_before = await raw.fetchrow(
            'SELECT * FROM "accounts" WHERE "userId" = $1 FOR UPDATE', user_id)
        if account_before is None:
            raise ValueError(f"Account {user_id} does not exist")
        hash_before = await raw.fetch('SELECT * FROM "hash_user_id" WHERE "userId" = $1', user_id)
        before = await export_objects(raw, user_id)
        if before_replace is not None:
            await before_replace(before)
        untouched = Counter(object_key(obj) for obj in before if obj[0] not in keys)
        for table in tables:
            await raw.execute(f'DELETE FROM "{table}" WHERE "userId" = $1', user_id)
        for name, row in decoded:
            query = importers[name](user_id, row)
            await raw.execute(query.sql, *query.args)
        counts = Counter(name for name, _row in decoded)
        for name, count in counts.items():
            actual_count = await raw.fetchval(
                f'SELECT count(*) FROM "{_table(name)}" WHERE "userId" = $1', user_id)
            if actual_count != count:
                raise RuntimeError(f"Row count mismatch for {name}")
        exported = await export_objects(raw, user_id)
        actual = Counter(object_key(obj) for obj in exported if obj[0] in keys)
        missing, extra = expected - actual, actual - expected
        progress(f"Inserted rows: {len(decoded)}; entity types: {len(importers)}")
        progress(f"Missing objects: {sum(missing.values())}; Extra objects: {sum(extra.values())}")
        if missing or extra:
            raise RuntimeError("Post-import semantic validation failed")
        if untouched != Counter(object_key(obj) for obj in exported if obj[0] not in keys):
            raise RuntimeError("Entities outside snapshot changed")
        if account_before != await raw.fetchrow('SELECT * FROM "accounts" WHERE "userId" = $1', user_id):
            raise RuntimeError("Account/auth data changed")
        hash_after = await raw.fetch('SELECT * FROM "hash_user_id" WHERE "userId" = $1', user_id)
        if Counter(tuple(r) for r in hash_before) != Counter(tuple(r) for r in hash_after):
            raise RuntimeError("Hash mapping changed")
    except BaseException:
        await transaction.rollback()
        raise
    else:
        if commit:
            await transaction.commit()
            progress("RESULT: PASS; COMMIT complete")
        else:
            await transaction.rollback()
            progress("RESULT: PASS; ROLLBACK complete (dry-run)")


