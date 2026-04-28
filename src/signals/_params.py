from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARAMS_PATH = PROJECT_ROOT / "config" / "params.yaml"


def load_params(path: Path | str = DEFAULT_PARAMS_PATH) -> dict[str, Any]:
    params_path = Path(path)
    payload = yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}
    if "l1_regime" not in payload or "l2_breadth" not in payload:
        raise RuntimeError(f"Invalid signal params: {params_path}")
    return payload
