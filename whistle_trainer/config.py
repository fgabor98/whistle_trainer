"""Default values from PROJECT_SPEC.md "Proposed defaults", kept in one place."""

from enum import StrEnum


class Mode(StrEnum):
    GUIDED = "guided"
    RHYTHM = "rhythm"


class Difficulty(StrEnum):
    EASY = "easy"
    STANDARD = "standard"


class Sound(StrEnum):
    """How Listen and Hear note play notes. The first one is the default."""

    PIANO = "piano"
    WHISTLE = "whistle"


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

# Audio analysis (TECHNICAL_SPEC.md "Audio input and analysis").
SAMPLE_RATE = 48000
ANALYSIS_WINDOW_S = 2048 / 48000
ANALYSIS_HOP_S = 0.010
BANDPASS_LOW_HZ = 400.0
BANDPASS_HIGH_HZ = 4500.0
BANDPASS_LENGTH_S = 1025 / 48000
PITCH_MIN_HZ = 450.0
PITCH_MAX_HZ = 4200.0
YIN_THRESHOLD = 0.15
MIN_PITCH_CONFIDENCE = 0.8
SILENCE_DB = -120.0
# Used until the input has been set up.
UNCALIBRATED_THRESHOLD_DB = -50.0

# Detected note display smoothing.
DISPLAY_MEDIAN_FRAMES = 5
DISPLAY_STABLE_S = 0.050
DISPLAY_TIMEOUT_S = 0.150

# Audio setup.
SETUP_SILENCE_S = 3.0
SETUP_WHISTLE_S = 1.5
SETUP_WHISTLE_TIMEOUT_S = 10.0
SETUP_MIN_MARGIN_DB = 6.0
SETUP_MIN_USABLE_MARGIN_DB = 12.0
# Range measurement: steady pitch needed per note, time allowed per note, and the
# pause between the low and the high note.
SETUP_RANGE_NOTE_S = 2.0
SETUP_RANGE_TIMEOUT_S = 15.0
SETUP_RANGE_PAUSE_S = 3.0

# Test input: required hold of the single target note.
TEST_NOTE_HOLD_S = 1.0
# Random notes: the range used when no comfortable range was measured (D5 to E6, the
# range of the bundled songs), and the pause before the next note after a hit.
TEST_RANDOM_DEFAULT_RANGE = (74, 88)
TEST_RANDOM_NEXT_S = 1.5

# Rhythm mode: the count-in starts this long after the latest analyzed frame,
# leaving time to schedule the first clicks ahead of the output buffer.
COUNT_IN_LEAD_S = 0.5

# Hear target note: length of the reference, and how long the microphone is
# ignored after it ends so the app cannot hear itself.
REFERENCE_NOTE_S = 1.0
REFERENCE_SETTLE_S = 0.300

# Piano notes end like a released key: a short fade-out at the end of the note.
PIANO_RELEASE_S = 0.060
