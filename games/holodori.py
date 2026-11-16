"""Adapter for hololive Dreams (holodori) using Octo catalog + direct UnityPy extraction."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from core.base import (
    CategoryResult,
    DownloadOptions,
    GameAdapter,
    sanitize_filename,
)
from core.http_client import fetch_bytes, load_or_fetch_json
from core.unity_utils import (
    holo_expression_to_exp3,
    holo_physics_to_json,
    require_unitypy,
    write_json,
)

UNITY_VERSION = "6000.3.15f1"
DB_ROOT = "https://raw.githubusercontent.com/HolodoriDB/holodori-db-jpn-diff/main"


class HolodoriAdapter(GameAdapter):
    code = "holodori"
    name = "hololive Dreams"
    credits = "HolodoriDB (holodori-db-jpn-diff) & holodori-asset-tools"
    supported_regions = ("jp",)

    _RARITY_MAP = {
        "3": "CARD_RARITY_RARITY_3",
        "4": "CARD_RARITY_RARITY_4",
        "sr": "CARD_RARITY_RARITY_4",
        "5": "CARD_RARITY_RARITY_5",
        "ssr": "CARD_RARITY_RARITY_5",
    }

    @staticmethod
    def _require_holodori_tools():
        UnityPy = require_unitypy(UNITY_VERSION)
        try:
            from holodori_asset_tools import catalog as holo_catalog
            from holodori_asset_tools import crypto as holo_crypto
        except ImportError as exc:
            raise RuntimeError(
                "holodori requires holodori-asset-tools, UnityPy, and Pillow. "
                "Install with: pip install holodori-asset-tools UnityPy Pillow"
            ) from exc
        return UnityPy, holo_catalog, holo_crypto

    @staticmethod
    def _unwrap(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in items:
            if isinstance(row, dict) and isinstance(row.get("data"), dict):
                out.append(row["data"])
            elif isinstance(row, dict):
                out.append(row)
        return out

    def _load_masterdata(self, options: DownloadOptions):
        mdir = self.masterdata_dir(options)
        cards = load_or_fetch_json(
            mdir / "Card.json",
            f"{DB_ROOT}/Card.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap,
        )
        chars = load_or_fetch_json(
            mdir / "Character.json",
            f"{DB_ROOT}/Character.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap,
        )
        costumes = load_or_fetch_json(
            mdir / "Costume.json",
            f"{DB_ROOT}/Costume.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap,
        )
        lang_card_raw = load_or_fetch_json(
            mdir / "LangCard_Jpn.json",
            f"{DB_ROOT}/LangCard_Jpn.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap,
        )
        lang_char_raw = load_or_fetch_json(
            mdir / "LangCharacter_Jpn.json",
            f"{DB_ROOT}/LangCharacter_Jpn.json",
            refresh=options.refresh_masterdata,
            transform=self._unwrap,
        )
        lang_card = {x["id"]: x.get("text", "") for x in lang_card_raw if "id" in x}
        lang_char = {x["id"]: x.get("text", "") for x in lang_char_raw if "id" in x}
        char_by_id = {c["id"]: c for c in chars if "id" in c}
        return cards, chars, costumes, char_by_id, lang_card, lang_char

    def _load_catalog(self, options: DownloadOptions, holo_catalog):
        cat_path = self.masterdata_dir(options) / "octo_catalog.json"
        if options.refresh_masterdata and cat_path.exists():
            cat_path.unlink(missing_ok=True)
        cat = holo_catalog.get(cat_path)
        by_name = {b.name: b for b in cat.assetBundles}
        by_id = {b.id: b for b in cat.assetBundles}
        return cat, by_name, by_id

    def _matched_char_ids(self, chars: list[dict], lang_char: dict[str, str], query: str) -> set[str]:
        q = query.strip().lower()
        out: set[str] = set()
        for ch in chars:
            cid = ch.get("id", "")
            haystack = " ".join(
                str(x)
                for x in (
                    cid,
                    ch.get("assetId", ""),
                    ch.get("nameEng", ""),
                    ch.get("shortNameEng", ""),
                    lang_char.get(ch.get("nameLangId", ""), ""),
                    lang_char.get(ch.get("shortNameLangId", ""), ""),
                )
            ).lower()
            if q in haystack or cid.lower() == q or ch.get("assetId", "").lower() == q:
                out.add(cid)
        return out

    @staticmethod
    def _download_bundles_parallel(entries: list[Any], threads: int) -> tuple[dict[str, bytes], dict[str, str]]:
        """Download raw encrypted bundles in parallel; caller decodes on main thread."""
        blobs: dict[str, bytes] = {}
        errs: dict[str, str] = {}
        if not entries:
            return blobs, errs
        with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
            futs = {pool.submit(fetch_bytes, b.url, None, 60, 3, True): b for b in entries}
            for fut in as_completed(futs):
                b = futs[fut]
                try:
                    blobs[b.name] = fut.result()
                except Exception as exc:
                    errs[b.name] = str(exc)
        return blobs, errs

    @staticmethod
    def _script_class_name(obj) -> str:
        try:
            data = obj.read()
            script = getattr(data, "m_Script", None)
            if script:
                return getattr(script.read(), "m_ClassName", "") or ""
        except Exception:
            pass
        return ""

    def run_category(self, category: str, options: DownloadOptions) -> CategoryResult:
        if category not in ("card", "character", "live2d"):
            return CategoryResult(game=self.code, category=category, supported=False, note=f"Unknown category: {category}")

        UnityPy, holo_catalog, holo_crypto = self._require_holodori_tools()
        cards, chars, costumes, char_by_id, lang_card, lang_char = self._load_masterdata(options)
        _, by_name, by_id = self._load_catalog(options, holo_catalog)

        base_out = self.game_dir(options) / category
        q = (options.character or "").strip().lower()
        char_ids = self._matched_char_ids(chars, lang_char, q) if q else None
        rar_suffix = self._RARITY_MAP.get((options.rarity or "").lower())

        if category == "card":
            return self._extract_cards(
                cards, lang_card, by_name, options, base_out, char_ids, rar_suffix, q, UnityPy, holo_crypto
            )
        if category == "character":
            return self._extract_characters(
                chars, lang_char, by_name, options, base_out, char_ids, UnityPy, holo_crypto
            )
        return self._extract_live2d(
            costumes, by_name, by_id, options, base_out, char_ids, q, UnityPy, holo_crypto
        )

    def _extract_cards(
        self,
        cards: list[dict],
        lang_card: dict[str, str],
        by_name: dict[str, Any],
        options: DownloadOptions,
        base_out: Path,
        char_ids: set[str] | None,
        rar_suffix: str | None,
        q: str,
        UnityPy,
        holo_crypto,
    ) -> CategoryResult:
        selected = []
        for c in sorted(cards, key=lambda x: int(x.get("order", 999999999))):
            aid = c.get("assetId")
            if not aid:
                continue
            if not (by_name.get(f"img_card_full_{aid}") or by_name.get(f"img_card_vert_{aid}")):
                continue
            if rar_suffix and not str(c.get("rarity", "")).endswith(rar_suffix):
                continue
            if char_ids is not None and c.get("characterId") not in char_ids:
                cname = lang_card.get(c.get("nameLangId", ""), "").lower()
                if q not in cname and q not in aid.lower():
                    continue
            selected.append(c)
        if options.limit:
            selected = selected[: options.limit]

        plan: list[tuple[Any, Path]] = []
        skipped = 0
        for c in selected:
            aid = c["assetId"]
            rar_digit = str(c.get("rarity", "")).rsplit("_", 1)[-1]
            label = sanitize_filename(lang_card.get(c.get("nameLangId", ""), "") or aid)
            for kind in ("full", "vert"):
                bname = f"img_card_{kind}_{aid}"
                entry = by_name.get(bname)
                if not entry:
                    continue
                dest = base_out / f"{aid}_r{rar_digit}_{label}_{kind}.png"
                if dest.exists() and dest.stat().st_size > 0:
                    skipped += 1
                else:
                    plan.append((entry, dest))

        total = skipped + len(plan)
        if not plan:
            return CategoryResult(game=self.code, category="card", total=total, skipped=skipped, output_path=base_out)

        print(f"[holodori:card] Downloading & decoding {len(plan)} bundles (threads={options.threads})...")
        blobs, errs = self._download_bundles_parallel([b for b, _ in plan], options.threads)
        downloaded = 0
        errors: list[str] = []
        for entry, dest in plan:
            if entry.name not in blobs:
                errors.append(f"{entry.name}: {errs.get(entry.name, 'download failed')}")
                continue
            try:
                env = UnityPy.load(holo_crypto.decrypt(blobs[entry.name], entry.name))
                saved_any = False
                for obj in env.objects:
                    if obj.type.name == "Texture2D":
                        d = obj.read()
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        d.image.save(dest)
                        saved_any = True
                        break
                if saved_any:
                    downloaded += 1
                else:
                    errors.append(f"{entry.name}: No Texture2D found")
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")

        return CategoryResult(
            game=self.code,
            category="card",
            total=total,
            downloaded=downloaded,
            skipped=skipped,
            failed=len(errors),
            output_path=base_out,
            note="Card Full (2048x1024) + Vert (thx Octo AES decrypt + Texture2D)",
            errors=errors[:10],
        )

    def _extract_characters(
        self,
        chars: list[dict],
        lang_char: dict[str, str],
        by_name: dict[str, Any],
        options: DownloadOptions,
        base_out: Path,
        char_ids: set[str] | None,
        UnityPy,
        holo_crypto,
    ) -> CategoryResult:
        prefixes = (
            ("full_2d", "img_chr_full_2d_"),
            ("icon_mini", "img_chr_icon_mini_"),
            ("key_band", "img_chr_key_band_"),
        )
        selected = [
            c
            for c in sorted(chars, key=lambda x: int(x.get("order", 999999999)))
            if (char_ids is None or c.get("id") in char_ids)
            and c.get("assetId")
            and any(by_name.get(f"{pref}{c['assetId']}") for _, pref in prefixes)
        ]
        if options.limit:
            selected = selected[: options.limit]

        plan: list[tuple[Any, Path]] = []
        skipped = 0
        for ch in selected:
            aid = ch.get("assetId")
            if not aid:
                continue
            slug = sanitize_filename(ch.get("nameEng") or lang_char.get(ch.get("nameLangId", ""), "") or aid)
            cdir = base_out / f"{aid}_{slug}"
            for label, prefix in prefixes:
                entry = by_name.get(f"{prefix}{aid}")
                if not entry:
                    continue
                dest = cdir / f"{label}.png"
                if dest.exists() and dest.stat().st_size > 0:
                    skipped += 1
                else:
                    plan.append((entry, dest))

        total = skipped + len(plan)
        if not plan:
            return CategoryResult(game=self.code, category="character", total=total, skipped=skipped, output_path=base_out)

        print(f"[holodori:character] Downloading & decoding {len(plan)} bundles (threads={options.threads})...")
        blobs, errs = self._download_bundles_parallel([b for b, _ in plan], options.threads)
        downloaded = 0
        errors: list[str] = []
        for entry, dest in plan:
            if entry.name not in blobs:
                errors.append(f"{entry.name}: {errs.get(entry.name, 'download failed')}")
                continue
            try:
                env = UnityPy.load(holo_crypto.decrypt(blobs[entry.name], entry.name))
                saved_any = False
                for obj in env.objects:
                    if obj.type.name == "Texture2D":
                        d = obj.read()
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        d.image.save(dest)
                        saved_any = True
                        break
                if saved_any:
                    downloaded += 1
                else:
                    errors.append(f"{entry.name}: No Texture2D found")
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")

        return CategoryResult(
            game=self.code,
            category="character",
            total=total,
            downloaded=downloaded,
            skipped=skipped,
            failed=len(errors),
            output_path=base_out,
            note="Character 2D standing (4096x4096) + mini icon + key band",
            errors=errors[:10],
        )

    def _extract_live2d(
        self,
        costumes: list[dict],
        by_name: dict[str, Any],
        by_id: dict[int, Any],
        options: DownloadOptions,
        base_out: Path,
        char_ids: set[str] | None,
        q: str,
        UnityPy,
        holo_crypto,
    ) -> CategoryResult:
        selected: list[tuple[str, Any]] = []
        seen: set[str] = set()
        for cos in costumes:
            aid = cos.get("assetId")
            if not aid or aid in seen:
                continue
            if char_ids is not None and cos.get("characterId") not in char_ids:
                if q not in aid.lower():
                    continue
            b = by_name.get(f"live2d_mdl_{aid}")
            if not b:
                continue
            seen.add(aid)
            selected.append((aid, b))
        if options.limit:
            selected = selected[: options.limit]

        # Collect model bundles + expression dependency bundles
        needed_entries: dict[str, Any] = {}
        model_specs: list[tuple[str, Any, list[Any]]] = []
        for aid, mdl_entry in selected:
            exp_entries: list[Any] = []
            for dep_id in getattr(mdl_entry, "dependencies", []) or []:
                dep = by_id.get(dep_id)
                if dep and dep.name.startswith("live2d_exp_") and not dep.name.endswith("_test"):
                    exp_entries.append(dep)
                    needed_entries[dep.name] = dep
            needed_entries[mdl_entry.name] = mdl_entry
            model_specs.append((aid, mdl_entry, exp_entries))

        # Shared sample motions (capped when --limit is given)
        mot_entries = [
            b for name, b in sorted(by_name.items()) if name.startswith("live2d_mot_")
        ]
        if options.limit:
            mot_entries = mot_entries[: min(len(mot_entries), max(1, options.limit))]
        for me in mot_entries:
            needed_entries[me.name] = me

        # Skip bundles whose output files already exist
        download_list: list[Any] = []
        skipped_models = 0
        active_specs: list[tuple[str, Any, list[Any]]] = []
        for aid, mdl_entry, exp_entries in model_specs:
            mdir = base_out / aid
            if (mdir / f"{aid}.moc3").exists() and (mdir / f"{aid}.model3.json").exists():
                skipped_models += 1
                continue
            active_specs.append((aid, mdl_entry, exp_entries))
            download_list.append(mdl_entry)
            download_list.extend(exp_entries)

        active_mots = []
        mot_dir = base_out / "_shared_motions"
        for me in mot_entries:
            if (mot_dir / f"{me.name}.anim.json").exists():
                skipped_models += 1
            else:
                active_mots.append(me)
                download_list.append(me)

        # Deduplicate download list preserving order
        uniq_map = {e.name: e for e in download_list}
        download_list = list(uniq_map.values())

        total = skipped_models + len(active_specs) + len(active_mots)
        if not download_list:
            return CategoryResult(
                game=self.code,
                category="live2d",
                total=total,
                skipped=skipped_models,
                output_path=base_out,
                note="Live2D Cubism 5 (.moc3 + .model3.json + textures + physics + .exp3.json + shared motions)",
            )

        print(f"[holodori:live2d] Downloading & decoding {len(download_list)} bundles (threads={options.threads})...")
        blobs, errs = self._download_bundles_parallel(download_list, options.threads)

        downloaded = 0
        errors: list[str] = []

        for aid, mdl_entry, exp_entries in active_specs:
            if mdl_entry.name not in blobs:
                errors.append(f"{mdl_entry.name}: {errs.get(mdl_entry.name, 'download failed')}")
                continue
            mdir = base_out / aid
            tex_dir = mdir / "textures"
            exp_dir = mdir / "expressions"
            tex_dir.mkdir(parents=True, exist_ok=True)
            exp_dir.mkdir(parents=True, exist_ok=True)

            try:
                env = UnityPy.load(holo_crypto.decrypt(blobs[mdl_entry.name], mdl_entry.name))
                moc_file = ""
                physics_file = ""
                tex_files: list[str] = []

                for obj in env.objects:
                    if obj.type.name == "Texture2D":
                        d = obj.read()
                        tname = sanitize_filename(getattr(d, "m_Name", "") or f"tex_{obj.path_id}") + ".png"
                        d.image.save(tex_dir / tname)
                        tex_files.append(f"textures/{tname}")
                    elif obj.type.name == "MonoBehaviour":
                        cls = self._script_class_name(obj)
                        if cls == "CubismMoc":
                            tt = obj.read_typetree()
                            raw_moc = bytes(tt.get("_bytes") or b"")
                            if raw_moc:
                                moc_path = mdir / f"{aid}.moc3"
                                moc_path.write_bytes(raw_moc)
                                moc_file = f"{aid}.moc3"
                        elif cls == "CubismPhysicsController":
                            tt = obj.read_typetree()
                            phy_path = mdir / f"{aid}.physics3.json"
                            write_json(phy_path, holo_physics_to_json(tt))
                            physics_file = f"{aid}.physics3.json"

                exp_refs: list[dict[str, str]] = []
                for dep in exp_entries:
                    if dep.name not in blobs:
                        continue
                    try:
                        env_e = UnityPy.load(holo_crypto.decrypt(blobs[dep.name], dep.name))
                        for o2 in env_e.objects:
                            if o2.type.name == "MonoBehaviour":
                                tt = o2.read_typetree()
                                if "Parameters" in tt:
                                    exp_name = dep.name.removeprefix("live2d_exp_")
                                    exp_fname = f"{exp_name}.exp3.json"
                                    write_json(exp_dir / exp_fname, holo_expression_to_exp3(tt))
                                    exp_refs.append({"Name": exp_name, "File": f"expressions/{exp_fname}"})
                                    break
                    except Exception:
                        pass

                model3 = {
                    "Version": 3,
                    "FileReferences": {
                        "Moc": moc_file,
                        "Textures": sorted(tex_files),
                        **({"Physics": physics_file} if physics_file else {}),
                        **({"Expressions": exp_refs} if exp_refs else {}),
                    },
                    "Groups": [
                        {"Target": "Parameter", "Name": "EyeBlink", "Ids": ["ParamEyeLOpen", "ParamEyeROpen"]},
                        {"Target": "Parameter", "Name": "LipSync", "Ids": ["ParamMouthOpenY"]},
                    ],
                }
                write_json(mdir / f"{aid}.model3.json", model3)
                downloaded += 1
            except Exception as exc:
                errors.append(f"{mdl_entry.name}: {exc}")

        for me in active_mots:
            if me.name not in blobs:
                continue
            try:
                env_m = UnityPy.load(holo_crypto.decrypt(blobs[me.name], me.name))
                for obj in env_m.objects:
                    if obj.type.name == "AnimationClip":
                        write_json(mot_dir / f"{me.name}.anim.json", obj.read_typetree())
                    elif obj.type.name == "MonoBehaviour":
                        write_json(mot_dir / f"{me.name}.motion_meta.json", obj.read_typetree())
                downloaded += 1
            except Exception as exc:
                errors.append(f"{me.name}: {exc}")

        return CategoryResult(
            game=self.code,
            category="live2d",
            total=total,
            downloaded=downloaded,
            skipped=skipped_models,
            failed=len(errors),
            output_path=base_out,
            note="Live2D Cubism 5 (.moc3 + .model3.json + 4K textures + physics + .exp3.json + shared motions)",
            errors=errors[:10],
        )
