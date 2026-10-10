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
