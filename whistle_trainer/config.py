"""Default values from PROJECT_SPEC.md "Proposed defaults", kept in one place."""

from enum import StrEnum


class Mode(StrEnum):
    GUIDED = "guided"
    RHYTHM = "rhythm"


class Difficulty(StrEnum):
    EASY = "easy"
    STANDARD = "standard"


DEFAULT_MODE = Mode.GUIDED
DEFAULT_DIFFICULTY = Difficulty.EASY

DEFAULT_TEMPO = 60
MIN_TEMPO = 30
MAX_TEMPO = 120

PITCH_TOLERANCE_CENTS = {Difficulty.EASY: 40.0, Difficulty.STANDARD: 25.0}
STABLE_CONFIRMATION_S = 0.100
GRACE_PERIOD_S = 0.100
REPEATED_NOTE_RELEASE_S = 0.100

COUNT_IN_BEATS = 4
ONSET_WINDOW_FRACTION = 0.20
ONSET_WINDOW_CAP_S = 0.150
RHYTHM_THRESHOLD_FRACTION = 0.80

MAX_FEEDBACK_DELAY_S = 0.150
SHOW_NOTE_NAMES = True

MIN_TRANSPOSITION = -12
MAX_TRANSPOSITION = 12

# The score is drawn this many octaves away from the sounding pitch.
WRITTEN_OCTAVE_OFFSET = -1

A4_HZ = 440.0
