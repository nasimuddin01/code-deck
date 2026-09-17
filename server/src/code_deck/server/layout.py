"""Layout schema + persistence.

A layout is what the builder edits and the player renders: a list of widgets
with positions on the 320x480 screen, plus device/overlay settings. The user's
layout lives at CODE_DECK_HOME/layout.json; the packaged default reproduces the
v1 screen. Item types are validated client-side against the widget registry;
the server only guarantees shape and bounds so an old layout can never crash it.
"""
from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..config import HOME

SCREEN_W, SCREEN_H = 320, 480


class Screen(BaseModel):
    w: int = SCREEN_W
    h: int = SCREEN_H


class LayoutItem(BaseModel):
    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)
    props: dict[str, Any] = Field(default_factory=dict)
    locked: bool = False
    hidden: bool = False


class Settings(BaseModel):
    overlay_enabled: bool = True
    overlay_seconds: float = Field(10.0, gt=0, le=120)
    brightness: int = Field(39, ge=0, le=255)
    refresh_seconds: float = Field(10.0, ge=1, le=300)


class Layout(BaseModel):
    schema_version: Literal[1] = 1
    screen: Screen = Field(default_factory=Screen)
    grid: int = Field(8, ge=1)
    items: list[LayoutItem] = Field(default_factory=list)  # z-order = array order
    settings: Settings = Field(default_factory=Settings)

    @model_validator(mode="after")
    def _items_inside_screen(self) -> "Layout":
        ids: set[str] = set()
        for it in self.items:
            if it.id in ids:
                raise ValueError(f"duplicate item id {it.id!r}")
            ids.add(it.id)
            if it.x + it.w > self.screen.w or it.y + it.h > self.screen.h:
                raise ValueError(
                    f"item {it.id!r} ({it.x},{it.y} {it.w}x{it.h}) exceeds the "
                    f"{self.screen.w}x{self.screen.h} screen")
        return self


def default_layout() -> Layout:
    text = resources.files("code_deck").joinpath("layouts/default.json").read_text()
    return Layout.model_validate_json(text)


class LayoutStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (HOME / "layout.json")
        self.rev = 0

    def load(self) -> Layout:
        try:
            return Layout.model_validate_json(self.path.read_text())
        except FileNotFoundError:
            return default_layout()
        except ValueError:
            # a corrupt user file must not take the device down
            return default_layout()

    def save(self, layout: Layout) -> Layout:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(layout.model_dump(), indent=2))
        os.replace(tmp, self.path)  # atomic: the player never reads a half-written file
        self.rev += 1
        return layout

    def reset(self) -> Layout:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        self.rev += 1
        return default_layout()
