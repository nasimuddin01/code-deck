"""The .env loader and the generated .env.example."""
import os
from pathlib import Path

from code_deck import config
from code_deck.cli import EXAMPLE_HEADER

REPO = Path(__file__).resolve().parents[2]


def test_env_example_is_generated_from_spec():
    # regenerate with: uv run code-deck env example > ../.env.example
    assert (REPO / ".env.example").read_text() == config.render_env_file(header=EXAMPLE_HEADER)


def test_every_spec_key_is_documented():
    text = (REPO / ".env.example").read_text()
    for name, *_ in config.ENV_SPEC:
        assert f"CODE_DECK_{name}=" in text


def test_parse_env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        "# comment\n"
        "CODE_DECK_PORT=9000\n"
        "export CODE_DECK_HOST = 0.0.0.0\n"
        "CODE_DECK_HOME=\"~/my deck\"\n"
        "CODE_DECK_RENDERER=pil # trailing comment\n"
        "not a line\n"
    )
    assert config.parse_env_file(f) == {
        "CODE_DECK_PORT": "9000",
        "CODE_DECK_HOST": "0.0.0.0",
        "CODE_DECK_HOME": "~/my deck",
        "CODE_DECK_RENDERER": "pil",
    }


def test_load_env_only_prefixed_and_never_overrides(tmp_path, monkeypatch):
    f = tmp_path / "deck.env"
    f.write_text("CODE_DECK_PORT=9001\nCODE_DECK_OTLP_PORT=5000\nOTHER_SECRET=nope\n")
    monkeypatch.setenv("CODE_DECK_ENV_FILE", str(f))
    monkeypatch.setenv("CODE_DECK_OTLP_PORT", "4444")       # real env wins
    monkeypatch.delenv("CODE_DECK_PORT", raising=False)
    monkeypatch.delenv("OTHER_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)                              # no ./.env here
    used = config.load_env()
    try:
        assert f in used
        assert os.environ["CODE_DECK_PORT"] == "9001"
        assert os.environ["CODE_DECK_OTLP_PORT"] == "4444"
        assert "OTHER_SECRET" not in os.environ
        assert "CODE_DECK_PORT" in config.FROM_FILES
        assert "CODE_DECK_OTLP_PORT" not in config.FROM_FILES
    finally:
        os.environ.pop("CODE_DECK_PORT", None)


def test_render_env_file_writes_given_values_live():
    text = config.render_env_file({"CODE_DECK_PORT": "9002"})
    assert "\nCODE_DECK_PORT=9002\n" in text
    assert "# CODE_DECK_HOST=127.0.0.1" in text
