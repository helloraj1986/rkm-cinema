"""The offline staging knobs must REACH the api container (his report, 2026-09-18).

REGRESSION: `services/offline.py` has read `RKM_OFFLINE_STAGING`, `RKM_OFFLINE_TTL_HOURS` and
`RKM_OFFLINE_MAX_BYTES` since B1, but `render_config.py::build_api_vars` — the ONLY writer of
`.rkm.env`, which is the api container's `env_file` — never passed any of them. So the 12 GiB cap was
forced, and the refusal's own advice ("raise the cap (RKM_OFFLINE_MAX_BYTES)") could not be followed:
setting it in the repo `.env` changed nothing, because compose reads that file for INTERPOLATION only
and the container reads `.rkm.env`.

What he saw: every poster's Download said *"the server's download storage is full"*.

⚠ `render_config` is loaded BY PATH, exactly as `test_render_config.py` does it — it lives at the repo
root, is not an installed module, and nothing here calls `main()`, so the real `.env` is never touched.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root

#: The minimum a render needs to run at all — `build_api_vars` REFUSES (exit 2) without a TMDB key.
#: Same base as `test_render_config.py`, so the two files agree about what a valid env looks like.
BASE = {"MEDIA_SERVER": "jellyfin", "TMDB_API_KEY": "k"}

CAP_DEFAULT = 12 * 1024 ** 3


@pytest.fixture(scope="module")
def rc():
    spec = importlib.util.spec_from_file_location("render_config_offline_test", ROOT / "render_config.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_knobs_are_rendered_at_all(rc):
    api = rc.build_api_vars(dict(BASE))
    assert "RKM_OFFLINE_STAGING" in api
    assert "RKM_OFFLINE_TTL_HOURS" in api
    assert "RKM_OFFLINE_MAX_BYTES" in api


def test_defaults_are_the_codes_own(rc):
    api = rc.build_api_vars(dict(BASE))
    assert api["RKM_OFFLINE_STAGING"] == "/shared/offline"
    assert api["RKM_OFFLINE_TTL_HOURS"] == "48"
    assert api["RKM_OFFLINE_MAX_BYTES"] == str(CAP_DEFAULT)


def test_env_overrides_are_honoured(rc):
    api = rc.build_api_vars(dict(
        BASE,
        RKM_OFFLINE_STAGING="/mnt/roomy/offline",
        RKM_OFFLINE_TTL_HOURS="12",
        RKM_OFFLINE_MAX_BYTES=str(60 * 1024 ** 3),
    ))
    assert api["RKM_OFFLINE_STAGING"] == "/mnt/roomy/offline"
    assert api["RKM_OFFLINE_TTL_HOURS"] == "12"
    assert api["RKM_OFFLINE_MAX_BYTES"] == str(60 * 1024 ** 3)


def test_zero_survives_rendering(rc):
    """⚠ `0` is a REAL value for both numeric knobs — no cap, and never sweep.

    A `or "48"`-style default would treat the string "0" as falsy and silently put the 12 GiB budget
    back, which is the exact bug this file exists to prevent: the fix would appear not to work.
    """
    api = rc.build_api_vars(dict(BASE, RKM_OFFLINE_MAX_BYTES="0", RKM_OFFLINE_TTL_HOURS="0"))
    assert api["RKM_OFFLINE_MAX_BYTES"] == "0"
    assert api["RKM_OFFLINE_TTL_HOURS"] == "0"


def test_a_blank_value_falls_back_rather_than_rendering_empty(rc):
    """An empty line in `.env` means "not set", not "staging at the empty path"."""
    api = rc.build_api_vars(dict(BASE, RKM_OFFLINE_STAGING="   ", RKM_OFFLINE_MAX_BYTES=""))
    assert api["RKM_OFFLINE_STAGING"] == "/shared/offline"
    assert api["RKM_OFFLINE_MAX_BYTES"] == str(CAP_DEFAULT)
