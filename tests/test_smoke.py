"""Smoke tests: package imports and the GameState/Action contract round-trips."""

from fnaf_agent.state import Action, ActionType, Animatronic, Camera, GameState, Screen


def test_import() -> None:
    import fnaf_agent

    assert fnaf_agent.__version__


def test_gamestate_roundtrip() -> None:
    s = GameState(
        screen=Screen.CAMERA,
        night=1,
        hour=3,
        power=76,
        monitor_up=True,
        active_camera=Camera.CAM_4B,
        animatronics_visible=[Animatronic.CHICA],
    )
    assert GameState.from_json(s.to_json()) == s


def test_action_json() -> None:
    a = Action(ActionType.SELECT_CAMERA, camera=Camera.CAM_1C)
    assert '"1C"' in a.to_json()
