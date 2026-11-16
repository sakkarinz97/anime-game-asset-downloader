# Anime Game Masterdata & Asset Downloader

**Language / ภาษา:** [🇹🇭 ภาษาไทย](README.th.md) | [🇺🇸 English](README.md)

เครื่องมือ CLI ภาษา Python สำหรับดึง **Masterdata JSON** และดาวน์โหลด/แตกไฟล์ **Assets ความละเอียดสูงสุด** จากเกมไอดอล, ดนตรี, และอนิเมะ RPG 8 เกมยอดนิยม แยกเก็บเป็นสัดส่วนตามเกมและหมวดหมู่ พร้อมระบบอัปโหลดและซิงค์ขึ้น **Google Drive** อัตโนมัติ

> [!NOTE]
> โปรเจกต์นี้ออกแบบตามแนวทาง **Hybrid Architecture (Approach 2)**: เก็บเฉพาะซอร์สโค้ด Python บน **GitHub** (`sakkarinz97/anime-game-asset-downloader`) และแยกเก็บไฟล์ภาพ โมเดล Live2D/Spine และ Unity AssetBundle ขนาดใหญ่ไว้ใน **Google Drive** (`Work/AnimeGameAssets/`) ผ่าน `.gitignore`

---

## สารบัญ

1. [โปรเจกต์นี้คืออะไร? และภาพรวมสถาปัตยกรรม](#overview)
2. [รายชื่อเกมทั้ง 8 เกม & สิ่งที่ดาวน์โหลดได้](#games)
3. [ความต้องการของระบบและการติดตั้ง](#install)
4. [คู่มือคำสั่งและการใช้งาน CLI ทั้งหมด](#cli)
5. [ตัวอย่างคำสั่งใช้งานจริง](#examples)
6. [Reference แหล่งข้อมูล GitHub, API และ CDN ของแต่ละเกม](#references)
7. [ข้อมูลลิขสิทธิ์ของแต่ละเกมและข้อจำกัดการใช้งาน](#copyright)

---

<a id="overview"></a>
## 1. โปรเจกต์นี้คืออะไร? และภาพรวมสถาปัตยกรรม

**Anime Game Masterdata & Asset Downloader** เป็นสคริปต์รวมศูนย์ (`main.py` / `anime-dl`) ที่รวม **Adapter ของ 8 เกม** ไว้ในคำสั่งเดียว รองรับตั้งแต่เกมที่โหลดผ่าน HTTP JSON/PNG โดยตรง ไปจนถึงเกมที่ต้องถอดรหัส AES และแตกไฟล์ UnityFS AssetBundle + Shader/Animation ด้วย `UnityPy`

### หมวดหมู่ Asset ที่รองรับ
1. **`card`** — ภาพการ์ด / Memoria ความละเอียดสูงสุด (ทั้งก่อนและหลัง Awaken / Training, ภาพพื้นหลังเต็มใบ HQ, Cutout และ Cover เมื่อมี)
2. **`live2d`** — ไฟล์โมเดลตัวละคร 2 มิติ (Live2D Cubism 2/3/4/5 พร้อม `.moc`/`.moc3`, `model.json`/`model3.json`, textures, physics, expressions และ motions; ส่วนเกมที่ใช้ **Spine** จะดาวน์โหลดเป็น `.skel` / `.atlas` / `.png` ลงในโฟลเดอร์ `spine/` โดยอัตโนมัติ)
3. **`character`** — ภาพตัวละครยืน (Standing / Full Cutout / Chibi `puchi`/`livesd`), ไอคอนตัวละคร, ลายเซ็น และ Poster ความละเอียดสูง
4. **`card_animation`** *(โหมดพิเศษเฉพาะ **`yumesute`** และ **`assaultlily`**)* — ดึงและแตกไฟล์การ์ดเวอร์ชัน Animation จาก UnityFS AssetBundle ออกมาเป็นเลเยอร์ภาพ, FX Sprite Sheets, Mask, Emoria Spine 3.6 และ `animation_meta.json` (เลือกได้ทั้งเก็บหรือไม่เก็บไฟล์ `.bundle` ดิบ)
5. **`all`** — รันหมวดมาตรฐานทั้ง 3 หมวด (`card`, `live2d`, `character`) ต่อเนื่องในคำสั่งเดียว (และสามารถพ่วง `--card-animation` เพื่อแถม `card_animation` ให้เกมที่รองรับได้ทันที)

### โครงสร้างไฟล์ของโปรเจกต์และผลลัพธ์

```text
anime-game-asset-downloader/
├── main.py                  # CLI หลัก (entrypoint `anime-dl`)
├── pyproject.toml           # การตั้งค่าแพ็กเกจ Python & optional extras
├── requirements.txt         # ไลบรารีเสริมสำหรับถอดรหัสและแตก UnityFS bundle
├── core/
│   ├── base.py              # Base adapter contract, DownloadOptions, CategoryResult
│   ├── http_client.py       # HTTP downloader พร้อม retry, exponential backoff & HTML-404 guard
│   ├── unity_utils.py       # ตัวแตก UnityPy Texture2D, TextAsset, Spine 3.6 & Animated Card Bundle
│   └── drive_sync.py        # ระบบซิงค์ไฟล์เข้า Google Drive ผ่าน `gdrive` CLI
├── games/
│   ├── __init__.py          # Registry ของเกมทั้ง 8 เกม (`ADAPTERS`)
│   ├── cgss.py              # THE iDOLM@STER Cinderella Girls: Starlight Stage
│   ├── mltd.py              # THE iDOLM@STER Million Live! Theater Days
│   ├── pjsk.py              # Project SEKAI COLORFUL STAGE! feat. Hatsune Miku
│   ├── holodori.py          # hololive Dreams
│   ├── bandori.py           # BanG Dream! Girls Band Party!
│   ├── ournotes.py          # BanG Dream! Our Notes
│   ├── yumesute.py          # World Dai Star: Yume no Stellarium
│   └── assaultlily.py       # Assault Lily: Last Bullet
└── downloads/               # (ถูก .gitignore) โฟลเดอร์เก็บ masterdata & assets บนเครื่อง
    └── <game_code>/
        ├── masterdata/      # แคชไฟล์ JSON / Catalog จากต้นทาง
        ├── card/
        ├── card_animation/  # (yumesute, assaultlily)
        ├── live2d/          # (หรือ `spine/` สำหรับ yumesute, assaultlily)
        └── character/
```

เมื่อเปิดใช้ `--upload-drive` ระบบจะสร้างโครงสร้างโฟลเดอร์ปลายทางบน **Google Drive** ดังนี้:

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
## 2. รายชื่อเกมทั้ง 8 เกม & สิ่งที่ดาวน์โหลดได้

| รหัส (`--game`) | ชื่อเกม | `--region` ที่รองรับ | `card` | `card_animation` *(พิเศษ)* | `live2d` / `spine` | `character` |
| :--- | :--- | :--- | :--- | :---: | :--- | :--- |
| **`cgss`** | THE iDOLM@STER Cinderella Girls: Starlight Stage | `jp` | PNG การ์ด (`card`) + ภาพเต็มแนวนอน (`spread`) | — | ❌ *(ในเกมใช้โมเดล 3D และ 2D Puchi ไม่มี Live2D)* | ไอคอนการ์ด (`icon_card`) + ตัวจิ๋ว `puchi` |
| **`mltd`** | THE iDOLM@STER Million Live! Theater Days | `jp` | การ์ดแบบมีกรอบ/ไร้กรอบ (`framed`/`clean`) + พื้นหลัง `card_bg_hq` (ปกติ & Awake) | — | ❌ *(ในเกมใช้โมเดล 3D ไม่มี Live2D)* | พอร์ตเทรตไอคอนใหญ่ (`icon_l`) ปกติ & Awake |
| **`pjsk`** | プロジェクトセカイ カラフルステージ！ feat. 初音ミク | `jp`, `en`, `tw`, `kr`, `cn` | `card_normal.png` + `card_after_training.png` (ตั้งแต่ ★3 ขึ้นไป) | — | ✅ **Cubism 3/4** (`.moc3`, `.model3.json`, textures, motions จาก `_ripper.json`) | Cutout พื้นใส (`cutout`, `cutout_trm`) + Character Icons |
| **`holodori`** | hololive Dreams (`holodori`) | `jp` | ถอดรหัส Octo AES + UnityPy: Full `2048x1024` + Vertical (`vert`) | — | ✅ **Cubism 5** (`.moc3`, `.model3.json`, 4K textures, `physics3.json`, `.exp3.json`, `_shared_motions`) | Full 2D Standing (`4096x4096`) + `icon_mini` + `key_band` |
| **`bandori`** | BanG Dream! Girls Band Party! | `jp`, `en`, `tw`, `cn`, `kr` | `card_normal.png` + `card_after_training.png` (ตั้งแต่ ★3 ขึ้นไป) | — | ✅ **Cubism 2** (`.moc`, `model.json`, `physics.json`, motions, expressions) | Cutout Trim + ตัวจิ๋ว `livesd` + Character Icons |
| **`ournotes`** | BanG Dream! Our Notes | `hk-tw-mo` *(หรือ `tw`)*, `en`, `jp` | Member Card (`member_full`, `member_background`) + Support Card (`snap_full`) | — | ✅ **Cubism 3/4** (โหลดตาม manifest และรวม chunked `.prefab.json` ให้อัตโนมัติ) | `character_sprite`, `character_thumbnail`, `character_face_icon` + `member_character` Cutout |
| **`yumesute`** | World Dai Star: Yume no Stellarium (`Yumesute`) | `jp` | Full-Res `1920x1180` (`0.png`/`1.png`, `cover0`/`cover1`) + Transparent Cutout | 🎬 **Animated Actor Cards** (`4★ SSR _1` & ซีรีส์ `15xxxx`): ภาพ 1920x1180 + Multi-layer + FX Sprite Sheet + Mask + Shader/Holo JSON + `.bundle` | 🦴 **Spine 4.1** (`.skel`, `.atlas`, `.png` — บันทึกลง `spine/`) | Card/Poster Icons + *(ถ้ามี `UnityPy`+`brotli`)* Full Posters `1357x1920` & ลายเซ็นจาก Live CDN |
| **`assaultlily`** | アサルトリリィ Last Bullet | `jp` | Full JPG `800x600` (`full/`) + 256x256 PNG + `memoria_ultimate` (ตั้งแต่ ★6/ปลุกพลังไม่จำกัด) | 🎬 **Animated Memoria Prefabs** (`card_prefab`): Atlases `2048x2048` + VFX Sprites + Emoria **Spine 3.6** (`.skel`/`.atlas`/`.png`) + `card_preview.jpg` + `animation_meta.json` + `.bundle` | 🦴 **Spine Samples** (`.skel`, `.atlas`, `.png` `CharacterJobSpine*` — บันทึกลง `spine/`) | Portraits (`chara`) + Costume Standing `@2x` (`900x1550`) + Full Illus (`1536x1174` JPG) + `job_icon` |

> [!TIP]
> * เกม **`yumesute`** และ **`assaultlily`** ใช้ **Spine** ไม่ใช่ Live2D Cubism ดังนั้นเมื่อเรียก `--category live2d` ระบบจะดาวน์โหลดไฟล์ Spine ลงในโฟลเดอร์ `spine/` ของเกมนั้นแทนเพื่อให้สอดคล้องกับเอนจินจริง
> * สำหรับ `yumesute`, `assaultlily`, และ `holodori` ที่ต้องแตกรวมหรือถอดรหัส Unity AssetBundle ระบบมี rate limiting และ retry อัตโนมัติเพื่อป้องกันเซิร์ฟเวอร์ CDN บล็อก

---

<a id="install"></a>
## 3. ความต้องการของระบบและการติดตั้ง

* **Python เวอร์ชัน `>= 3.10`**

### แบบที่ 1: โหมดพื้นฐาน (Python Standard Library ล้วน)
เหมาะสำหรับเกม **`cgss`**, **`mltd`**, **`pjsk`**, **`bandori`**, **`ournotes`**, ส่วนภาพการ์ด/ตัวละคร/Spine sample ของ **`assaultlily`**, และส่วนการ์ด/ไอคอน/Spine 4.1 บน GitHub ของ **`yumesute`** — **ไม่จำเป็นต้องติดตั้งแพ็กเกจเสริม** รันได้ทันที:

```bash
git clone https://github.com/sakkarinz97/anime-game-asset-downloader.git
cd anime-game-asset-downloader
python3 main.py --list-games
```

### แบบที่ 2: โหมดเต็มรูปแบบ (รองรับ `holodori`, Live CDN ของ `yumesute`, และ `--card-animation`)
จำเป็นต้องติดตั้งไลบรารีสำหรับถอดรหัสและแตกไฟล์ UnityFS (`Pillow`, `UnityPy`, `brotli`, `holodori-asset-tools`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

หรือติดตั้งในรูปแบบแพ็กเกจ (ได้คำสั่ง `anime-dl` ไว้เรียกใช้จากทุกที่):

```bash
pip install -e ".[all]"
# หรือเลือกเฉพาะชุดที่ต้องการ: ".[unity]" หรือ ".[holodori]"
```

### เงื่อนไขเพิ่มเติมสำหรับ Google Drive Sync (`--upload-drive`)
ต้องมีคำสั่ง `gdrive` CLI อยู่บน `PATH` (หรือ `/opt/antigravity/bin/gdrive`) และผ่านการเชื่อมต่อบัญชี Google Drive แล้ว สามารถทดสอบได้ด้วย `gdrive auth status`

---

<a id="cli"></a>
## 4. คู่มือคำสั่งและการใช้งาน CLI ทั้งหมด

สามารถเรียกใช้งานผ่าน `python3 main.py [OPTIONS]` หรือ `anime-dl [OPTIONS]` (หากติดตั้งด้วย `pip install -e .`)

### พารามิเตอร์ทั้งหมด

| คำสั่ง / Flag | ค่าเริ่มต้น | ตัวเลือก / รูปแบบ | คำอธิบาย |
| :--- | :--- | :--- | :--- |
| `-h`, `--help` | `False` | Flag | แสดงวิธีใช้งานและรายการพารามิเตอร์ทั้งหมดแล้วออก |
| `--list-games` | `False` | Flag | แสดงรายชื่อเกมทั้ง 8 เกม โซนที่รองรับ การรองรับ `AnimCard` และเครดิตแหล่งข้อมูลแล้วออก |
| `--game` | `all` | `cgss`, `mltd`, `pjsk`, `holodori`, `bandori`, `ournotes`, `yumesute`, `assaultlily`, `all` | เลือกเกมที่ต้องการ (ระบุหลายเกมคั่นด้วยช่องว่างหรือเครื่องหมาย `,` เช่น `--game pjsk,bandori` หรือ `--game pjsk bandori`) |
| `--category` | `all` | `card`, `live2d`, `character`, `card_animation`, `all` | เลือกหมวด Asset (`all` = `card` + `live2d` + `character`) |
| `--card-animation` | `False` | Flag | *(พิเศษเฉพาะ `yumesute`, `assaultlily`)* สั่งโหลดหมวด `card_animation` เพิ่มเติมควบคู่กับ `--category` ที่เลือก |
| `--animated-only` | `False` | Flag | *(พิเศษเฉพาะ `yumesute`, `assaultlily`)* กรองเฉพาะการ์ดที่มีเวอร์ชัน Animation ในหมวด `card` / `card_animation` |
| `--no-raw-bundle` | `False` | Flag | ข้ามการเก็บไฟล์ UnityFS `.bundle` ดิบตอนแตก `card_animation` (เก็บเฉพาะภาพ PNG, Spine, `card_preview.jpg` และ `animation_meta.json` เพื่อประหยัดพื้นที่) |
| `--region` | `jp` | ดูตารางด้านล่าง | เลือกโซนเซิร์ฟเวอร์ (มีผลเฉพาะเกมที่รองรับหลายเซิร์ฟเวอร์) |
| `--rarity` | `None` | ดูตารางด้านล่าง | กรองระดับความหายากของตัวการ์ด/ไอเท็ม |
| `--character` | `None` | ข้อความ / ID | กรองจากชื่อตัวละคร (อังกฤษ/โรมันจิ/ญี่ปุ่น/เกาหลี/จีน) ชื่อการ์ด หรือรหัส ID (substring match) |
| `--limit` | `None` | ตัวเลขจำนวนเต็ม | จำกัดจำนวนรายการที่โหลดต่อหมวดของแต่ละเกม (เหมาะสำหรับทดสอบหรือสุ่มตัวอย่าง) |
| `--threads` | `8` | ตัวเลขจำนวนเต็ม | จำนวนเธรดดาวน์โหลดพร้อมกัน *(ส่วน Unity CDN ของ `yumesute`/`assaultlily` จะถูกจำกัดที่ ≤ 2-3 เธรดอัตโนมัติเพื่อความเสถียร)* |
| `--out-dir` | `./downloads` | Path | โฟลเดอร์ปลายทางสำหรับเก็บไฟล์ในเครื่อง |
| `--refresh-masterdata` | `False` | Flag | บังคับโหลด Masterdata JSON และ Asset Catalog จากต้นทางใหม่แทนการใช้แคชเดิม |
| `--upload-drive` | `False` | Flag | ซิงค์ไฟล์ที่โหลดขึ้น Google Drive ทันทีหลังจบแต่ละหมวด |
| `--drive-parent-id` | `1kaSiYfkeaFXvXQQbZlFKJV4Tq--M5yFf` | Drive Folder ID | Folder ID ปลายทางบน Google Drive (ค่าเริ่มต้นคือโฟลเดอร์ `Work/`) |
| `--drive-root-name` | `AnimeGameAssets` | ชื่อโฟลเดอร์ | ชื่อโฟลเดอร์หลักที่จะสร้าง/อ้างอิงภายใน `--drive-parent-id` |
| `--drive-mode` | `auto` | `auto`, `direct`, `zip` | รูปแบบอัปโหลดขึ้น Drive: `direct` (ทีละไฟล์ตามโครงสร้างโฟลเดอร์), `zip` (บีบอัดเป็น `<game>_<cat>.zip`), `auto` (`direct` เมื่อมี ≤ 40 ไฟล์ มิฉะนั้นแพ็กเป็น `.zip`) |
| `--cleanup-local` | `False` | Flag | ลบไฟล์หมวดนั้นในเครื่องหลังอัปโหลดขึ้น Google Drive สำเร็จ |
| `--overwrite-drive` | `False` | Flag | อัปเดตทับไฟล์เดิมบน Google Drive หากมีชื่อไฟล์ซ้ำอยู่แล้ว |

### ค่า `--region` และ `--rarity` ที่รองรับในแต่ละเกม

| เกม | `--region` ที่รองรับ | `--rarity` ที่รองรับ |
| :--- | :--- | :--- |
| **`cgss`** | `jp` | `n`, `r`, `sr`, `ssr` |
| **`mltd`** | `jp` | `n`, `r`, `sr`, `ssr` |
| **`pjsk`** | `jp`, `en`, `tw`, `kr`, `cn` | `1`, `2`, `r` (`1`+`2`), `3`/`sr`, `4`/`ssr`, `bd`/`birthday` |
| **`holodori`** | `jp` | `3`, `4`/`sr`, `5`/`ssr` |
| **`bandori`** | `jp`, `en`, `tw`, `cn`, `kr` | `n`/`1`, `r`/`2`, `sr`/`3`, `ssr`/`4`, `5` |
| **`ournotes`** | `hk-tw-mo` *(alias: `tw`)*, `en`, `jp` | `r`/`2`, `sr`/`3`, `ssr`/`4`, `ex` *(10)*, `bd` *(20)* |
| **`yumesute`** | `jp` | การ์ด: `1`/`n`, `2`/`r`, `3`/`sr`, `4`/`ssr` *(ซีรีส์ `15xxxx` อยู่ใน `rarity=4`)*; Poster: `r`/`2`, `sr`/`3`, `ssr`/`4`, `ur` |
| **`assaultlily`** | `jp` | `r`/`3`, `sr`/`4`, `ssr`/`5`, `ur`/`6`, `lg`/`7`, `8`, `9`, `10` |

### รายละเอียดโหมดพิเศษ `--card-animation` (`yumesute` & `assaultlily`)
* **`yumesute` (Animated Actor Cards)**
  * ค้นหา AssetBundle ใน Addressables Catalog กลุ่ม `charactercards_assets_charactercard` เฉพาะการ์ดที่มีแอนิเมชันจริง ได้แก่ **4★ SSR Awakened (`4xxxx_1`)** และ **ซีรีส์ `15xxxx` (`_0.._3`)** (ตัวเลือก `--animated-only` จะกรองให้ตรงกับชุดนี้เช่นกัน)
  * เมื่อแตกไฟล์ลง `downloads/yumesute/card_animation/<cid>_r<rar>_<actor>/<variant>/` จะได้:
    * `textures/` — ภาพการ์ด `1920x1180` + เลเยอร์แยกชิ้นส่วน + FX Sprite Sheets + Alpha Mask
    * `animation_meta.json` — ข้อมูล `UIParticle`, `Animator`/`AnimationClip`, Holo Shader Properties (`_HoloTex`, `_MaskTex` ฯลฯ)
    * `<variant>.bundle` — ไฟล์ UnityFS ดิบ (ยกเว้นใส่ `--no-raw-bundle`)
* **`assaultlily` (Animated Memoria Prefabs & Emoria Spine 3.6)**
  * อ่านรายการ `asset_bundle/card_prefab/card_*` จาก Masterdata ของ A.RA.YA แล้วดึงจาก `allb.tqlwsl.moe`
  * เมื่อแตกไฟล์ลง `downloads/assaultlily/card_animation/<key>_<rtag>_<name>/` จะได้:
    * `textures/` — Sprite Atlas ความละเอียดสูง (`2048x2048`) และ Texture VFX
    * `spine/` *(เฉพาะการ์ดซีรีส์ **Emoria**)* — ไฟล์ **Spine 3.6** ครบชุด (`.skel`, `.atlas`, `.png`) พร้อมคำอธิบายเฟรมในเมตาดาตา
    * `card_preview.jpg` — ภาพพรีวิว JPG ของการ์ด (เมื่อพบในแคตตาล็อก)
    * `animation_meta.json` — ข้อมูล AnimationClip / Canvas / MonoBehaviour / Material
    * `card_<key>.bundle` — ไฟล์ UnityFS ดิบ (ยกเว้นใส่ `--no-raw-bundle`)

---

<a id="examples"></a>
## 5. ตัวอย่างคำสั่งใช้งานจริง

### 1) ดูรายชื่อเกมทั้งหมดและคู่มือ
```bash
python3 main.py --list-games
python3 main.py --help
```

### 2) ดาวน์โหลดพื้นฐานและกรองเฉพาะตัวละคร/ความหายาก
```bash
# ทดลองโหลด Project SEKAI (EN) และ Bandori (JP) อย่างละ 2 รายการต่อหมวด
python3 main.py --game pjsk bandori --category all --limit 2

# โหลดเฉพาะการ์ด SSR ของ Shimamura Uzuki ใน CGSS
python3 main.py --game cgss --category card --rarity ssr --character uzuki --limit 5

# โหลดเฉพาะภาพการ์ดของ BanG Dream! Our Notes เซิร์ฟเวอร์ไต้หวัน/ฮ่องกง/มาเก๊า
python3 main.py --game ournotes --region hk-tw-mo --category card --limit 5

# โหลด Live2D ของ hololive Dreams (เช่น Tokino Sora) โดยใช้ .venv
.venv/bin/python main.py --game holodori --category live2d --character sora --limit 2
```

### 3) โหลดการ์ดเวอร์ชัน Animation (พิเศษเฉพาะ `yumesute` & `assaultlily`)
```bash
# โหลดเฉพาะการ์ด Animation ของทั้ง 2 เกม อย่างละ 2 รายการ
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --limit 2

# โหลดภาพการ์ดนิ่ง (เฉพาะใบที่มี animation) + แตกเวอร์ชัน animation พร้อมกัน
.venv/bin/python main.py --game yumesute assaultlily --category card --card-animation --animated-only --limit 2

# โหลดการ์ด Emoria (Spine 3.6 เต็มชุด) ของ Assault Lily
.venv/bin/python main.py --game assaultlily --category card_animation --character 80000001

# แตกเฉพาะไฟล์ภาพ/Spine/JSON โดยไม่เก็บไฟล์ .bundle ดิบ (ประหยัดพื้นที่)
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --no-raw-bundle --limit 2
```

### 4) ดาวน์โหลดและซิงค์ขึ้น Google Drive อัตโนมัติ
```bash
# โหลดทุกเกมทุกหมวด (จำกัดอย่างละ 2 รายการ) แล้วซิงค์ขึ้น Google Drive โฟลเดอร์ Work/AnimeGameAssets/
.venv/bin/python main.py --game all --category all --limit 2 --upload-drive

# ซิงค์การ์ด Animation ของ Yumesute และ Assault Lily ขึ้น Drive
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --limit 2 --upload-drive

# บังคับแพ็กเป็น .zip ก่อนอัปโหลด และลบไฟล์ชั่วคราวในเครื่องหลังอัปโหลดเสร็จ
.venv/bin/python main.py --game pjsk --category live2d --upload-drive --drive-mode zip --cleanup-local

# ระบุ Folder ID ปลายทางบน Drive เอง และบังคับเขียนทับไฟล์เดิม
.venv/bin/python main.py --game mltd --category card --upload-drive --drive-parent-id <FOLDER_ID> --drive-root-name MyAssets --overwrite-drive
```

---

<a id="references"></a>
## 6. Reference แหล่งข้อมูล GitHub, API และ CDN ของแต่ละเกม

ตารางและรายละเอียดด้านล่างแสดง **GitHub Repositories**, **API Endpoints**, และ **CDN** ที่โค้ดในโปรเจกต์นี้เชื่อมต่อหรือนำโครงสร้างมาอ้างอิงจริง:

| เกม | GitHub Repositories ที่ใช้งาน / อ้างอิงในโปรเจกต์ | API / CDN ปลายทางที่ดึงไฟล์จริง | บทบาทของแต่ละแหล่งข้อมูล |
| :--- | :--- | :--- | :--- |
| **`cgss`** | อ้างอิงระบบฐานข้อมูล: [`summertriangle-dev/sparklebox`](https://github.com/summertriangle-dev/sparklebox) | API: `starlight.kirara.ca/api/v1/list/{card_t,char_t}`<br>CDN: `hidamarirhodonite.kirara.ca/{card,spread,icon_card,puchi}/` | ดึง Masterdata รายชื่อการ์ด/ไอดอล และไฟล์ PNG ผ่าน API & Image Mirror ของ Starlight DB โดยตรง |
| **`mltd`** | องค์กรต้นทาง API: [`matsurihi-me`](https://github.com/matsurihi-me) | API: `api.matsurihi.me/api/mltd/v2/{cards,idols}`<br>CDN: `storage.matsurihi.me/mltd/{card,card_bg_hq,icon_l}/` | ดึงข้อมูลการ์ด/ไอดอลและภาพความละเอียดสูงตรงจาก Matsurihi.me Princess Public API & Storage |
| **`pjsk`** | **Masterdata (เลือกตามโซน)**:<br>• [`Sekai-World/sekai-master-db-diff`](https://github.com/Sekai-World/sekai-master-db-diff) (`jp`)<br>• [`Sekai-World/sekai-master-db-en-diff`](https://github.com/Sekai-World/sekai-master-db-en-diff) (`en`)<br>• [`Sekai-World/sekai-master-db-tc-diff`](https://github.com/Sekai-World/sekai-master-db-tc-diff) (`tw`)<br>• [`Sekai-World/sekai-master-db-kr-diff`](https://github.com/Sekai-World/sekai-master-db-kr-diff) (`kr`)<br>• [`Sekai-World/sekai-master-db-cn-diff`](https://github.com/Sekai-World/sekai-master-db-cn-diff) (`cn`)<br>อ้างอิงระบบนิเวศ: [`StarMoe-org/Moesekai`](https://github.com/StarMoe-org/Moesekai), [`Sekai-World/sekai-viewer`](https://github.com/Sekai-World/sekai-viewer) | CDN การ์ด/Cutout: `storage.pjsk.moe/sekai-{region}-assets/`<br>Live2D Index & Ripper: `assets.pjsk.moe/sekai-extra-assets/`<br>Icon Mirror: `moe.exmeaning.com/assets/` | ดึง `cards.json` และ `gameCharacters.json` ตรงจาก GitHub ของ Sekai-World แล้วโหลดการ์ด, Cutout และ Live2D (`_ripper.json`) จาก Moesekai |
| **`holodori`** | • [`HolodoriDB/holodori-db-jpn-diff`](https://github.com/HolodoriDB/holodori-db-jpn-diff) *(Masterdata)*<br>• [`HolodoriDB/holodori-asset-tools`](https://github.com/HolodoriDB/holodori-asset-tools) *(Octo Catalog & Crypto)* | GitHub Raw สำหรับ `Card.json`, `Character.json`, `Costume.json`, `Lang*.json` + Octo AssetBundle CDN ผ่าน `holodori_asset_tools.catalog` & `crypto` | ดึง Masterdata JSON จาก GitHub ของ HolodoriDB และใช้แพ็กเกจ `holodori-asset-tools` เพื่อโหลด Catalog, ถอดรหัส AES และสกัด Texture/Cubism 5 ด้วย UnityPy |
| **`bandori`** | อ้างอิงโครงสร้าง Live2D: [`A-kirami/bestdori-live2d-downloader`](https://github.com/A-kirami/bestdori-live2d-downloader) | API: `bestdori.com/api/{cards,characters,costumes}/`<br>CDN: `bestdori.com/assets/{region}/` & `/res/icon/` | ดึงการ์ด, Cutout, Live SD, และไฟล์ `buildData.asset` จาก Bestdori! แล้วนำแนวทางประกอบไฟล์ `.moc` + `model.json` ของ repo ดังกล่าวมาใช้ |
| **`ournotes`** | • [`StarMoe-org/moenotes-masterdata`](https://github.com/StarMoe-org/moenotes-masterdata) *(Masterdata 3 โซน: `hk-tw-mo`, `en`, `jp`)*<br>อ้างอิงโปรเจกต์แม่: [`StarMoe-org/moenotes`](https://github.com/StarMoe-org/moenotes) | CDN Assets: `assets.bdon.moe/{lang_prefix}/`<br>Live2D Manifest: `assets.bdon.moe/chart-site/models.json` | ดึง `MasterMemberCard.json`, `MasterSupportCard.json`, `MasterCharacter.json` จาก GitHub `StarMoe-org/moenotes-masterdata` และโหลดภาพ/Live2D (พร้อมรวม chunked `.prefab.json`) จาก `assets.bdon.moe` |
| **`yumesute`** | • [`SonolusHaniwa/sirius-decrypted-data`](https://github.com/SonolusHaniwa/sirius-decrypted-data)<br>• [`wds-sirius/Adv-Resource`](https://github.com/wds-sirius/Adv-Resource)<br>• [`wds-sirius/asset-of-dreams`](https://github.com/wds-sirius/asset-of-dreams) | Live Official Unity Addressables CDN: `assets-e.wds-stellarium.com/production/2d-assets/Android/{ver}/` | • `sirius-decrypted-data`: Masterdata (`card.json`, `master/*.json`) + ภาพการ์ด 1920x1180 (`0.png`, `1.png`, `cover*.png`)<br>• `Adv-Resource`: Spine 4.1 (`manifest/Spine.json`, `spine/*.{skel,atlas,png}`), cutout, card/poster icons, `_temp/2dcatalog.json` fallback<br>• `asset-of-dreams`: `config.yml` เพื่ออ่าน `asset_version` ล่าสุดสำหรับโหลด `catalog_{ver}.json.br`, Animated Actor Cards, Posters และ Signatures จาก Live CDN |
| **`assaultlily`** | • [`LaTlcia/A.RA.YA`](https://github.com/LaTlcia/A.RA.YA) *(MasterdataBase & Asset Catalog)*<br>• [`czk200518-hash/AssaultLily-deskpet`](https://github.com/czk200518-hash/AssaultLily-deskpet) *(Spine Samples)*<br>อ้างอิงแนวทางเครื่องมือ: [`LaTlcia/ArayaToolbox`](https://github.com/LaTlcia/ArayaToolbox) | CDN Card/Bundles: `allb.tqlwsl.moe/` (`Image/Card/`, `asset_bundle/card_prefab/`)<br>Asset Mirror: `allb.game-db.tw/images/` | • `LaTlcia/A.RA.YA`: ดึง Masterdata การ์ด/ตัวละคร/ชุด และรายการ `asset_bundle/card_prefab/*` + `Image/Card/*`<br>• `czk200518-hash/AssaultLily-deskpet`: ตัวอย่างโมเดล `CharacterJobSpine*`<br>• `allb.tqlwsl.moe` & `allb.game-db.tw`: ภาพ Memoria Full 800x600 JPG, 256x256 PNG, Costume Standing `@2x` และ Animated Memoria Prefab `.bundle` (รวม Emoria Spine 3.6) |

---

<a id="copyright"></a>
## 7. ข้อมูลลิขสิทธิ์ของแต่ละเกมและข้อจำกัดการใช้งาน

ทรัพย์สินทางปัญญา ภาพประกอบ ตัวละคร โมเดล 2D/3D บทสนทนา และข้อมูลในเกมทั้งหมดเป็น **ลิขสิทธิ์และเครื่องหมายการค้าของเจ้าของสิทธิ์ดั้งเดิมในแต่ละเกม** โปรเจกต์นี้ไม่ได้เป็นเจ้าของและไม่ได้จัดเก็บไฟล์ที่มีลิขสิทธิ์เหล่านั้นไว้ใน Repository

### ตารางข้อมูลลิขสิทธิ์ทั้ง 8 เกม

| รหัสเกม | ชื่อเกมทางการ | เจ้าของลิขสิทธิ์ / ผู้พัฒนา & ผู้ให้บริการ | ข้อความลิขสิทธิ์ทางการ (Copyright Notice) |
| :--- | :--- | :--- | :--- |
| **`cgss`** | アイドルマスター シンデレラガールズ スターライトステージ *(THE iDOLM@STER Cinderella Girls: Starlight Stage)* | **Bandai Namco Entertainment Inc.** *(พัฒนา: Cygames, Inc.)* | `THE IDOLM@STER™ & © Bandai Namco Entertainment Inc.` |
| **`mltd`** | アイドルマスター ミリオンライブ！ シアターデイズ *(THE iDOLM@STER Million Live! Theater Days)* | **Toshiyuki Kubooka** / **Bandai Namco Entertainment Inc.** | `© 窪岡俊之 THE IDOLM@STER™ & © Bandai Namco Entertainment Inc.` |
| **`pjsk`** | プロジェクトセカイ カラフルステージ！ feat. 初音ミク *(Project SEKAI COLORFUL STAGE! feat. Hatsune Miku)* | **SEGA Corporation** / **Colorful Palette Inc.** / **Crypton Future Media, INC.** *(www.piapro.net)* | `© SEGA / © Colorful Palette Inc. / © Crypton Future Media, INC. www.piapro.net` |
| **`holodori`** | hololive Dreams *(ホロライブドリームズ)* | **COVER Corporation** / **QualiArts, Inc.** | `© COVER / © QualiArts, Inc.` |
| **`bandori`** | バンドリ！ ガールズバンドパーティ！ *(BanG Dream! Girls Band Party!)* | **BanG Dream! Project** / **Bushiroad Inc.** *(พัฒนาเดิมร่วมกับ Craft Egg Inc. ก่อนโอนการพัฒนาให้ Bushiroad เมื่อ ม.ค. 2024)* | `© BanG Dream! Project © Craft Egg Inc. © bushiroad All Rights Reserved.` |
| **`ournotes`** | バンドリ！ アワーノーツ *(BanG Dream! Our Notes)* | **BanG Dream! Project** / **FROMTOKYO Inc.** / **Bushiroad Inc.** *(ให้บริการ Global โดย BILIBILI HK LIMITED)* | `© BanG Dream! Project © FROMTOKYO © bushiroad All Rights Reserved.` |
| **`yumesute`** | ワールドダイスター 夢のステラリウム *(World Dai Star: Yume no Stellarium)* | **Sirius / Project WDS** / **KMS, inc.** | `© Sirius / Project WDS Developed and Published by KMS, inc.` |
| **`assaultlily`** | アサルトリリィ Last Bullet *(Assault Lily: Last Bullet)* | **AZONE INTERNATIONAL・acus / Assault Lily Project** / **WFS / Pokelabo, Inc.** *(โอนสิทธิ์พัฒนา-ให้บริการในญี่ปุ่นแก่ KING PAWN Inc. ตั้งแต่ ธ.ค. 2025)* / **SHAFT Inc.** | `© AZONE INTERNATIONAL・acus / アサルトリリィプロジェクト © WFS © Pokelabo, Inc. © SHAFT` |

### ข้อกำหนดและข้อสงวนสิทธิ์ (Disclaimer)
1. **ไม่เกี่ยวข้องกับผู้พัฒนาทางการ (Unofficial Tool)**: เครื่องมือนี้สร้างขึ้นโดยชุมชนผู้ใช้ เพื่อช่วยให้สามารถจัดเก็บและสืบค้นข้อมูล Asset จากแหล่งสาธารณะได้สะดวกขึ้นเท่านั้น ไม่มีความเกี่ยวข้องหรือได้รับการรับรองจากบริษัทเจ้าของเกมทั้ง 8 เกม
2. **ใช้งานส่วนบุคคลและการศึกษาเท่านั้น (Personal, Research & Archival Use Only)**: ห้ามนำไฟล์ภาพ โมเดล Live2D/Spine หรือข้อมูลที่ดาวน์โหลดไปใช้ในเชิงพาณิชย์ ขายต่อ ดัดแปลงแอบอ้างเป็นผลงานตนเอง หรือเผยแพร่ซ้ำในลักษณะที่ละเมิดข้อตกลงการให้บริการ (Terms of Service) และกฎหมายลิขสิทธิ์
3. **ใบอนุญาตซอฟต์แวร์โอเพนซอร์สของไลบรารีเสริม**:
   * โค้ดใน Repository นี้ (`main.py`, `core/*`, `games/*`) เป็นสคริปต์ Python แยกต่างหากสำหรับเรียกใช้ข้อมูลผ่าน HTTP/JSON/UnityPy
   * ไลบรารีเสริมบางตัวใน `requirements.txt` และโปรเจกต์อ้างอิงของชุมชนมีสัญญาอนุญาตของตนเอง เช่น `A-kirami/bestdori-live2d-downloader` (**MIT**), `HolodoriDB/holodori-asset-tools` (**GPL-3.0** — ใช้เฉพาะเมื่อผู้ใช้ติดตั้งแพ็กเกจเสริมเพื่อรันหมวด `holodori`), `czk200518-hash/AssaultLily-deskpet` (**GPL-3.0**), `Sekai-World/sekai-viewer` (**GPL-3.0**), `StarMoe-org/Moesekai` และ `StarMoe-org/moenotes` (**AGPL-3.0**) รวมถึง **UnityPy**, **Pillow** และ **brotli** ตามเงื่อนไขของแต่ละแพ็กเกจ
