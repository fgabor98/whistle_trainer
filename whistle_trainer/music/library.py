"""Loading the bundled songs and the songs the user added."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import platformdirs

from whistle_trainer.music.model import Song
from whistle_trainer.music.musicxml import SongFormatError, parse_file, parse_string

SONGS_DIR = Path(__file__).resolve().parent.parent / "resources" / "songs"
INTRO_SONG_ID = "introductory-exercise"
USER_SONG_PREFIX = "user-"


def default_user_songs_dir() -> Path:
    return platformdirs.user_data_path("whistle-trainer", appauthor=False) / "songs"


@dataclass
class SongLibrary:
    songs: list[Song] = field(default_factory=list)
    errors: list[SongFormatError] = field(default_factory=list)
    user_directory: Path | None = None
    paths: dict[str, Path] = field(default_factory=dict)  # files of added songs, by song id

    def get(self, song_id: str) -> Song | None:
        return next((s for s in self.songs if s.id == song_id), None)

    def remove(self, song_id: str) -> None:
        """Delete an added song's file and forget it."""
        path = self.paths.pop(song_id, None)
        if path is None:
            raise ValueError(f"{song_id} is not an added song")
        path.unlink(missing_ok=True)
        self.songs = [s for s in self.songs if s.id != song_id]


def _parse_user_song(path: Path) -> Song:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SongFormatError(path.name, f"cannot be read ({error})") from error
    song = parse_string(text, song_id=USER_SONG_PREFIX + path.stem, file_name=path.name)
    return replace(song, user_added=True)


def load_songs(directory: Path = SONGS_DIR, user_directory: Path | None = None) -> SongLibrary:
    """The bundled songs (introductory exercise first, then by title), then the added songs by title."""
    library = SongLibrary(user_directory=user_directory)
    bundled = []
    for path in sorted(directory.glob("*.musicxml")):
        try:
            bundled.append(parse_file(path))
        except SongFormatError as error:
            library.errors.append(error)
    bundled.sort(key=lambda s: (s.id != INTRO_SONG_ID, s.title.casefold()))
    added = []
    if user_directory is not None and user_directory.is_dir():
        for path in sorted(user_directory.glob("*.musicxml")):
            try:
                song = _parse_user_song(path)
            except SongFormatError as error:
                library.errors.append(error)
                continue
            added.append(song)
            library.paths[song.id] = path
    added.sort(key=lambda s: s.title.casefold())
    library.songs = bundled + added
    return library
