"""Safe Unity AssetBundle & Cubism helpers (avoids crash-prone Sprite/all-MonoBehaviour dumps)."""

from __future__ import annotations

import json
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

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            d = obj.read()
            base_name = getattr(d, "m_Name", "") or f"tex_{obj.path_id}"
            fname = f"{name_prefix}{base_name}.png"
            dest = out_dir / fname
            d.image.save(dest)
            saved.append(dest)
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

    return saved


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
