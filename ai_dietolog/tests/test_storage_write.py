import json
import math
from pathlib import Path

import pytest
from pydantic import BaseModel

from ai_dietolog.core import storage


class Dummy(BaseModel):
    x: float


def test_write_json_atomic_on_nan(tmp_path: Path):
    target = tmp_path / "data.json"
    # initial valid write
    storage.write_json(target, Dummy(x=1.0))
    assert json.loads(target.read_text()) == {"x": 1.0}

    # attempt to write NaN should raise and leave file untouched
    with pytest.raises(ValueError):
        storage.write_json(target, Dummy(x=math.nan))
    assert json.loads(target.read_text()) == {"x": 1.0}
