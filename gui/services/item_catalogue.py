"""Read the same typed, local master-data cache as the game server."""

from helpers.cache import cache, load_master_data


def load_items():
    if not cache.item_master:
        load_master_data()
    if not cache.item_master:
        raise ValueError("No ItemMaster rows found in _data/masterdata/ItemMaster.json")
    return sorted(cache.item_master, key=lambda item: (item.display_order, item.id_))
