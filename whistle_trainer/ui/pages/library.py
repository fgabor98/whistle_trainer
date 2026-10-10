"""Song library page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from whistle_trainer import strings
from whistle_trainer.music.library import SongLibrary
from whistle_trainer.music.model import Song
from whistle_trainer.music.timing import song_seconds


def format_length(total_seconds: float) -> str:
    minutes, seconds = divmod(round(total_seconds), 60)
    return f"{minutes}:{seconds:02d}"


class LibraryPage(QWidget):
    song_selected = Signal(str)  # song id

    def __init__(self, library: SongLibrary, parent: QWidget | None = None):
        super().__init__(parent)
        self.library = library

        self.song_list = QTreeWidget()
        self.song_list.setRootIsDecorated(False)
        self.song_list.setHeaderLabels(
            [strings.LIBRARY_COLUMN_TITLE, strings.LIBRARY_COLUMN_LENGTH, strings.LIBRARY_COLUMN_RANGE]
        )
        header = self.song_list.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for song in library.songs:
            self.song_list.addTopLevelItem(self._song_item(song))
        self.song_list.currentItemChanged.connect(self._on_current_changed)

        hint = QLabel(strings.LIBRARY_LENGTH_HINT)
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.song_list)
        layout.addWidget(hint)

        if not library.songs:
            layout.insertWidget(0, QLabel(strings.LIBRARY_NO_SONGS))
        if library.errors:
            details = "\n".join(str(error) for error in library.errors)
            errors = QLabel(f"{strings.LIBRARY_LOAD_ERRORS}\n{details}")
            errors.setWordWrap(True)
            errors.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(errors)

    def _song_item(self, song: Song) -> QTreeWidgetItem:
        item = QTreeWidgetItem([
            song.title,
            format_length(song_seconds(song, song.tempo)),
            f"{song.lowest.name}–{song.highest.name}",
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, song.id)
        return item

    def _on_current_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is not None:
            self.song_selected.emit(current.data(0, Qt.ItemDataRole.UserRole))

    def select_song(self, song_id: str) -> None:
        for i in range(self.song_list.topLevelItemCount()):
            item = self.song_list.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == song_id:
                self.song_list.setCurrentItem(item)
                return
