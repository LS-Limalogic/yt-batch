import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def yt_batch_module():
    module_path = Path(__file__).resolve().parents[1] / "yt-batch.py"
    spec = importlib.util.spec_from_file_location("yt_batch", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def args_factory():
    def make_args(**overrides):
        defaults = {
            "model": "1",
            "shifts": 1,
            "quality": 192,
            "keep_original": False,
            "source": "ytm",
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return make_args
