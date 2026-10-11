"""Loading the bundled songs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from whistle_trainer.music.model import Song
from whistle_trainer.music.musicxml import SongFormatError, parse_file

SONGS_DIR = Path(__file__).resolve().parent.parent / "resources" / "songs"
INTRO_SONG_ID = "introductory-exercise"


@dataclass
class SongLibrary:
    songs: list[Song] = field(default_factory=list)
    errors: list[SongFormatError] = field(default_factory=list)

    def get(self, song_id: str) -> Song | None:
        return next((s for s in self.songs if s.id == song_id), None)


def load_songs(directory: Path = SONGS_DIR) -> SongLibrary:
    """Every song in the directory, introductory exercise first, then by title."""
    library = SongLibrary()
    for path in sorted(directory.glob("*.musicxml")):
        try:
            library.songs.append(parse_file(path))
        except SongFormatError as error:
            library.errors.append(error)
    library.songs.sort(key=lambda s: (s.id != INTRO_SONG_ID, s.title.casefold()))
    return library
