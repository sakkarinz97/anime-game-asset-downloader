# Anime Game Masterdata & Asset Downloader

**Language / ภาษา:** [🇺🇸 English](README.md) | [🇹🇭 ภาษาไทย](README.th.md)

A unified Python CLI tool for fetching **Masterdata JSON** and downloading/extracting **full-resolution assets** across 8 popular anime, idol, and gacha games—organized cleanly by game and category, with built-in automated sync to **Google Drive**.

> [!NOTE]
> This project follows a **Hybrid Architecture (Approach 2)**: only Python downloader scripts live on **GitHub** (`sakkarinz97/anime-game-asset-downloader`), while large images, Live2D/Spine models, and Unity AssetBundles are excluded via `.gitignore` and stored in **Google Drive** (`Work/AnimeGameAssets/`).

---

## Table of Contents

1. [Project Overview & Architecture](#overview)
2. [Supported Games & Extracted Assets](#games)
3. [Requirements & Installation](#install)
4. [Complete CLI Reference](#cli)
5. [Usage Examples](#examples)
6. [Per-Game GitHub, API & CDN References](#references)
7. [Official Copyright Notices & Legal Disclaimer](#copyright)

---

<a id="overview"></a>
## 1. Project Overview & Architecture

**Anime Game Masterdata & Asset Downloader** consolidates **8 game adapters** behind a single CLI entrypoint (`main.py` / `anime-dl`). It supports both direct HTTP JSON/image endpoints and encrypted/packed UnityFS AssetBundles requiring AES decryption, Addressables catalog parsing, and `UnityPy` texture/shader/animation extraction.

### Supported Asset Categories
1. **`card`** — Highest-resolution Card / Memoria illustrations (base & awakened/trained variants, HQ clean backgrounds, cutouts, and covers where available).
2. **`live2d`** — 2D character model rigs (Live2D Cubism 2/3/4/5 with `.moc`/`.moc3`, `model.json`/`model3.json`, textures, physics, expressions, and motions; games built on **Spine** save `.skel` / `.atlas` / `.png` files under `spine/` automatically).
3. **`character`** — Standing character illustrations (Cutouts / Chibi `puchi` / `livesd`), character icons, signatures, and high-resolution posters.
4. **`card_animation`** *(Special mode exclusively for **`yumesute`** and **`assaultlily`**)* — Fetches and unpacks animated card UnityFS AssetBundles into multi-layer textures, FX sprite sheets, alpha masks, Emoria Spine 3.6 rigs, and `animation_meta.json` (optionally keeping or skipping raw `.bundle` files).
5. **`all`** — Runs all 3 standard categories (`card`, `live2d`, `character`) sequentially in a single command (and can be combined with `--card-animation` to include animated cards for supported games).

### Repository & Output Directory Structure

```text
anime-game-asset-downloader/
├── main.py                  # Main CLI entrypoint (`anime-dl`)
├── pyproject.toml           # Python package metadata & optional dependency extras
├── requirements.txt         # Optional dependencies for UnityFS decoding & holodori decryption
├── core/
│   ├── base.py              # Shared adapter contract, DownloadOptions, CategoryResult
│   ├── http_client.py       # Resilient HTTP client (retries, backoff & HTML-404 guard)
│   ├── unity_utils.py       # Safe UnityPy Texture2D, TextAsset, Spine 3.6 & Animated Card extractor
│   └── drive_sync.py        # Google Drive synchronization client backed by `gdrive` CLI
├── games/
│   ├── __init__.py          # Registry of all 8 game adapters (`ADAPTERS`)
│   ├── cgss.py              # THE iDOLM@STER Cinderella Girls: Starlight Stage
│   ├── mltd.py              # THE iDOLM@STER Million Live! Theater Days
│   ├── pjsk.py              # Project SEKAI COLORFUL STAGE! feat. Hatsune Miku
│   ├── holodori.py          # hololive Dreams
│   ├── bandori.py           # BanG Dream! Girls Band Party!
│   ├── ournotes.py          # BanG Dream! Our Notes
│   ├── yumesute.py          # World Dai Star: Yume no Stellarium
│   └── assaultlily.py       # Assault Lily: Last Bullet
└── downloads/               # (gitignored) Local masterdata cache & downloaded assets
    └── <game_code>/
        ├── masterdata/      # Cached JSON / Addressables / Octo catalogs
        ├── card/
        ├── card_animation/  # (yumesute, assaultlily)
        ├── live2d/          # (saved as `spine/` for yumesute & assaultlily)
        └── character/
```

When `--upload-drive` is enabled, assets are synced to **Google Drive** under:

```text
Work/
└── AnimeGameAssets/
    ├── cgss/          (card, character)
    ├── mltd/          (card, character)
    ├── pjsk/          (card, live2d, character)
    ├── holodori/      (card, live2d, character)
    ├── bandori/       (card, live2d, character)
    ├── ournotes/      (card, live2d, character)
    ├── yumesute/      (card, card_animation, spine, character)
    └── assaultlily/   (card, card_animation, spine, character)
```

---

<a id="games"></a>
## 2. Supported Games & Extracted Assets

| Code (`--game`) | Game Title | Supported `--region` | `card` | `card_animation` *(Special)* | `live2d` / `spine` | `character` |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **`cgss`** | THE iDOLM@STER Cinderella Girls: Starlight Stage | `jp` | Card PNGs (`card`) + widescreen illustrations (`spread`) | — | ❌ *(Game uses 3D models & 2D Puchi sprites; no Live2D)* | Card icons (`icon_card`) + `puchi` chibi sprites |
| **`mltd`** | THE iDOLM@STER Million Live! Theater Days | `jp` | Framed/unframed card PNGs + HQ backgrounds (`card_bg_hq`, normal & awake) | — | ❌ *(Game uses 3D models; no Live2D)* | Large portrait icons (`icon_l`, normal & awake) |
| **`pjsk`** | Project SEKAI COLORFUL STAGE! feat. Hatsune Miku | `jp`, `en`, `tw`, `kr`, `cn` | `card_normal.png` + `card_after_training.png` (★3+) | — | ✅ **Cubism 3/4** (`.moc3`, `.model3.json`, textures, motions via `_ripper.json`) | Transparent cutouts (`cutout`, `cutout_trm`) + Character Icons |
| **`holodori`** | hololive Dreams (`holodori`) | `jp` | Octo AES decrypt + UnityPy: Full `2048x1024` + Vertical (`vert`) | — | ✅ **Cubism 5** (`.moc3`, `.model3.json`, 4K textures, `physics3.json`, `.exp3.json`, `_shared_motions`) | Full 2D Standing (`4096x4096`) + `icon_mini` + `key_band` |
| **`bandori`** | BanG Dream! Girls Band Party! | `jp`, `en`, `tw`, `cn`, `kr` | `card_normal.png` + `card_after_training.png` (★3+) | — | ✅ **Cubism 2** (`.moc`, `model.json`, `physics.json`, motions, expressions) | Cutout trims + `livesd` chibi sprites + Character Icons |
| **`ournotes`** | BanG Dream! Our Notes | `hk-tw-mo` *(alias: `tw`)*, `en`, `jp` | Member Cards (`member_full`, `member_background`) + Support Cards (`snap_full`) | — | ✅ **Cubism 3/4** (manifest-driven + auto-merged chunked `.prefab.json`) | `character_sprite`, `character_thumbnail`, `character_face_icon` + `member_character` cutouts |
| **`yumesute`** | World Dai Star: Yume no Stellarium (`Yumesute`) | `jp` | Full-res `1920x1180` (`0.png`/`1.png`, `cover0`/`cover1`) + Cutouts | 🎬 **Animated Actor Cards** (`4★ SSR _1` & `15xxxx` series): 1920x1180 layers + FX sprite sheets + masks + Shader/Holo JSON + `.bundle` | 🦴 **Spine 4.1** (`.skel`, `.atlas`, `.png` — saved to `spine/`) | Card/Poster icons + *(with `UnityPy` + `brotli`)* Full Posters `1357x1920` & Signatures from live CDN |
| **`assaultlily`** | Assault Lily: Last Bullet | `jp` | Full JPG `800x600` (`full/`) + 256x256 PNG + `memoria_ultimate` (★6+ / infinite-evolvable) | 🎬 **Animated Memoria Prefabs** (`card_prefab`): 2048x2048 Atlases + VFX sprites + Emoria **Spine 3.6** (`.skel`/`.atlas`/`.png`) + `card_preview.jpg` + `animation_meta.json` + `.bundle` | 🦴 **Spine Samples** (`.skel`, `.atlas`, `.png` `CharacterJobSpine*` — saved to `spine/`) | Character portraits (`chara`) + Costume Standing `@2x` (`900x1550`) + Full Illus (`1536x1174` JPG) + `job_icon` |

> [!TIP]
> * **`yumesute`** and **`assaultlily`** run on **Esoteric Software Spine** rather than Live2D Cubism. Running `--category live2d` automatically places their Spine assets inside each game's `spine/` folder to match the actual engine format.
> * Unity CDN endpoints (`yumesute`, `assaultlily`, `holodori`) apply built-in concurrency caps, pacing delays, and exponential retries to avoid server throttling.

---

<a id="install"></a>
## 3. Requirements & Installation

* **Python `>= 3.10`**

### Option 1: Minimal Mode (Python Standard Library Only)
Works out of the box with **zero external packages** for `cgss`, `mltd`, `pjsk`, `bandori`, `ournotes`, `assaultlily` static/Spine samples, and `yumesute` GitHub-hosted assets:

```bash
git clone https://github.com/sakkarinz97/anime-game-asset-downloader.git
cd anime-game-asset-downloader
python3 main.py --list-games
```

### Option 2: Full Mode (Enables `holodori`, `yumesute` Live CDN, & `--card-animation`)
Install the UnityFS decryption and asset extraction dependencies (`Pillow`, `UnityPy`, `brotli`, `holodori-asset-tools`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Or install as a package (exposes the `anime-dl` command globally inside your environment):

```bash
pip install -e ".[all]"
# Or choose targeted extras: ".[unity]" or ".[holodori]"
```

### Prerequisite for Google Drive Sync (`--upload-drive`)
Requires the `gdrive` CLI available on `PATH` (or `/opt/antigravity/bin/gdrive`) and authenticated against your Google Drive account (`gdrive auth status`).

---

<a id="cli"></a>
## 4. Complete CLI Reference

Invoke via `python3 main.py [OPTIONS]` or `anime-dl [OPTIONS]` (when installed via `pip install -e .`).

### All Command-Line Options

| Flag | Default | Values / Format | Description |
| :--- | :--- | :--- | :--- |
| `-h`, `--help` | `False` | Flag | Show CLI help message and exit |
| `--list-games` | `False` | Flag | Print all 8 supported games, regions, `AnimCard` capability, and credits, then exit |
| `--game` | `all` | `cgss`, `mltd`, `pjsk`, `holodori`, `bandori`, `ournotes`, `yumesute`, `assaultlily`, `all` | Target game(s), space- or comma-separated (e.g., `--game pjsk,bandori` or `--game pjsk bandori`) |
| `--category` | `all` | `card`, `live2d`, `character`, `card_animation`, `all` | Target category (`all` executes `card` + `live2d` + `character`) |
| `--card-animation` | `False` | Flag | *(Special option for `yumesute` & `assaultlily`)* Also download the `card_animation` category alongside `--category` |
| `--animated-only` | `False` | Flag | *(Special option for `yumesute` & `assaultlily`)* Filter `card`/`card_animation` to animated-capable cards only |
| `--no-raw-bundle` | `False` | Flag | Do not retain raw UnityFS `.bundle` archives during `card_animation` extraction (saves extracted PNG/Spine/JPG/JSON only) |
| `--region` | `jp` | See table below | Server region for multi-region games |
| `--rarity` | `None` | See table below | Filter cards/items by rarity |
| `--character` | `None` | String / ID | Case-insensitive substring filter on character name (EN/Romaji/JP/KR/ZH), card title, or ID |
| `--limit` | `None` | Integer | Limit items per game/category (useful for testing or sampling) |
| `--threads` | `8` | Integer | Max concurrent download threads *(automatically capped at 2–3 on sensitive Unity CDNs)* |
| `--out-dir` | `./downloads` | Path | Local output root directory |
| `--refresh-masterdata` | `False` | Flag | Re-fetch cached masterdata JSON and asset catalogs instead of using local cache |
| `--upload-drive` | `False` | Flag | Sync downloaded assets to Google Drive after each category completes |
| `--drive-parent-id` | `1kaSiYfkeaFXvXQQbZlFKJV4Tq--M5yFf` | Drive Folder ID | Destination Google Drive parent folder ID (defaults to `Work/`) |
| `--drive-root-name` | `AnimeGameAssets` | Folder name | Root subfolder name created/reused inside `--drive-parent-id` |
| `--drive-mode` | `auto` | `auto`, `direct`, `zip` | Upload strategy: `direct` (file-by-file mirroring folder structure), `zip` (packs `<game>_<cat>.zip`), or `auto` (`direct` when ≤ 40 files else `zip`) |
| `--cleanup-local` | `False` | Flag | Delete local category directory after successful upload to Google Drive |
| `--overwrite-drive` | `False` | Flag | Update/overwrite existing files with the same name in Google Drive |

### Supported `--region` and `--rarity` Values Per Game

| Game | Supported `--region` | Supported `--rarity` |
| :--- | :--- | :--- |
| **`cgss`** | `jp` | `n`, `r`, `sr`, `ssr` |
| **`mltd`** | `jp` | `n`, `r`, `sr`, `ssr` |
| **`pjsk`** | `jp`, `en`, `tw`, `kr`, `cn` | `1`, `2`, `r` (`1`+`2`), `3`/`sr`, `4`/`ssr`, `bd`/`birthday` |
| **`holodori`** | `jp` | `3`, `4`/`sr`, `5`/`ssr` |
| **`bandori`** | `jp`, `en`, `tw`, `cn`, `kr` | `n`/`1`, `r`/`2`, `sr`/`3`, `ssr`/`4`, `5` |
| **`ournotes`** | `hk-tw-mo` *(alias: `tw`)*, `en`, `jp` | `r`/`2`, `sr`/`3`, `ssr`/`4`, `ex` *(10)*, `bd` *(20)* |
| **`yumesute`** | `jp` | Cards: `1`/`n`, `2`/`r`, `3`/`sr`, `4`/`ssr` *(animated `15xxxx` cards share `rarity=4`)*; Posters: `r`/`2`, `sr`/`3`, `ssr`/`4`, `ur` |
| **`assaultlily`** | `jp` | `r`/`3`, `sr`/`4`, `ssr`/`5`, `ur`/`6`, `lg`/`7`, `8`, `9`, `10` |

### Deep Dive: `--card-animation` Special Mode (`yumesute` & `assaultlily`)
* **`yumesute` (Animated Actor Cards)**
  * Scans the Unity Addressables catalog (`charactercards_assets_charactercard`) for cards containing live animated prefabs: **4★ SSR awakened (`4xxxx_1`)** and the **5★-equivalent `15xxxx` series (`_0.._3`)** (`--animated-only` applies the exact same filter).
  * Extracts into `downloads/yumesute/card_animation/<cid>_r<rar>_<actor>/<variant>/`:
    * `textures/` — Full `1920x1180` illustration + depth cutout layers + FX sprite sheets + alpha masks
    * `animation_meta.json` — `UIParticle`, `Animator`/`AnimationClip`, and Holo shader properties (`_HoloTex`, `_MaskTex`, etc.)
    * `<variant>.bundle` — Raw UnityFS bundle (omitted when `--no-raw-bundle` is set)
* **`assaultlily` (Animated Memoria Prefabs & Emoria Spine 3.6)**
  * Discovers `asset_bundle/card_prefab/card_*` entries from A.RA.YA masterdata and fetches them from `allb.tqlwsl.moe`.
  * Extracts into `downloads/assaultlily/card_animation/<key>_<rtag>_<name>/`:
    * `textures/` — High-resolution `2048x2048` sprite atlases and VFX textures
    * `spine/` *(**Emoria** cards)* — Complete **Spine 3.6** assets (`.skel`, `.atlas`, `.png`)
    * `card_preview.jpg` — 800x600 preview JPG (when indexed in the image catalog)
    * `animation_meta.json` — Extracted AnimationClips, Canvas hierarchy, MonoBehaviours & Materials
    * `card_<key>.bundle` — Raw UnityFS bundle (omitted when `--no-raw-bundle` is set)

---

<a id="examples"></a>
## 5. Usage Examples

### 1) Inspect Supported Games & Help
```bash
python3 main.py --list-games
python3 main.py --help
```

### 2) Standard Asset Downloads & Filtering
```bash
# Sample 2 items per category from Project SEKAI and Bandori
python3 main.py --game pjsk bandori --category all --limit 2

# Download only SSR cards of Shimamura Uzuki in CGSS
python3 main.py --game cgss --category card --rarity ssr --character uzuki --limit 5

# Download BanG Dream! Our Notes cards from the HK/TW/MO region
python3 main.py --game ournotes --region hk-tw-mo --category card --limit 5

# Download hololive Dreams Cubism 5 Live2D models for Tokino Sora using .venv
.venv/bin/python main.py --game holodori --category live2d --character sora --limit 2
```

### 3) Animated Cards (`yumesute` & `assaultlily` Special Mode)
```bash
# Download 2 animated card samples each for Yumesute and Assault Lily
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --limit 2

# Download static cards (filtered to animated-capable cards only) together with animated bundles
.venv/bin/python main.py --game yumesute assaultlily --category card --card-animation --animated-only --limit 2

# Download an Assault Lily Emoria animated card (includes full Spine 3.6 rig)
.venv/bin/python main.py --game assaultlily --category card_animation --character 80000001

# Extract PNGs, Spine rigs & JSON metadata only without keeping raw .bundle files
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --no-raw-bundle --limit 2
```

### 4) Download & Auto-Sync to Google Drive
```bash
# Sample all 8 games (limit 2 per category) and upload to Google Drive (Work/AnimeGameAssets/)
.venv/bin/python main.py --game all --category all --limit 2 --upload-drive

# Sync Yumesute & Assault Lily animated cards to Google Drive
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --limit 2 --upload-drive

# Force .zip archiving per category and remove local files after successful upload
.venv/bin/python main.py --game pjsk --category live2d --upload-drive --drive-mode zip --cleanup-local

# Target a custom Google Drive Folder ID and overwrite existing remote files
.venv/bin/python main.py --game mltd --category card --upload-drive --drive-parent-id <FOLDER_ID> --drive-root-name MyAssets --overwrite-drive
```

---

<a id="references"></a>
## 6. Per-Game GitHub, API & CDN References

The table below lists every **GitHub repository**, **public API**, and **CDN endpoint** directly queried or architecturally referenced by each adapter:

| Game | GitHub Repositories Used / Referenced | Live API & CDN Endpoints | Purpose / Role |
| :--- | :--- | :--- | :--- |
| **`cgss`** | Reference codebase: [`summertriangle-dev/sparklebox`](https://github.com/summertriangle-dev/sparklebox) | API: `starlight.kirara.ca/api/v1/list/{card_t,char_t}`<br>CDN: `hidamarirhodonite.kirara.ca/{card,spread,icon_card,puchi}/` | Fetches card/idol metadata JSON and PNG assets directly from Starlight DB API & image mirror |
| **`mltd`** | Project GitHub org: [`matsurihi-me`](https://github.com/matsurihi-me) | API: `api.matsurihi.me/api/mltd/v2/{cards,idols}`<br>CDN: `storage.matsurihi.me/mltd/{card,card_bg_hq,icon_l}/` | Fetches card/idol metadata and high-resolution card/background PNGs directly from Matsurihi.me Princess Public API & Storage |
| **`pjsk`** | **Masterdata (by region)**:<br>• [`Sekai-World/sekai-master-db-diff`](https://github.com/Sekai-World/sekai-master-db-diff) (`jp`)<br>• [`Sekai-World/sekai-master-db-en-diff`](https://github.com/Sekai-World/sekai-master-db-en-diff) (`en`)<br>• [`Sekai-World/sekai-master-db-tc-diff`](https://github.com/Sekai-World/sekai-master-db-tc-diff) (`tw`)<br>• [`Sekai-World/sekai-master-db-kr-diff`](https://github.com/Sekai-World/sekai-master-db-kr-diff) (`kr`)<br>• [`Sekai-World/sekai-master-db-cn-diff`](https://github.com/Sekai-World/sekai-master-db-cn-diff) (`cn`)<br>Ecosystem references: [`StarMoe-org/Moesekai`](https://github.com/StarMoe-org/Moesekai), [`Sekai-World/sekai-viewer`](https://github.com/Sekai-World/sekai-viewer) | Cards/Cutouts CDN: `storage.pjsk.moe/sekai-{region}-assets/`<br>Live2D Index & Ripper: `assets.pjsk.moe/sekai-extra-assets/`<br>Icon Mirror: `moe.exmeaning.com/assets/` | Fetches `cards.json` and `gameCharacters.json` directly from Sekai-World GitHub repos, then downloads cards, cutouts, and Live2D models/motions via Moesekai (`_ripper.json`) |
| **`holodori`** | • [`HolodoriDB/holodori-db-jpn-diff`](https://github.com/HolodoriDB/holodori-db-jpn-diff) *(Masterdata)*<br>• [`HolodoriDB/holodori-asset-tools`](https://github.com/HolodoriDB/holodori-asset-tools) *(Octo Catalog & Crypto)* | GitHub Raw (`Card.json`, `Character.json`, `Costume.json`, `Lang*.json`) + Octo AssetBundle CDN via `holodori_asset_tools.catalog` & `crypto` | Fetches masterdata from HolodoriDB GitHub and uses `holodori-asset-tools` to resolve the Octo catalog, decrypt AES-encrypted bundles, and extract 2D/Cubism 5 assets with `UnityPy` |
| **`bandori`** | Reference structure: [`A-kirami/bestdori-live2d-downloader`](https://github.com/A-kirami/bestdori-live2d-downloader) | API: `bestdori.com/api/{cards,characters,costumes}/`<br>CDN: `bestdori.com/assets/{region}/` & `/res/icon/` | Fetches cards, trims, `livesd` sprites, and `buildData.asset` from Bestdori!, assembling `.moc` + `model.json` using the documented Live2D structure |
| **`ournotes`** | • [`StarMoe-org/moenotes-masterdata`](https://github.com/StarMoe-org/moenotes-masterdata) (`hk-tw-mo`, `en`, `jp`)<br>Parent project reference: [`StarMoe-org/moenotes`](https://github.com/StarMoe-org/moenotes) | Assets CDN: `assets.bdon.moe/{lang_prefix}/`<br>Live2D Manifest: `assets.bdon.moe/chart-site/models.json` | Fetches `MasterMemberCard.json`, `MasterSupportCard.json`, and `MasterCharacter.json` from `StarMoe-org/moenotes-masterdata`, and downloads images/Live2D models (merging chunked `.prefab.json`) from `assets.bdon.moe` |
| **`yumesute`** | • [`SonolusHaniwa/sirius-decrypted-data`](https://github.com/SonolusHaniwa/sirius-decrypted-data)<br>• [`wds-sirius/Adv-Resource`](https://github.com/wds-sirius/Adv-Resource)<br>• [`wds-sirius/asset-of-dreams`](https://github.com/wds-sirius/asset-of-dreams) | Official Unity Addressables CDN: `assets-e.wds-stellarium.com/production/2d-assets/Android/{ver}/` | • `sirius-decrypted-data`: `card.json`, `master/*.json` & 1920x1180 card PNGs (`0.png`, `1.png`, `cover*.png`)<br>• `Adv-Resource`: Spine 4.1 (`manifest/Spine.json`, `spine/*.{skel,atlas,png}`), cutouts, icons, `_temp/2dcatalog.json` fallback<br>• `asset-of-dreams`: `config.yml` for live `asset_version` to fetch `catalog_{ver}.json.br`, Animated Actor Cards, Full Posters & Signatures from the live CDN |
| **`assaultlily`** | • [`LaTlcia/A.RA.YA`](https://github.com/LaTlcia/A.RA.YA) *(MasterdataBase & Asset Catalog)*<br>• [`czk200518-hash/AssaultLily-deskpet`](https://github.com/czk200518-hash/AssaultLily-deskpet) *(Spine Samples)*<br>Tooling reference: [`LaTlcia/ArayaToolbox`](https://github.com/LaTlcia/ArayaToolbox) | Cards/Bundles CDN: `allb.tqlwsl.moe/` (`Image/Card/`, `asset_bundle/card_prefab/`)<br>Asset Mirror: `allb.game-db.tw/images/` | • `LaTlcia/A.RA.YA`: Card/character/job masterdata plus `asset_bundle/card_prefab/*` & `Image/Card/*` catalogs<br>• `czk200518-hash/AssaultLily-deskpet`: Sample `CharacterJobSpine*` Spine rigs<br>• `allb.tqlwsl.moe` & `allb.game-db.tw`: Full 800x600 Memoria JPGs, 256x256 PNGs, `@2x` costume art & Animated Memoria `.bundle` prefabs (incl. Emoria Spine 3.6) |

---

<a id="copyright"></a>
## 7. Official Copyright Notices & Legal Disclaimer

All game artwork, illustrations, character designs, 2D/3D models, scenario texts, and masterdata remain the **exclusive intellectual property and trademarks of their respective owners**. This repository neither claims ownership over nor hosts any copyrighted game media.

### Per-Game Copyright & Rights Holders

| Code | Official Title | Rights Holders / Developers & Publishers | Official Copyright Notice |
| :--- | :--- | :--- | :--- |
| **`cgss`** | アイドルマスター シンデレラガールズ スターライトステージ *(THE iDOLM@STER Cinderella Girls: Starlight Stage)* | **Bandai Namco Entertainment Inc.** *(Developed with Cygames, Inc.)* | `THE IDOLM@STER™ & © Bandai Namco Entertainment Inc.` |
| **`mltd`** | アイドルマスター ミリオンライブ！ シアターデイズ *(THE iDOLM@STER Million Live! Theater Days)* | **Toshiyuki Kubooka** / **Bandai Namco Entertainment Inc.** | `© 窪岡俊之 THE IDOLM@STER™ & © Bandai Namco Entertainment Inc.` |
| **`pjsk`** | プロジェクトセカイ カラフルステージ！ feat. 初音ミク *(Project SEKAI COLORFUL STAGE! feat. Hatsune Miku)* | **SEGA Corporation** / **Colorful Palette Inc.** / **Crypton Future Media, INC.** *(www.piapro.net)* | `© SEGA / © Colorful Palette Inc. / © Crypton Future Media, INC. www.piapro.net` |
| **`holodori`** | hololive Dreams *(ホロライブドリームズ)* | **COVER Corporation** / **QualiArts, Inc.** | `© COVER / © QualiArts, Inc.` |
| **`bandori`** | バンドリ！ ガールズバンドパーティ！ *(BanG Dream! Girls Band Party!)* | **BanG Dream! Project** / **Bushiroad Inc.** *(Originally co-developed with Craft Egg Inc.; development transferred to Bushiroad in Jan 2024)* | `© BanG Dream! Project © Craft Egg Inc. © bushiroad All Rights Reserved.` |
| **`ournotes`** | バンドリ！ アワーノーツ *(BanG Dream! Our Notes)* | **BanG Dream! Project** / **FROMTOKYO Inc.** / **Bushiroad Inc.** *(Global publishing by BILIBILI HK LIMITED)* | `© BanG Dream! Project © FROMTOKYO © bushiroad All Rights Reserved.` |
| **`yumesute`** | ワールドダイスター 夢のステラリウム *(World Dai Star: Yume no Stellarium)* | **Sirius / Project WDS** / **KMS, inc.** | `© Sirius / Project WDS Developed and Published by KMS, inc.` |
| **`assaultlily`** | アサルトリリィ Last Bullet *(Assault Lily: Last Bullet)* | **AZONE INTERNATIONAL・acus / Assault Lily Project** / **WFS / Pokelabo, Inc.** *(JP development & operations transferred to KING PAWN Inc. in Dec 2025)* / **SHAFT Inc.** | `© AZONE INTERNATIONAL・acus / アサルトリリィプロジェクト © WFS © Pokelabo, Inc. © SHAFT` |

### Legal Disclaimer & Third-Party Licenses
1. **Unofficial Community Tool**: This project is an independent open-source utility and is **not affiliated with, endorsed by, or sponsored by** any of the publishers or IP holders listed above.
2. **Personal, Research & Archival Use Only**: Downloaded assets are strictly for personal backup, educational study, and non-commercial research/archival purposes. Do **not** redistribute, resell, mint, or commercially exploit any extracted assets or violate the respective games' Terms of Service.
3. **Third-Party Open-Source Libraries**:
   * All Python scripts authored in this repository (`main.py`, `core/*`, `games/*`) are standalone wrappers fetching/parsing publicly accessible data.
   * Optional dependencies and referenced community repositories carry their own licenses—including `A-kirami/bestdori-live2d-downloader` (**MIT**), `HolodoriDB/holodori-asset-tools` (**GPL-3.0**, only required when optionally installed for `holodori`), `czk200518-hash/AssaultLily-deskpet` (**GPL-3.0**), `Sekai-World/sekai-viewer` (**GPL-3.0**), `StarMoe-org/Moesekai` & `StarMoe-org/moenotes` (**AGPL-3.0**), as well as **UnityPy**, **Pillow**, and **brotli** under their respective licenses.
