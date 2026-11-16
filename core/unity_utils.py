"""Safe Unity AssetBundle & Cubism helpers (avoids crash-prone Sprite/all-MonoBehaviour dumps)."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any


def require_unitypy(fallback_version: str = "2022.3.21f1"):
    try:
        import warnings
        import UnityPy
        from UnityPy.exceptions import UnityVersionFallbackWarning
    except ImportError as exc:
        raise RuntimeError(
            "This operation requires UnityPy and Pillow. Install with: "
            "pip install UnityPy Pillow brotli"
        ) from exc

    UnityPy.config.FALLBACK_UNITY_VERSION = fallback_version
    warnings.simplefilter("ignore", UnityVersionFallbackWarning)
    return UnityPy


def _unique_tex_filename(used: set[str], base_name: str, w: int, h: int, prefix: str = "") -> str:
    safe_base = "".join("_" if c in '<>:"/\\|?*\r\n\t' else c for c in base_name).strip() or "texture"
    cand = f"{prefix}{safe_base}.png"
    if cand not in used:
        used.add(cand)
        return cand
    cand_dim = f"{prefix}{safe_base}_{w}x{h}.png"
    if cand_dim not in used:
        used.add(cand_dim)
        return cand_dim
    idx = 2
    while f"{prefix}{safe_base}_{w}x{h}_{idx}.png" in used:
        idx += 1
    final = f"{prefix}{safe_base}_{w}x{h}_{idx}.png"
    used.add(final)
    return final


def extract_textures_and_texts(
    bundle_bytes: bytes,
    out_dir: Path,
    fallback_version: str = "2022.3.21f1",
    name_prefix: str = "",
) -> list[Path]:
    """Safely extract Texture2D (.png) and TextAsset files from a UnityFS bundle."""
    UnityPy = require_unitypy(fallback_version)
    env = UnityPy.load(bundle_bytes)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    used_tex_names: set[str] = set()

    tex_objs = []
    for obj in env.objects:
        if obj.type.name == "Texture2D":
            d = obj.read()
            base_name = getattr(d, "m_Name", "") or f"tex_{obj.path_id}"
            w = int(getattr(d, "m_Width", 0) or 0)
            h = int(getattr(d, "m_Height", 0) or 0)
            tex_objs.append((-(w * h), obj.path_id, base_name, w, h, d))
        elif obj.type.name == "TextAsset":
            d = obj.read()
            base_name = getattr(d, "m_Name", "") or f"text_{obj.path_id}.txt"
            dest = out_dir / f"{name_prefix}{base_name}"
            script = d.m_Script
            raw = (
                script.encode("utf-8", "surrogateescape")
                if isinstance(script, str)
                else bytes(script)
            )
            dest.write_bytes(raw)
            saved.append(dest)

    for _, _, base_name, w, h, d in sorted(tex_objs, key=lambda x: (x[0], x[1])):
        fname = _unique_tex_filename(used_tex_names, base_name, w, h, prefix=name_prefix)
        dest = out_dir / fname
        d.image.save(dest)
        saved.append(dest)

    return saved


def _read_material_props(tt: dict[str, Any]) -> dict[str, Any]:
    sp = tt.get("m_SavedProperties", {}) or {}
    floats_raw = sp.get("m_Floats", {})
    if isinstance(floats_raw, list):
        floats = {
            str(item[0]): float(item[1])
            for item in floats_raw
            if isinstance(item, (list, tuple)) and len(item) == 2
        }
    elif isinstance(floats_raw, dict):
        floats = {str(k): float(v) for k, v in floats_raw.items()}
    else:
        floats = {}

    tex_raw = sp.get("m_TexEnvs", {})
    if isinstance(tex_raw, list):
        tex_slots = [str(item[0]) for item in tex_raw if isinstance(item, (list, tuple)) and item]
    elif isinstance(tex_raw, dict):
        tex_slots = [str(k) for k in tex_raw.keys()]
    else:
        tex_slots = []

    return {
        "name": tt.get("m_Name", ""),
        "floats": floats,
        "tex_slots": tex_slots,
    }


def _parse_atlas_pages(atlas_text: str) -> list[str]:
    pages: list[str] = []
    for raw_line in atlas_text.splitlines():
        line = raw_line.lstrip("\ufeff").strip()
        if line.lower().endswith((".png", ".webp", ".jpg")):
            pages.append(Path(line).name)
    return pages


def extract_animated_card_bundle(
    bundle_bytes: bytes,
    out_dir: Path,
    fallback_version: str = "2022.3.21f1",
    extra_meta: dict[str, Any] | None = None,
    save_raw_bundle: bool = True,
    bundle_filename: str | None = None,
) -> dict[str, Any]:
    """
    Extract an animated card UnityFS bundle safely into `out_dir`:
      - `<bundle_filename>` (raw UnityFS bundle, when `save_raw_bundle=True`)
      - `textures/*.png` (main layers, masks, VFX sprite sheets, Spine atlas pages)
      - `spine/*.skel`, `spine/*.atlas`, plus linked `.png` pages (when Spine rig is present)
      - `animation_meta.json` (AnimationClips, Materials/shaders, Sprites, ParticleSystems, MonoScripts)
    """
    UnityPy = require_unitypy(fallback_version)
    env = UnityPy.load(bundle_bytes)
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_dir = out_dir / "textures"
    tex_dir.mkdir(parents=True, exist_ok=True)

    if save_raw_bundle and bundle_filename:
        (out_dir / bundle_filename).write_bytes(bundle_bytes)

    counts = Counter(obj.type.name for obj in env.objects)
    dependencies: list[str] = []
    tex_candidates: list[tuple[int, int, str, int, int, Any]] = []
    text_assets: list[tuple[str, bytes]] = []
    animation_clips: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    sprites: list[dict[str, Any]] = []
    scripts: list[str] = []
    behaviours: list[dict[str, Any]] = []

    for obj in env.objects:
        tname = obj.type.name
        if tname == "AssetBundle":
            try:
                tt = obj.read_typetree()
                deps = tt.get("m_Dependencies") or []
                dependencies.extend(str(x) for x in deps if x)
            except Exception:
                pass
        elif tname == "Texture2D":
            d = obj.read()
            base_name = getattr(d, "m_Name", "") or f"tex_{obj.path_id}"
            w = int(getattr(d, "m_Width", 0) or 0)
            h = int(getattr(d, "m_Height", 0) or 0)
            tex_candidates.append((-(w * h), obj.path_id, base_name, w, h, d))
        elif tname == "TextAsset":
            d = obj.read()
            base_name = getattr(d, "m_Name", "") or f"text_{obj.path_id}.txt"
            script = d.m_Script
            raw = (
                script.encode("utf-8", "surrogateescape")
                if isinstance(script, str)
                else bytes(script)
            )
            text_assets.append((base_name, raw))
        elif tname == "AnimationClip":
            try:
                tt = obj.read_typetree()
                mc = tt.get("m_MuscleClip", {}) or {}
                clip_settings = mc.get("m_AnimationClipSettings") or tt.get("m_AnimationClipSettings") or {}
                animation_clips.append(
                    {
                        "name": tt.get("m_Name", ""),
                        "sampleRate": float(tt.get("m_SampleRate", 60.0) or 60.0),
                        "startTime": float(mc.get("m_StartTime", 0.0) or 0.0),
                        "stopTime": float(mc.get("m_StopTime", 0.0) or 0.0),
                        "loopTime": bool(clip_settings.get("m_LoopTime", False)),
                    }
                )
            except Exception:
                pass
        elif tname == "Material":
            try:
                tt = obj.read_typetree()
                materials.append(_read_material_props(tt))
            except Exception:
                pass
        elif tname == "Sprite":
            try:
                tt = obj.read_typetree()
                r = tt.get("m_Rect", {}) or {}
                sprites.append(
                    {
                        "name": tt.get("m_Name", ""),
                        "x": float(r.get("x", 0.0) or 0.0),
                        "y": float(r.get("y", 0.0) or 0.0),
                        "width": float(r.get("width", 0.0) or 0.0),
                        "height": float(r.get("height", 0.0) or 0.0),
                    }
                )
            except Exception:
                pass
        elif tname == "MonoScript":
            try:
                d = obj.read()
                full = f"{d.m_Namespace}.{d.m_ClassName}".strip(".")
                if full and full not in scripts:
                    scripts.append(full)
            except Exception:
                pass
        elif tname == "MonoBehaviour":
            try:
                tt = obj.read_typetree()
                clean = {
                    k: v
                    for k, v in tt.items()
                    if k not in ("m_GameObject", "m_Script", "m_Enabled")
                }
                interesting_keys = {
                    "scale",
                    "fromAnimation",
                    "toAnimation",
                    "defaultMix",
                    "frameAnimationTime",
                    "_largeCharacterScale",
                    "_partySlotCharacterPosition",
                    "_partySlotCharacterScale",
                }
                if interesting_keys.intersection(clean.keys()):
                    behaviours.append(clean)
            except Exception:
                pass

    # Save largest textures first so primary artwork keeps exact base filename on collisions
    used_tex_names: set[str] = set()
    tex_meta: list[dict[str, Any]] = []
    tex_path_by_name: dict[str, Path] = {}
    for _, _, base_name, w, h, d in sorted(tex_candidates, key=lambda x: (x[0], x[1])):
        fname = _unique_tex_filename(used_tex_names, base_name, w, h)
        dest = tex_dir / fname
        d.image.save(dest)
        tex_path_by_name[fname] = dest
        tex_meta.append({"file": f"textures/{fname}", "name": base_name, "width": w, "height": h})

    # Save TextAssets (Spine .skel/.atlas or generic text)
    spine_dir = out_dir / "spine"
    texts_dir = out_dir / "texts"
    atlas_pages: list[str] = []
    spine_files: list[str] = []
    text_files: list[str] = []
    for name, raw in text_assets:
        lname = name.lower()
        is_spine = lname.endswith((".skel", ".atlas"))
        if not is_spine and lname.endswith(".json"):
            try:
                head_txt = raw[:512].decode("utf-8", "ignore")
                if '"skeleton"' in head_txt and ('"bones"' in head_txt or '"spine"' in head_txt):
                    is_spine = True
            except Exception:
                pass
        target_root = spine_dir if is_spine else texts_dir
        target_root.mkdir(parents=True, exist_ok=True)
        dest = target_root / Path(name).name
        dest.write_bytes(raw)
        if is_spine:
            spine_files.append(f"spine/{dest.name}")
            if lname.endswith(".atlas"):
                atlas_pages.extend(_parse_atlas_pages(raw.decode("utf-8", "ignore")))
        else:
            text_files.append(f"texts/{dest.name}")

    # Copy Spine atlas texture pages into `spine/` so viewers load standalone cleanly
    if spine_files:
        for page_name in dict.fromkeys(atlas_pages):
            src = tex_path_by_name.get(page_name)
            if src and src.exists():
                shutil.copy2(src, spine_dir / page_name)
                spine_files.append(f"spine/{page_name}")

    meta: dict[str, Any] = {
        **(extra_meta or {}),
        "bundle_size": len(bundle_bytes),
        "raw_bundle": bundle_filename if (save_raw_bundle and bundle_filename) else None,
        "has_spine": bool(spine_files),
        "object_counts": dict(counts),
        "particle_systems": int(counts.get("ParticleSystem", 0)),
        "dependencies": dependencies,
        "scripts": scripts,
        "animation_clips": animation_clips,
        "textures": tex_meta,
        "sprites": sprites,
        "materials": materials,
        "spine_files": spine_files,
        "text_files": text_files,
        "behaviours": behaviours,
    }
    write_json(out_dir / "animation_meta.json", meta)
    return meta


_BLEND_MAP = {0: "Overwrite", 1: "Add", 2: "Multiply"}


def holo_expression_to_exp3(tt: dict[str, Any]) -> dict[str, Any]:
    """Convert Unity CubismExpressionData MonoBehaviour typetree to .exp3.json."""
    params = []
    for p in tt.get("Parameters", []):
        params.append(
            {
                "Id": p.get("Id", ""),
                "Value": float(p.get("Value", 0.0)),
                "Blend": _BLEND_MAP.get(int(p.get("Blend", 1)), "Add"),
            }
        )
    return {
        "Type": tt.get("Type") or "Live2D Expression",
        "FadeInTime": float(tt.get("FadeInTime", 0.3)),
        "FadeOutTime": float(tt.get("FadeOutTime", 0.3)),
        "Parameters": params,
    }


def holo_physics_to_json(tt: dict[str, Any]) -> dict[str, Any]:
    """Export Unity CubismPhysicsController _rig data into structured physics JSON."""
    rig = tt.get("_rig", {})
    settings = []
    for i, sub in enumerate(rig.get("SubRigs", [])):
        inputs = []
        for inp in sub.get("Input", []):
            src = inp.get("Source", {})
            inputs.append(
                {
                    "Source": {
                        "Target": "Parameter",
                        "Id": src.get("Id", inp.get("SourceId", "")),
                    },
                    "Weight": float(inp.get("Weight", 0.0)),
                    "Type": "X" if inp.get("Type", 0) == 0 else ("Y" if inp.get("Type") == 1 else "Angle"),
                    "Reflect": bool(inp.get("Reflect", False)),
                }
            )
        outputs = []
        for outp in sub.get("Output", []):
            dst = outp.get("Destination", {})
            outputs.append(
                {
                    "Destination": {
                        "Target": "Parameter",
                        "Id": dst.get("Id", outp.get("DestinationId", "")),
                    },
                    "VertexIndex": int(outp.get("VertexIndex", 0)),
                    "Scale": float(outp.get("Scale", 1.0)),
                    "Weight": float(outp.get("Weight", 1.0)),
                    "Type": "Angle",
                    "Reflect": bool(outp.get("Reflect", False)),
                }
            )
        vertices = []
        for v in sub.get("Particles", []):
            vertices.append(
                {
                    "Position": v.get("InitialPosition", {"X": 0.0, "Y": 0.0}),
                    "Mobility": float(v.get("Mobility", 0.9)),
                    "Delay": float(v.get("Delay", 0.9)),
                    "Acceleration": float(v.get("Acceleration", 1.0)),
                    "Radius": float(v.get("Radius", 3.0)),
                }
            )
        settings.append(
            {
                "Id": f"PhysicsSetting{i + 1}",
                "Normalization": sub.get("Normalization", {}),
                "Input": inputs,
                "Output": outputs,
                "Vertices": vertices,
            }
        )

    return {
        "Version": 3,
        "Meta": {
            "PhysicsSettingCount": len(settings),
            "EffectiveForces": {
                "Gravity": rig.get("Gravity", {"X": 0.0, "Y": -1.0}),
                "Wind": rig.get("Wind", {"X": 0.0, "Y": 0.0}),
            },
            "Fps": int(rig.get("Fps", 0)),
        },
        "PhysicsSettings": settings,
        "_raw_rig": rig,
    }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
