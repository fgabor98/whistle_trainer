"""Application setup, main window, and page navigation."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from whistle_trainer import strings
from whistle_trainer.music.library import SongLibrary, load_songs
from whistle_trainer.storage.progress import ProgressStore
from whistle_trainer.storage.settings import SettingsStore
from whistle_trainer.ui.pages.library import LibraryPage


class MainWindow(QMainWindow):
    def __init__(self, library: SongLibrary, settings: SettingsStore, progress: ProgressStore):
        super().__init__()
        self.library = library
        self.settings = settings
        self.progress = progress
        self.setWindowTitle(strings.APP_NAME)
        self.resize(1000, 700)

        self.back_button = QPushButton(strings.BACK)
        self.back_button.clicked.connect(self.go_back)
        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.4)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.listening_label = QLabel(f"● {strings.LISTENING}")
        self.listening_label.hide()

        header = QHBoxLayout()
        header.addWidget(self.back_button)
        header.addWidget(self.title_label, stretch=1)
        header.addWidget(self.listening_label)

        self.pages = QStackedWidget()
        self.library_page = LibraryPage(library)
        self.library_page.song_selected.connect(self._on_song_selected)
        self.pages.addWidget(self.library_page)
        self.page_titles = {self.library_page: strings.PAGE_LIBRARY}
        self.history: list[QWidget] = []

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(header)
        layout.addWidget(self.pages, stretch=1)
        self.setCentralWidget(central)

        self.show_page(self.library_page, remember=False)
        if settings.settings.last_song_id:
            self.library_page.select_song(settings.settings.last_song_id)

    def show_page(self, page: QWidget, remember: bool = True) -> None:
        if remember and self.pages.currentWidget() is not page:
            self.history.append(self.pages.currentWidget())
        self.pages.setCurrentWidget(page)
        self.title_label.setText(self.page_titles[page])
        self.back_button.setVisible(bool(self.history))

    def go_back(self) -> None:
        if self.history:
            self.show_page(self.history.pop(), remember=False)

    def set_listening(self, active: bool) -> None:
        self.listening_label.setVisible(active)

    def _on_song_selected(self, song_id: str) -> None:
        self.settings.settings.last_song_id = song_id

    def closeEvent(self, event) -> None:
        self.settings.save()
        self.progress.save()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(strings.APP_NAME)
    app.setDesktopFileName("whistle-trainer")

    settings = SettingsStore()
    progress = ProgressStore()
    messages = [m for m in (settings.load(), progress.load()) if m]

    library = load_songs()
    changed = progress.reset_changed_songs((s.id, len(s.events)) for s in library.songs)
    if changed:
        titles = ", ".join(library.get(song_id).title for song_id in changed)
        messages.append(strings.PROGRESS_SONG_CHANGED.format(titles=titles))

    window = MainWindow(library, settings, progress)
    window.show()
    for message in messages:
        QTimer.singleShot(0, lambda m=message: QMessageBox.warning(window, strings.APP_NAME, m))
    return app.exec()
