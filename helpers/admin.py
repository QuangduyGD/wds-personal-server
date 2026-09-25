"""Shared admin operations for CLI and GUI; all state lives in PostgreSQL."""

import datetime
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import yaml

from core import _init_connection
from db import DBConnWrapper
from db.account import get_account_by_id
from db.user import get_users, get_user_profiles, upsert_inbox
from helpers.config import Database, database
from models.enums import ThingTypes

NO_ID_TYPES = frozenset({ThingTypes.Coin, ThingTypes.Jewel, ThingTypes.Stamina})
RECEIVE_LIMIT = int(datetime.datetime(2100, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1_000_000)


def parse_thing_type(value):
    for thing in ThingTypes:
        if str(value).lower() in (thing.name.lower(), str(int(thing))):
            return thing
    raise ValueError(f"Unknown ThingType: {value}")


def validate_present(user_id, thing_type, thing_id, amount):
    if not 0 < user_id <= 2**63 - 1:
        raise ValueError("userId must be a positive BIGINT")
    thing_type = parse_thing_type(thing_type)
    if not 0 < amount <= 2**31 - 1:
        raise ValueError("Amount must be between 1 and 2147483647")
    if thing_type not in NO_ID_TYPES and not 0 < thing_id <= 2**63 - 1:
        raise ValueError(f"thingId is required and must be positive for {thing_type.name}")
    if not 0 <= thing_id <= 2**63 - 1:
        raise ValueError("thingId must be a non-negative BIGINT")
    return thing_type


@dataclass(frozen=True)
class AccountSummary:
    user_id: int
    name: str | None
    player_rank: int | None
    platform: str
    hash_user_id: str | None


async def load_account(conn, user_id):
    account = await conn.fetchrow(get_account_by_id(user_id))
    if account is None:
        raise ValueError(f"No account with userId {user_id}")
    user = await conn.fetchrow(get_users(user_id))
    profile = await conn.fetchrow(get_user_profiles(user_id))
    hash_id = await conn.conn.fetchval(
        'SELECT "hashUserId" FROM "hash_user_id" WHERE "userId" = $1', user_id)
    return AccountSummary(user_id, profile.name if profile else None,
                          user.playerRank if user else None, account.platform, hash_id)


async def give_present(conn, user_id, thing_type, thing_id, amount, message):
    """Create the same unclaimed, non-time-limited inbox row as the original CLI."""
    thing_type = validate_present(user_id, thing_type, thing_id, amount)
    async with conn.transaction():
        exists = await conn.conn.fetchval(
            'SELECT "userId" FROM "accounts" WHERE "userId" = $1 FOR UPDATE', user_id)
        if exists is None:
            raise ValueError(f"No account with userId {user_id}")
        # Serialize grants for this account and avoid an existing inbox ID.
        while True:
            inbox_id = random.randint(1_000_000, 9_999_999_999)
            if not await conn.conn.fetchval(
                'SELECT 1 FROM "inbox" WHERE "userId" = $1 AND "id" = $2', user_id, inbox_id):
                break
        await conn.execute(upsert_inbox(user_id, {
            "id": inbox_id, "thingType": int(thing_type), "thingId": thing_id,
            "thingQuantity": amount, "isTimeLimited": False, "hasReceived": False,
            "title": message or None, "description": message or None,
            "sentAt": time.time_ns() // 1000, "receivedAt": None,
            "receiveLimitAt": RECEIVE_LIMIT,
        }))
    return inbox_id


class AdminService:
    def __init__(self, config_path=None):
        if config_path is None:
            self.config = database
        else:
            content = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
            self.config = Database(**content["database"])

    @asynccontextmanager
    async def connection(self):
        cfg = self.config
        raw = await asyncpg.connect(host=cfg.host, port=cfg.port, database=cfg.database,
                                    user=cfg.username, password=cfg.password,
                                    timeout=10, command_timeout=20)
        try:
            await _init_connection(raw)
            yield DBConnWrapper(raw)
        finally:
            await raw.close()

    async def load_account(self, user_id):
        async with self.connection() as conn:
            return await load_account(conn, user_id)

    async def give_present(self, user_id, thing_type, thing_id, amount, message):
        async with self.connection() as conn:
            return await give_present(conn, user_id, thing_type, thing_id, amount, message)
