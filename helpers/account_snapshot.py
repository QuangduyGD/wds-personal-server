"""Snapshot decoding and semantic validation; never used as runtime storage."""

import msgpack
from models.keys import KEYS
from models.unions import IDATA_OBJECT_KEY


def normalize_user_currency(objects):
    """Copy expected User balances from canonical Currency for validation only.

    Reject ambiguous Currency rows: the runtime JOIN expects one per account.
    Do not normalize the actual export, which would hide exporter regressions.
    """
    currencies = [payload for key, payload in objects
                  if key == IDATA_OBJECT_KEY["Currency"]]
    if len(currencies) > 1:
        raise ValueError("Snapshot contains multiple Currency objects")
    fields = ("coin", "freeJewel", "paidJewel")
    balances = decode_payload("Currency", currencies[0]) if currencies else dict.fromkeys(fields, 0)
    slots = {camel(attr): index for index, attr, *_ in KEYS["User"]}
    result = []
    for key, payload in objects:
        if key == IDATA_OBJECT_KEY["User"]:
            payload = list(payload)
            for field in fields:
                payload[slots[field]] = balances[field]
        result.append([key, payload])
    return result

def camel(attr: str) -> str:
    parts = attr.rstrip("_").split("_")

    return parts[0] + "".join(
        p[:1].upper() + p[1:]
        for p in parts[1:]
    )


def timestamp_to_microseconds(value):
    """
    Convert msgpack.Timestamp -> epoch microseconds.

    PostgreSQL-side models in this server currently represent DateTime
    as integer epoch microseconds.
    """
    if isinstance(value, msgpack.Timestamp):
        return (
            value.seconds * 1_000_000
            + value.nanoseconds // 1000
        )

    return value


def decode_value(base, is_array, kind, value):
    """
    Convert a value from the client's wire representation into the
    representation expected by the DB/model layer.
    """

    if value is None:
        return None

    # Arrays
    if is_array:

        # MessagePack byte[] is decoded by msgpack as Python bytes.
        #
        # PostgreSQL album_page.items currently uses JSON, so the DB-side
        # representation is list[int].
        #
        # Example:
        #
        #     b"\x91\x96\x95"
        #
        # becomes:
        #
        #     [145, 150, 149]
        #
        if base == "byte" and isinstance(
            value,
            (bytes, bytearray),
        ):
            return list(value)

        if not isinstance(value, (list, tuple)):
            return value

        return [
            decode_value(
                base,
                False,
                kind,
                item,
            )
            for item in value
        ]

    # Nested MessagePack model
    if kind == "model":
        if isinstance(value, (list, tuple)):
            return decode_payload(
                base,
                value,
            )

        return value

    # Enum is stored as its integer representation
    if kind == "enum":
        return int(value)

    # DateTime
    if base == "DateTime":
        return timestamp_to_microseconds(value)

    return value


def decode_payload(type_name, payload):
    """
    Convert:

        [field0, field1, field2, ...]

    into:

        {
            "fieldName": value,
            ...
        }

    according to models.keys.KEYS.
    """

    if type_name not in KEYS:
        raise KeyError(
            f"No KEYS schema for type {type_name}"
        )

    result = {}

    for (
        key,
        attr,
        base,
        is_array,
        kind,
        nullable,
    ) in KEYS[type_name]:

        value = (
            payload[key]
            if key < len(payload)
            else None
        )

        result[camel(attr)] = decode_value(
            base,
            is_array,
            kind,
            value,
        )

    return result


def normalize(value):
    """
    Convert values into a hashable representation for semantic comparison.

    Timestamp precision below 1 microsecond is ignored because the current
    DB representation stores DateTime as epoch microseconds.
    """

    if isinstance(value, msgpack.Timestamp):
        return (
            "__timestamp__",
            value.seconds,
            value.nanoseconds // 1000,
        )

    if isinstance(value, bytes):
        return (
            "__bytes__",
            value,
        )

    if isinstance(value, bytearray):
        return (
            "__bytes__",
            bytes(value),
        )

    if isinstance(value, list):
        return tuple(
            normalize(x)
            for x in value
        )

    if isinstance(value, tuple):
        return tuple(
            normalize(x)
            for x in value
        )

    if isinstance(value, dict):
        return tuple(
            sorted(
                (
                    key,
                    normalize(val),
                )
                for key, val in value.items()
            )
        )

    return value


def object_key(obj):
    union_key, payload = obj

    return (
        union_key,
        normalize(payload),
    )


