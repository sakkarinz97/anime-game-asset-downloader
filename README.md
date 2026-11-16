# Anime Game Masterdata & Asset Downloader (พร้อมระบบ Sync Google Drive)

เครื่องมือรวมสำหรับดึง **Masterdata** และดาวน์โหลด **Assets ความละเอียดสูงสุด** จากเกมไอดอล/กาชาอนิเมะ 8 เกมยอดนิยม แยกเก็บเป็นสัดส่วนตามเกมและหมวดหมู่ พร้อมระบบอัปโหลดและซิงค์ขึ้น **Google Drive** อัตโนมัติ

---

## สถาปัตยกรรมโปรเจกต์ (Approach 2: แยก Code บน GitHub และ Asset บน Google Drive)

* **GitHub Repository**: เก็บเฉพาะโค้ด Python ดาวน์โหลด, Adapters ของทั้ง 8 เกม, ระบบ UnityPy extractor และ Google Drive sync (`downloads/`, `.venv/`, และไฟล์ภาพ/ไบนารีขนาดใหญ่ถูกกันออกผ่าน `.gitignore`)
* **Google Drive (`Work/AnimeGameAssets/`)**: เก็บไฟล์ภาพและไฟล์ Live2D/Spine ที่โหลดเสร็จแล้วอย่างเป็นระเบียบ โดยไม่เปลืองพื้นที่ Git:

```text
Work/
└── AnimeGameAssets/
    ├── cgss/ (card, character)
    ├── mltd/ (card, character)
    ├── pjsk/ (card, live2d, character)
    ├── holodori/ (card, live2d, character)
    ├── bandori/ (card, live2d, character)
    ├── ournotes/ (card, live2d, character)
    ├── yumesute/ (card, card_animation, spine, character)
    └── assaultlily/ (card, card_animation, spine, character)
```

---

## ตารางรองรับทั้ง 8 เกม & หมวดหมู่ Asset

| รหัส (`--game`) | ชื่อเกม | `card` (Card / Memoria) | `card_animation` (พิเศษ 2 เกม) | `live2d` (Live2D / Spine) | `character` (ตัวละคร / ไอคอน / ชิบิ) | แหล่งข้อมูล / เครดิต |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`cgss`** | THE iDOLM@STER Cinderella Girls: Starlight Stage | PNG การ์ด + ภาพเต็มแนวนอน (`spread`) | — | ❌ (ตัวเกมใช้ 3D + 2D Puchi Sprite ไม่มี Live2D) | ไอคอนการ์ด (`icon_card`) + `puchi` Sprite | Starlight DB (`kirara.ca`) |
| **`mltd`** | THE iDOLM@STER Million Live! Theater Days | PNG การ์ดกรอบ/ไร้กรอบ + พื้นหลัง HQ (`card_bg_hq`) | — | ❌ (ตัวเกมใช้โมเดล 3D ไม่มี Live2D) | พอร์ตเทรตไอคอนใหญ่ (`icon_l`) | Matsurihi.me Princess API |
| **`pjsk`** | プロジェクトセカイ カラフルステージ！ feat. 初音ミク | `card_normal.png` + `card_after_training.png` | — | ✅ Cubism 3/4 (`.moc3`, `.model3.json`, textures, motions) | Full Cutout (`cutout`, `cutout_trm`) + Character Icons | Moesekai (`pjsk.moe`) & `sekai-master-db-diff` |
| **`holodori`** | hololive Dreams (`holodori`) | ถอดรหัส Octo AES + UnityPy (`2048x1024` Full + Vertical) | — | ✅ Cubism 5 (`.moc3`, `.model3.json`, 4K textures, physics, `.exp3.json`, shared motions) | Full 2D Standing (`4096x4096`) + Mini Icon + Key Band | `HolodoriDB` & `holodori-asset-tools` |
| **`bandori`** | BanG Dream! Girls Band Party! | `card_normal.png` + `card_after_training.png` | — | ✅ Cubism 2 (`.moc`, `model.json`, `physics.json`, motions, `.exp.json`) | Full Cutout Trim (`trim_normal`/`after_training`) + `livesd` + Icons | Bestdori! & `bestdori-live2d-downloader` |
| **`ournotes`** | BanG Dream! Our Notes | Member Card (`member_full`, `member_background`) + Support Snap Full | — | ✅ Cubism 3/4 (รวมประกอบไฟล์ chunked `.prefab.json` อัตโนมัติ) | `character_sprite`, `thumbnail`, `face_icon` + `member_character` | Moenotes (`bdon.moe`) & `StarMoe-org` |
| **`yumesute`** | World Dai Star: Yume no Stellarium (`Yumesute`) | Full-Res `1920x1180` (`0/1`, `cover0/cover1`) + Cutouts | 🎬 **Animated Actor Cards** (`4★ _1` & `15xxxx`): ภาพ 1920x1180 + ชั้น Multi-layer + FX Sprite Sheet + Mask + Shader/Holo JSON + `.bundle` | 🦴 **Spine 4.1** (`.skel`, `.atlas`, `.png` — เกมใช้ Spine แทน Live2D บันทึกลง `spine/`) | Card/Poster Icons + (ถ้ามี UnityPy: Full Posters `1357x1920` & Signatures จาก Live CDN) | `wds-sirius`, `SonolusHaniwa` & WDS Live CDN |
| **`assaultlily`** | アサルトリリィ Last Bullet | Full JPG `800x600` (`full/`) + PNG `256x256` + `memoria_ultimate` | 🎬 **Animated Memoria Prefabs** (`card_prefab`): 2048x2048 Atlases + VFX Sprites + Emoria **Spine 3.6** (`.skel`/`.atlas`/`.png`) + `animation_meta.json` + `.bundle` | 🦴 **Spine Sample** (อ้างอิง CEDEC 2021 เกมใช้ Spine — โหลดไฟล์ตัวอย่างจาก community repo ลง `spine/`) | Portraits (`chara`) + Standing `@2x` (`900x1550`) + Costume Full Illus (`1536x1174` JPG) + Job Icon | `LaTlcia/A.RA.YA`, `allb.tqlwsl.moe`, `allb.game-db.tw`, `AssaultLily-deskpet` |

> **หมายเหตุสำคัญด้านเทคนิค**:
> * เกม `yumesute` และ `assaultlily` ใช้ **Esoteric Software Spine** เป็นเอนจินแอนิเมชัน 2 มิติหลัก (ไม่ใช้ Live2D Cubism) ระบบจึงดาวน์โหลดเป็น `.skel/.atlas/.png` แยกไว้ในโฟลเดอร์ `spine/` อย่างชัดเจน
> * **โหมดพิเศษ `--card-animation` / `--category card_animation`** ออกแบบเฉพาะสำหรับ **`yumesute`** และ **`assaultlily`**:
>   * **`yumesute`**: แอนิเมชันการ์ดใช้ Unity UIParticle + Parallax + Shader Mask/Holo เฉพาะการ์ด `4★ SSR` ปลุกพลัง (`_1`) และซีรีส์ `15xxxx` (`_0.._3`)
>   * **`assaultlily`**: แอนิเมชันการ์ด (`card_prefab` จาก `allb.tqlwsl.moe`) มีทั้งแบบ Sprite/Sway Prefabs (`AnimationClip` 60 FPS + Atlases `2048x2048`) และการ์ด **Emoria** ที่ใช้ **Spine 3.6** เต็มชุดในโฟลเดอร์ `spine/` พร้อมใช้งาน
> * เกม `cgss` และ `mltd` เป็นเกม 3D เป็นหลัก ระบบจึงข้ามหมวด `live2d` พร้อมแจ้งสถานะชัดเจน

---

## การติดตั้ง (Installation)

1. เกม 6 เกม (`cgss`, `mltd`, `pjsk`, `bandori`, `ournotes`, ส่วนภาพการ์ด/ตัวละครของ `assaultlily` และส่วน GitHub ของ `yumesute`) **รันบน Python >= 3.10 Standard Library ได้เลย** โดยไม่ต้องลงแพ็กเกจเสริม
2. หากต้องการใช้ **`holodori`**, **Full Posters / Signatures ของ `yumesute`**, และฟีเจอร์พิเศษ **`--card-animation`** ของ **`yumesute` & `assaultlily`** ให้สร้าง virtual environment แล้วติดตั้ง `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## ตัวอย่างการใช้งาน CLI (`main.py`)

### 1. ดูรายชื่อเกมทั้งหมดที่รองรับ
```bash
python main.py --list-games
```

### 2. โหลดการ์ด + Live2D + ตัวละคร ของเกมที่ต้องการ (แนะนำใส่ `--limit` เพื่อทดลองก่อน)
```bash
# โหลดตัวอย่างของ Project SEKAI และ Bandori อย่างละ 2 รายการ
python main.py --game pjsk bandori --category all --limit 2

# เฉพาะการ์ด SSR ของ CGSS ตัวละคร Uzuki
python main.py --game cgss --category card --rarity ssr --character uzuki --limit 5

# เฉพาะ Live2D ของ hololive Dreams (เช่น Sora / Gura)
.venv/bin/python main.py --game holodori --category live2d --character sora --limit 2

# โหลดทุกเกม ทุกหมวด (แบบจำกัด 2 รายการต่อหมวด)
.venv/bin/python main.py --game all --category all --limit 2
```

### 3. โหลดการ์ดเวอร์ชัน Animation (พิเศษเฉพาะ `yumesute` และ `assaultlily`)
```bash
# โหลดเฉพาะการ์ดเวอร์ชัน Animation ของ Yumesute และ Assault Lily (ตัวอย่างเกมละ 2 ใบ)
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --limit 2

# โหลดทั้งภาพการ์ดปกติ (เฉพาะใบที่มี animation) + เวอร์ชัน animation พร้อมกัน
.venv/bin/python main.py --game yumesute assaultlily --category card --card-animation --animated-only --limit 2

# โหลดการ์ด Emoria (Spine 3.6 เต็มชุด) ของ Assault Lily
.venv/bin/python main.py --game assaultlily --category card_animation --character 80000001

# แตกเฉพาะไฟล์ PNG / Spine / JSON โดยไม่เก็บไฟล์ .bundle ดิบ (ประหยัดพื้นที่)
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --no-raw-bundle --limit 2
```

### 4. โหลดและซิงค์ขึ้น Google Drive อัตโนมัติ
> ต้องเชื่อมต่อ `gdrive` CLI บนเครื่องหรือ Antigravity environment ก่อน

```bash
# ซิงค์ขึ้น Google Drive (โฟลเดอร์ Work/AnimeGameAssets/)
.venv/bin/python main.py --game all --category all --limit 2 --upload-drive

# ซิงค์การ์ดเวอร์ชัน Animation ของ Yumesute & Assault Lily ขึ้น Google Drive
.venv/bin/python main.py --game yumesute assaultlily --category card_animation --limit 2 --upload-drive

# เลือกโหมด zip เพื่อความเร็วเมื่อจำนวนไฟล์ต่อหมวดเยอะ และลบไฟล์ชั่วคราวบนเครื่องหลังอัปโหลดสำเร็จ
.venv/bin/python main.py --game pjsk --category live2d --upload-drive --drive-mode zip --cleanup-local
```

### พารามิเตอร์ทั้งหมด
* `--game`: ระบุชื่อเกม (`cgss`, `mltd`, `pjsk`, `holodori`, `bandori`, `ournotes`, `yumesute`, `assaultlily` หรือ `all`) — ระบุหลายเกมได้ทั้งแบบเว้นวรรคหรือคั่นด้วยลูกน้ำ
* `--category`: `card` | `live2d` | `character` | `card_animation` *(พิเศษสำหรับ `yumesute`, `assaultlily`)* | `all`
* `--card-animation`: ตัวเลือกพิเศษสำหรับ `yumesute` และ `assaultlily` เพื่อสั่งโหลดหมวด `card_animation` เพิ่มเติมควบคู่กับ `--category` ที่เลือก
* `--animated-only`: กรองเฉพาะการ์ดที่มีเวอร์ชัน Animation ใน `yumesute` (`4★` ปลุกพลัง / `15xxxx`) และ `assaultlily` (`isAnimation` / `card_prefab`)
* `--no-raw-bundle`: ไม่บันทึกไฟล์ `.bundle` ดิบตอนแตก `card_animation` (เก็บเฉพาะภาพ PNG, ไฟล์ Spine และ `animation_meta.json`)
* `--region`: เซิร์ฟเวอร์ (`jp`, `en`, `tw`, `hk-tw-mo`, `kr`, `cn`) เฉพาะเกมที่รองรับหลายโซน
* `--rarity`: กรองระดับความหายาก (`n`, `r`, `sr`, `ssr`, `ur`, `3`, `4`, `5` ฯลฯ)
* `--character`: กรองจากชื่อหรือรหัสตัวละคร (รองรับอังกฤษ/ญี่ปุ่น/ID)
* `--limit`: จำกัดจำนวนรายการต่อหมวด
* `--threads`: จำนวนเธรดโหลดพร้อมกัน (ค่าเริ่มต้น `8`)
* `--out-dir`: โฟลเดอร์ปลายทางในเครื่อง (ค่าเริ่มต้น `./downloads`)
* `--refresh-masterdata`: บังคับโหลด Masterdata JSON และ Asset Catalog ใหม่จากต้นทาง
* `--upload-drive`: ซิงค์เข้า Google Drive หลังจบแต่ละหมวด
* `--drive-parent-id`: Folder ID ปลายทางบน Drive (ค่าเริ่มต้น `1kaSiYfkeaFXvXQQbZlFKJV4Tq--M5yFf` = `Work/`)
* `--drive-root-name`: ชื่อโฟลเดอร์หลักบน Drive (ค่าเริ่มต้น `AnimeGameAssets`)
* `--drive-mode`: `auto` (อัปโหลดทีละไฟล์ถ้า ≤ 40 ไฟล์ ไม่อย่างนั้นรวมเป็น `.zip`) | `direct` | `zip`
* `--cleanup-local`: ลบไฟล์ในเครื่องหลังอัปโหลดเข้า Drive สำเร็จ

---

## เครดิตแหล่งข้อมูลโอเพนซอร์ส (Credits)

โปรเจกต์นี้ดึงข้อมูลและโครงสร้าง Asset จากชุมชนผู้พัฒนาโอเพนซอร์สต่อไปนี้:
* **Starlight DB** (`starlight.kirara.ca` / `hidamarirhodonite.kirara.ca`)
* **Matsurihi.me** (`api.matsurihi.me` / `storage.matsurihi.me`)
* **Moesekai** (`pjsk.moe`) & **Sekai-World** (`sekai-master-db-*`)
* **HolodoriDB** (`HolodoriDB/holodori-db-jpn-diff`) & **`holodori-asset-tools`**
* **Bestdori!** (`bestdori.com`) & **`A-kirami/bestdori-live2d-downloader`**
* **Moenotes** (`bdon.moe`) & **`StarMoe-org`** (`moenotes`, `moenotes-masterdata`)
* **World Dai Star** (`wds-sirius/Adv-Resource`, `wds-sirius/asset-of-dreams`, `SonolusHaniwa/sirius-decrypted-data`, WDS Official CDN)
* **Assault Lily: Last Bullet** (`LaTlcia/A.RA.YA`, `allb.tqlwsl.moe`, `allb.game-db.tw`, `czk200518-hash/AssaultLily-deskpet`)
