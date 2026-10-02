"""Constants from the official RaceRoom shared-memory API 3.5."""

from enum import IntEnum


SHARED_MEMORY_NAME = "$R3E"
API_VERSION_MAJOR = 3
API_VERSION_MINOR = 5
MAX_DRIVERS = 128
TIRE_COUNT = 4
PIT_MENU_ITEM_COUNT = 12


class GameMode(IntEnum):
    UNAVAILABLE = -1
    TRACK_TEST = 0
    LEADERBOARD_CHALLENGE = 1
    COMPETITION = 2
    SINGLE_RACE = 3
    CHAMPIONSHIP = 4
    MULTIPLAYER = 5
    MULTIPLAYER_RANKED = 6
    TRY_BEFORE_YOU_BUY = 7


class SessionType(IntEnum):
    UNAVAILABLE = -1
    PRACTICE = 0
    QUALIFY = 1
    RACE = 2
    WARMUP = 3


class SessionPhase(IntEnum):
    UNAVAILABLE = -1
    GARAGE = 1
    GRIDWALK = 2
    FORMATION = 3
    COUNTDOWN = 4
    GREEN = 5
    CHECKERED = 6


class ControlType(IntEnum):
    UNAVAILABLE = -1
    PLAYER = 0
    AI = 1
    REMOTE = 2
    REPLAY = 3


# Control work is deliberately deny-by-default.  M2 may expand this only after
# explicit policy and game-in-the-loop validation.
READ_ONLY_ALLOWED_GAME_MODES = frozenset(
    {
        GameMode.TRACK_TEST,
        GameMode.SINGLE_RACE,
        GameMode.CHAMPIONSHIP,
        GameMode.TRY_BEFORE_YOU_BUY,
    }
)
CONTROL_ALLOWED_GAME_MODES = frozenset({GameMode.TRACK_TEST})
