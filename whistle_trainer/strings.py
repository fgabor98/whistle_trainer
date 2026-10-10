"""All user-facing text."""

APP_NAME = "Whistle Trainer"

PAGE_LIBRARY = "Song library"

BACK = "Back"
LISTENING = "Listening"

LIBRARY_COLUMN_TITLE = "Song"
LIBRARY_COLUMN_LENGTH = "Length"
LIBRARY_COLUMN_RANGE = "Range"
LIBRARY_LENGTH_HINT = "Lengths are at each song's default tempo, without waiting or retries."
LIBRARY_NO_SONGS = "No songs could be loaded."
LIBRARY_LOAD_ERRORS = "Some songs could not be loaded:"

SONG_ERROR = "{file}: {message}"
SONG_ERROR_IN_MEASURE = "{file}, measure {measure}: {message}"

SETTINGS_RESET = (
    "Your settings could not be read and have been reset to defaults. "
    "The unreadable file was kept as {backup}."
)
PROGRESS_RESET = (
    "Your saved progress could not be read and has been reset. "
    "The unreadable file was kept as {backup}."
)
PROGRESS_SONG_CHANGED = "Saved progress for these songs was reset because the songs have changed: {titles}"

PAGE_AUDIO_SETUP = "Audio setup"
PAGE_TEST_INPUT = "Test input"

LIBRARY_AUDIO_SETUP = "Audio setup…"

SETUP_INPUT = "Input:"
SETUP_OUTPUT = "Output:"
SETUP_ACTIVITY = "Activity:"
SETUP_DETECTED = "Detected note:"
SETUP_UNAVAILABLE = "{name} (not connected)"
SETUP_SYSTEM_DEFAULT = "{name} (system default)"
SETUP_NO_INPUTS = "No audio inputs were found. Connect a microphone."
SETUP_START = "Start setup"
SETUP_REPEAT = "Repeat setup"
SETUP_MEASURE_RANGE = "Measure my range"
SETUP_TEST_INPUT = "Test input"
SETUP_INTRO = "Press Start setup to measure your room and your whistle. It takes about 10 seconds."
SETUP_ALREADY_DONE = "This input is set up. Repeat setup any time, for example in a new room."
SETUP_INPUT_MISSING = (
    "The saved input “{name}” is not connected. Connect it, or choose another input. "
    "The app never switches inputs on its own."
)
SETUP_INPUT_FAILED = (
    "The input could not be opened. Check that it is connected and not in use, "
    "then choose it again or press Start setup."
)
SETUP_INPUT_LOST = (
    "The input stopped working. Check that it is connected, "
    "then choose it again or press Start setup."
)
SETUP_STEP_SILENCE = "Stay quiet for a few seconds while the background sound is measured."
SETUP_STEP_WHISTLE = "Now whistle one steady, comfortable note and hold it."
SETUP_DONE = "Setup complete. Background {noise:.0f} dB, whistle {whistle:.0f} dB, activity threshold {threshold:.0f} dB."
SETUP_NO_STEADY_WHISTLE = (
    "No steady whistle was detected. Whistle closer to the microphone, check that the right input "
    "is selected and its volume is not muted, then press Repeat setup."
)
SETUP_TOO_QUIET = (
    "The whistle is too quiet compared with the background ({whistle:.0f} dB against {noise:.0f} dB). "
    "Move closer to the microphone, raise the input volume, or reduce background noise, then press Repeat setup."
)
SETUP_RANGE_LOW = "Whistle your lowest comfortable note and hold it."
SETUP_RANGE_HIGH = "Now whistle your highest comfortable note and hold it."
SETUP_RANGE_DONE = "Your comfortable range is {low}–{high}. Songs can be transposed to fit it."
SETUP_RANGE_FAILED = "Your range could not be measured. Whistle each note steadily for a second, then try again."
SETUP_RANGE_SAVED = "Measured range: {low}–{high}."

TEST_TARGET = "Target note:"
TEST_DIFFICULTY = "Difficulty:"
TEST_TRY_AGAIN = "Try again"
TEST_TARGET_LABEL = "Whistle {note}"
TEST_PASSED = "✓ Well done! Press Try again or choose another note."
TEST_NOT_SET_UP = "Set up this input first on the Audio setup page."

DIFFICULTY_NAMES = {"easy": "Easy", "standard": "Standard"}

GUIDE_WHISTLE_HIGHER = "▲ Whistle higher"
GUIDE_WHISTLE_LOWER = "▼ Whistle lower"
GUIDE_HOLD = "● Hold this note"
GUIDE_KEEP_GOING = "● Keep going"
GUIDE_NO_CLEAR_PITCH = "No clear pitch"
GUIDE_START_WHEN_READY = "Start whenever you are ready."

DETECTED_NONE = "No clear pitch"
DETECTED_NOTE = "{note} ({cents:+.0f} cents)"
LEVEL_DB = "{level:.0f} dB"

LIBRARY_TEMPO = "Tempo:"
LIBRARY_TEMPO_SUFFIX = " bpm"
LIBRARY_DIFFICULTY = "Difficulty:"
LIBRARY_MODE = "Mode:"
MODE_NAMES = {"guided": "Guided", "rhythm": "Rhythm"}
MODE_DESCRIPTIONS = {
    "guided": "The song waits for you at every note.",
    "rhythm": "After a count-in, the song keeps the beat. A mistake stops it, and you retry from there.",
}
LIBRARY_METRONOME = "Metronome sound (use headphones)"
LIBRARY_START = "Start practice"
LIBRARY_ESTIMATE = "About {length} at this tempo, not counting waiting and retries."

PRACTICE_TARGET_NOTE = "Whistle {note}"
PRACTICE_TARGET_REST = "Rest"
PRACTICE_PAUSE = "Pause"
PRACTICE_RESUME = "Resume"
PRACTICE_RESTART = "Restart song"
PRACTICE_REPEAT = "Repeat"
PRACTICE_LIBRARY = "Library"
PRACTICE_AUDIO_SETUP = "Audio setup…"
PRACTICE_PAUSED = "Paused. Press Resume to continue from the highlighted note."
PRACTICE_NOT_SET_UP = "Set up your microphone before practicing."
PRACTICE_INPUT_MISSING = "The microphone “{name}” is not connected. Connect it, or choose another input in Audio setup."
PRACTICE_INPUT_LOST = (
    "The microphone stopped working, so practice is paused. "
    "Check that it is connected, then press Resume or open Audio setup."
)
PRACTICE_FINISHED = "✓ Song complete! Active practice time {time}, {retries} retries."
PRACTICE_FINISHED_NO_RETRIES = "✓ Song complete with no retries! Active practice time {time}."
PRACTICE_PROGRESS = "Note {current} of {total}"

HOLD_LABEL = "Hold: {seconds:.1f} of {required:.1f} s"
REST_LABEL = "Quiet: {seconds:.1f} of {required:.1f} s"

GUIDE_TAKE_BREATH = "Take a breath"
GUIDE_RELEASE = "Stop briefly, then whistle this note again"

PRACTICE_RETRY = "Retry"
GUIDE_COUNT_IN = "Get ready… {beat}"
GUIDE_WHISTLE_NOW = "Whistle {note} now"
RHYTHM_FAILED = {
    "late_or_missing": "✗ {target} did not start on the beat. Start each note with the beat.",
    "interrupted": "✗ {target} stopped or broke off too early. Hold each note for its full length.",
    "too_short": "✗ {target} was not held on pitch long enough. Hold each note for its full length.",
    "rest_not_quiet": "✗ The rest was not quiet. Stay silent during rests.",
}
RHYTHM_RETRY_HINT = "Press Retry to start again from this note with a new count-in."
