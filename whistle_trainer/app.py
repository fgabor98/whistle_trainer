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
from whistle_trainer.audio.capture import AudioInput
from whistle_trainer.audio.devices import AudioDevices
from whistle_trainer.music.library import SongLibrary, load_songs
from whistle_trainer.storage.progress import ProgressStore
from whistle_trainer.storage.settings import SettingsStore
from whistle_trainer.ui.pages.library import LibraryPage
from whistle_trainer.ui.pages.practice import PracticePage
from whistle_trainer.ui.pages.setup import SetupPage
from whistle_trainer.ui.pages.test_input import TestInputPage


class MainWindow(QMainWindow):
    def __init__(self, library: SongLibrary, settings: SettingsStore, progress: ProgressStore,
                 devices: AudioDevices, audio: AudioInput):
        super().__init__()
        self.library = library
        self.settings = settings
        self.progress = progress
        self.audio = audio
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
        audio.running_changed.connect(self.set_listening)

        header = QHBoxLayout()
        header.addWidget(self.back_button)
        header.addWidget(self.title_label, stretch=1)
        header.addWidget(self.listening_label)

        self.pages = QStackedWidget()
        self.library_page = LibraryPage(library, settings)
        self.library_page.song_selected.connect(self._on_song_selected)
        self.library_page.start_requested.connect(self.start_practice)
        self.library_page.audio_setup_requested.connect(lambda: self.show_page(self.setup_page))
        self.setup_page = SetupPage(devices, audio, settings)
        self.setup_page.test_input_requested.connect(lambda: self.show_page(self.test_input_page))
        self.test_input_page = TestInputPage(devices, audio, settings)
        self.practice_page = PracticePage(devices, audio, settings)
        self.practice_page.audio_setup_requested.connect(lambda: self.show_page(self.setup_page))
        self.practice_page.library_requested.connect(self.show_library)
        self.page_titles = {
            self.library_page: strings.PAGE_LIBRARY,
            self.setup_page: strings.PAGE_AUDIO_SETUP,
            self.test_input_page: strings.PAGE_TEST_INPUT,
            self.practice_page: "",
        }
        for page in self.page_titles:
            self.pages.addWidget(page)
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
        current = self.pages.currentWidget()
        if current is not page:
            if remember:
                self.history.append(current)
            if hasattr(current, "deactivate"):
                current.deactivate()
        self.pages.setCurrentWidget(page)
        if hasattr(page, "activate"):
            page.activate()
        self.title_label.setText(page.title() if hasattr(page, "title") else self.page_titles[page])
        self.back_button.setVisible(bool(self.history))

    def show_library(self) -> None:
        self.show_page(self.library_page, remember=False)
        self.history.clear()
        self.back_button.hide()

    def start_practice(self, song_id: str) -> None:
        song = self.library.get(song_id)
        self.practice_page.load(song, self.settings.settings.preferences_for(song.id, song.tempo))
        self.show_page(self.practice_page)

    def go_back(self) -> None:
        if self.history:
            self.show_page(self.history.pop(), remember=False)

    def set_listening(self, active: bool) -> None:
        self.listening_label.setVisible(active)

    def _on_song_selected(self, song_id: str) -> None:
        self.settings.settings.last_song_id = song_id

    def closeEvent(self, event) -> None:
        current = self.pages.currentWidget()
        if hasattr(current, "deactivate"):
            current.deactivate()
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

    devices = AudioDevices()
    audio = AudioInput()
    window = MainWindow(library, settings, progress, devices, audio)
    window.show()
    for message in messages:
        QTimer.singleShot(0, lambda m=message: QMessageBox.warning(window, strings.APP_NAME, m))
    try:
        return app.exec()
    finally:
        audio.shutdown()
