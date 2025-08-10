import tempfile
from datetime import datetime
from pathlib import Path

from ai_dietolog.core import storage
from ai_dietolog.core.schema import Item, Meal, Total, Today


def test_save_today_preserves_existing_meals(tmp_path):
    # use temporary data directory
    storage.DATA_DIR = tmp_path
    meal1 = Meal(
        id="1",
        type="breakfast",
        items=[Item(name="apple", kcal=50)],
        total=Total(kcal=50),
        timestamp=datetime.utcnow(),
    )
    meal2 = Meal(
        id="2",
        type="lunch",
        items=[Item(name="soup", kcal=100)],
        total=Total(kcal=100),
        timestamp=datetime.utcnow(),
    )
    # initial save with first meal
    storage.save_today(1, Today(meals=[meal1], summary=Total(kcal=50)))
    # saving a new Today instance with only the second meal previously
    # replaced the existing meal; ensure both meals are kept now
    storage.save_today(1, Today(meals=[meal2], summary=Total(kcal=150)))
    loaded = storage.load_today(1)
    assert {m.id for m in loaded.meals} == {"1", "2"}
    assert loaded.summary.kcal == 150
