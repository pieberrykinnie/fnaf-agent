"""GameState and Action: the typed contract between perception, control, sim, and agents.

Coordinates and all perception are in the canonical 1280x720 frame.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class Screen(Enum):
    UNKNOWN = "unknown"
    TITLE_MENU = "title_menu"
    NIGHT_INTRO = "night_intro"  # "12 AM / 1st Night" card
    OFFICE = "office"
    CAMERA = "camera"
    JUMPSCARE = "jumpscare"
    GAME_OVER = "game_over"
    SIX_AM = "six_am"


class Camera(Enum):
    CAM_1A = "1A"  # Show Stage
    CAM_1B = "1B"  # Dining Area
    CAM_1C = "1C"  # Pirate Cove
    CAM_2A = "2A"  # West Hall
    CAM_2B = "2B"  # West Hall Corner
    CAM_3 = "3"  # Supply Closet
    CAM_4A = "4A"  # East Hall
    CAM_4B = "4B"  # East Hall Corner
    CAM_5 = "5"  # Backstage
    CAM_6 = "6"  # Kitchen (audio only)
    CAM_7 = "7"  # Restrooms


class Animatronic(Enum):
    FREDDY = "freddy"
    BONNIE = "bonnie"
    CHICA = "chica"
    FOXY = "foxy"


class ActionType(Enum):
    NOOP = "noop"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    DOOR_LEFT = "door_left"
    DOOR_RIGHT = "door_right"
    LIGHT_LEFT = "light_left"
    LIGHT_RIGHT = "light_right"
    MONITOR_TOGGLE = "monitor_toggle"
    SELECT_CAMERA = "select_camera"  # requires camera field
    MENU_NEW_GAME = "menu_new_game"
    MENU_CONTINUE = "menu_continue"


@dataclass(frozen=True)
class Action:
    type: ActionType
    camera: Camera | None = None

    def to_json(self) -> str:
        return json.dumps(
            {"type": self.type.value, "camera": self.camera.value if self.camera else None}
        )


@dataclass
class GameState:
    screen: Screen = Screen.UNKNOWN
    night: int | None = None
    hour: int | None = None  # 12 -> 0, 1..5
    power: int | None = None  # 0..99
    usage_bars: int | None = None  # 1..5
    door_left_closed: bool | None = None
    door_right_closed: bool | None = None
    light_left_on: bool | None = None
    light_right_on: bool | None = None
    monitor_up: bool | None = None
    active_camera: Camera | None = None
    animatronics_visible: list[Animatronic] = field(default_factory=list)
    frame_ms: float | None = None  # perception latency

    def to_json(self) -> str:
        d = asdict(self)
        d["screen"] = self.screen.value
        d["active_camera"] = self.active_camera.value if self.active_camera else None
        d["animatronics_visible"] = [a.value for a in self.animatronics_visible]
        return json.dumps(d, indent=2)

    @classmethod
    def from_json(cls, s: str) -> GameState:
        d = json.loads(s)
        d["screen"] = Screen(d["screen"])
        d["active_camera"] = Camera(d["active_camera"]) if d.get("active_camera") else None
        d["animatronics_visible"] = [Animatronic(a) for a in d.get("animatronics_visible", [])]
        return cls(**d)
