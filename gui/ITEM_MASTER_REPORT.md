# ItemMaster catalogue report

Source: `_data/masterdata/ItemMaster.json` via `helpers.cache.cache.item_master`.
Rows: **1984**. Resolved local PNGs: **0**.

Exact-name matches are listed below; duplicate names retain every ID. Missing names are not assigned guessed IDs.

| Japanese name | ItemMaster ID(s) |
|---|---|
| スタミナドリンク | 110001 |
| 高級スタミナドリンク | 110002 |
| 歌劇目録 | 130001 |
| 蒼玉のメダル | 130011 |
| 紅玉のメダル | 130012 |
| 翠玉のメダル | 130013 |
| 黄玉のメダル | 130014 |
| 紫玉のメダル | 130015 |
| スターの煌き | 130051 |
| 練習台本【初級】 | 120001 |
| 練習台本【中級】 | 120002 |
| 練習台本【上級】 | 120003 |
| 愛憐のかけら | 130021 |
| 蒼凛のかけら | 130022 |
| 翠彩のかけら | 130023 |
| 陽光のかけら | 130024 |
| 夢幻のかけら | 130025 |
| 愛憐の結晶 | 130031 |
| 蒼凛の結晶 | 130032 |
| 翠彩の結晶 | 130033 |
| 陽光の結晶 | 130034 |
| 夢幻の結晶 | 130035 |
| 役者名鑑 | 130041 |
| 花形名鑑 | 130042 |
| スター名鑑 | 130043 |
| 銅の額縁 | 130061 |
| 銀の額縁 | 130062 |
| 金の額縁 | 130063 |
| 明星の額縁 | 130064 |
| 星のしずく | 130072 |
| かたい木材 | 130081 |
| カラーストーン | 130082 |
| 星の砂 | 130091 |
| 白星のデコペン | 130301 |
| 緋星のデコペン | 130302 |
| 黄星のデコペン | 130303 |
| 蒼星のデコペン | 130304 |
| 虹星のデコペン | 130305 |
| ルミナスオイル | 130306 |
| ジュゴン像 | 140000 |
| 金のジュゴン像 | 150000 |
| 特別公演チケット | 130201 |
| アクターガチャチケット | 210001 |
| ★3アクター交換チケット | 220101 |
| SRポスター交換チケット | 221101 |
| 衣装交換シール | 222001 |
| SP撮影フィルム交換チケット | 222005 |
| EXPブーストチケット【雪】 | 710001 |
| 報酬ブーストチケット【雪】 | 711001 |

## Sanity checks

- ジュゴン像: expected 140000; cache [140000]; PASS
- 金の額縁: expected 130063; cache [130063]; PASS
- 明星の額縁: expected 130064; cache [130064]; PASS

## Local icon findings

ItemMaster has no icon/asset path field in this cache. The local Android Addressables catalog identifies `SpriteAtlases/Items`, `Assets/AddressableAssets/Icons/Items` and `Icon_Items.spriteatlas`; the downloaded atlas is in `2d-assets/android/spriteatlases_assets_spriteatlases/items.bundle`.

The installed `static-assets/Resources/Textures` has no item PNG directory. A numeric sprite-to-item mapping inside the Unity bundle has not been verified. The GUI does not decode bundles or download images; missing icons use a neutral placeholder.

IconResolver accepts explicit local PNG path fields if supplied by a future item model, and optionally loose PNGs placed at `Textures/Items/<ItemMaster ID>.png` or `Textures/Icons/Items/<ItemMaster ID>.png`. These are supported local layouts, not an inferred atlas naming rule. Unrelated banner PNGs are never used merely because their numeric filename matches.
