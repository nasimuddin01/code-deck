import json

import pytest
from pydantic import ValidationError

from code_deck.server.layout import Layout, LayoutStore, default_layout


def test_default_layout_validates_and_fits_screen():
    lay = default_layout()
    assert lay.schema_version == 1 and lay.screen.w == 320 and lay.screen.h == 480
    types = {i.type for i in lay.items}
    assert {"Header", "AccountCard", "SessionList", "Footer", "NeedsYouOverlay"} <= types


def test_item_outside_screen_rejected():
    bad = default_layout().model_dump()
    bad["items"][0]["w"] = 400
    with pytest.raises(ValidationError):
        Layout.model_validate(bad)


def test_duplicate_ids_rejected():
    bad = default_layout().model_dump()
    bad["items"][1]["id"] = bad["items"][0]["id"]
    with pytest.raises(ValidationError):
        Layout.model_validate(bad)


def test_unknown_schema_version_rejected():
    bad = default_layout().model_dump()
    bad["schema_version"] = 2
    with pytest.raises(ValidationError):
        Layout.model_validate(bad)


def test_store_roundtrip_atomic_and_reset(tmp_path):
    ls = LayoutStore(tmp_path / "layout.json")
    assert ls.load().items[0].id == "header"      # falls back to default
    lay = ls.load()
    lay.items[0].props["title"] = "MY DECK"
    ls.save(lay)
    assert not (tmp_path / "layout.json.tmp").exists()
    assert json.loads((tmp_path / "layout.json").read_text())["items"][0]["props"]["title"] == "MY DECK"
    assert ls.load().items[0].props["title"] == "MY DECK"
    ls.reset()
    assert not (tmp_path / "layout.json").exists()
    assert ls.load().items[0].props["title"] == "CODE DECK"


def test_corrupt_user_file_falls_back(tmp_path):
    p = tmp_path / "layout.json"
    p.write_text("{not json")
    assert LayoutStore(p).load().items[0].id == "header"
