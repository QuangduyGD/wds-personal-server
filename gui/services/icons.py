"""Local PNG resolution only. Unity bundles are not decoded or downloaded."""

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

TEXTURES = Path(__file__).resolve().parents[2] / "_data/assets/static-assets/Resources/Textures"


class IconResolver:
    def __init__(self, root=TEXTURES):
        self.root = Path(root).resolve()
        self._resolved = {}

    def _local_png(self, value):
        if not isinstance(value, str) or not value or "://" in value:
            return None
        value = value.replace("\\", "/")
        prefix = "Resources/Textures/"
        if prefix in value:
            value = value.split(prefix, 1)[1]
        candidate = (self.root / value).resolve()
        if self.root not in candidate.parents or candidate.suffix.lower() != ".png":
            return None
        return candidate if candidate.is_file() else None

    def resolve_item_icon(self, item) -> Path | None:
        values = item if isinstance(item, dict) else item.model_dump(by_alias=True)
        # Current ItemMaster has no asset fields. Honour explicit paths if a
        # later cache supplies them, but never resolve URLs or escape Textures.
        paths = tuple(values.get(field) for field in (
            "icon_path", "iconPath", "image_path", "imagePath", "asset_source", "assetSource"))
        item_id = values.get("id", values.get("id_"))
        key = (item_id, paths)
        if key not in self._resolved:
            result = next((path for value in paths if (path := self._local_png(value))), None)
            if result is None:
                # Optional local loose-PNG layout. This is NOT a claim that the
                # installed Unity atlas uses numeric sprite names. Only look in
                # item-specific directories, never match unrelated banner IDs.
                for folder in ("Items", "Icons/Items"):
                    result = self._local_png(f"{folder}/{item_id}.png")
                    if result is not None:
                        break
            self._resolved[key] = result
        return self._resolved[key]


class ItemPixmapCache:
    """GUI-thread-only bounded cache; decoded/scaled images survive filtering."""

    def __init__(self, resolver, size=48, capacity=256):
        self.resolver = resolver
        self.size = size
        self.capacity = capacity
        self._pixmaps = OrderedDict()
        self.placeholder = QPixmap(size, size)
        self.placeholder.fill(QColor("#edf0f3"))
        painter = QPainter(self.placeholder)
        painter.setPen(QColor("#a2aab5"))
        painter.drawRoundedRect(8, 8, size - 17, size - 17, 3, 3)
        painter.end()

    def get(self, item):
        path = self.resolver.resolve_item_icon(item)
        if path is None:
            return self.placeholder
        if path in self._pixmaps:
            self._pixmaps.move_to_end(path)
            return self._pixmaps[path]
        pixmap = QPixmap(str(path))
        pixmap = self.placeholder if pixmap.isNull() else pixmap.scaled(
            self.size, self.size, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._pixmaps[path] = pixmap
        if len(self._pixmaps) > self.capacity:
            self._pixmaps.popitem(last=False)
        return pixmap
