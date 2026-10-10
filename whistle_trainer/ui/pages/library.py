"""Song library page with the preparation panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from whistle_trainer import config, strings
from whistle_trainer.config import Difficulty, Mode
from whistle_trainer.music.library import SongLibrary
from whistle_trainer.music.model import Song
from whistle_trainer.music.timing import song_seconds
from whistle_trainer.storage.settings import SettingsStore, SongPreferences


def format_length(total_seconds: float) -> str:
    minutes, seconds = divmod(round(total_seconds), 60)
    return f"{minutes}:{seconds:02d}"


class LibraryPage(QWidget):
    song_selected = Signal(str)  # song id
    start_requested = Signal(str)  # song id
    audio_setup_requested = Signal()

    def __init__(self, library: SongLibrary, settings: SettingsStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.library = library
        self.store = settings
        self.song: Song | None = None

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
        self.song_list.itemActivated.connect(lambda _item, _column: self._start())

        hint = QLabel(strings.LIBRARY_LENGTH_HINT)
        hint.setWordWrap(True)
        songs = QVBoxLayout()
        songs.addWidget(self.song_list)
        songs.addWidget(hint)
        if not library.songs:
            songs.insertWidget(0, QLabel(strings.LIBRARY_NO_SONGS))
        if library.errors:
            details = "\n".join(str(error) for error in library.errors)
            errors = QLabel(f"{strings.LIBRARY_LOAD_ERRORS}\n{details}")
            errors.setWordWrap(True)
            errors.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            songs.addWidget(errors)

        self.song_title = QLabel()
        title_font = self.song_title.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.3)
        title_font.setBold(True)
        self.song_title.setFont(title_font)
        self.song_title.setWordWrap(True)
        self.mode_combo = QComboBox()
        for mode in Mode:
            self.mode_combo.addItem(strings.MODE_NAMES[mode], mode)
        self.mode_combo.currentIndexChanged.connect(self._on_preferences_changed)
        self.mode_description = QLabel()
        self.mode_description.setWordWrap(True)
        self.metronome_check = QCheckBox(strings.LIBRARY_METRONOME)
        self.metronome_check.setChecked(settings.settings.metronome_sound)
        self.metronome_check.toggled.connect(self._on_metronome_toggled)
        self.tempo_spin = QSpinBox()
        self.tempo_spin.setRange(config.MIN_TEMPO, config.MAX_TEMPO)
        self.tempo_spin.setSuffix(strings.LIBRARY_TEMPO_SUFFIX)
        self.tempo_spin.valueChanged.connect(self._on_preferences_changed)
        self.difficulty_combo = QComboBox()
        for difficulty in Difficulty:
            self.difficulty_combo.addItem(strings.DIFFICULTY_NAMES[difficulty], difficulty)
        self.difficulty_combo.currentIndexChanged.connect(self._on_preferences_changed)
        self.estimate_label = QLabel()
        self.estimate_label.setWordWrap(True)
        self.start_button = QPushButton(strings.LIBRARY_START)
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._start)
        self.audio_setup_button = QPushButton(strings.LIBRARY_AUDIO_SETUP)
        self.audio_setup_button.clicked.connect(self.audio_setup_requested)

        form = QFormLayout()
        form.addRow(strings.LIBRARY_MODE, self.mode_combo)
        form.addRow(strings.LIBRARY_TEMPO, self.tempo_spin)
        form.addRow(strings.LIBRARY_DIFFICULTY, self.difficulty_combo)
        panel = QGroupBox()
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(self.song_title)
        panel_layout.addLayout(form)
        panel_layout.addWidget(self.mode_description)
        panel_layout.addWidget(self.metronome_check)
        panel_layout.addWidget(self.estimate_label)
        panel_layout.addWidget(self.start_button)
        panel_layout.addStretch()
        panel_layout.addWidget(self.audio_setup_button)
        panel.setMinimumWidth(300)

        layout = QHBoxLayout(self)
        layout.addLayout(songs, stretch=2)
        layout.addWidget(panel, stretch=1)

        self.song_list.currentItemChanged.connect(self._on_current_changed)
        if self.song_list.topLevelItemCount():
            self.song_list.setCurrentItem(self.song_list.topLevelItem(0))
        else:
            self._on_current_changed(None, None)

    def _song_item(self, song: Song) -> QTreeWidgetItem:
        item = QTreeWidgetItem([
            song.title,
            format_length(song_seconds(song, song.tempo)),
            f"{song.lowest.name}–{song.highest.name}",
        ])
        item.setData(0, Qt.ItemDataRole.UserRole, song.id)
        return item

    def select_song(self, song_id: str) -> None:
        for i in range(self.song_list.topLevelItemCount()):
            item = self.song_list.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == song_id:
                self.song_list.setCurrentItem(item)
                return

    def preferences(self) -> SongPreferences | None:
        if self.song is None:
            return None
        return self.store.settings.preferences_for(self.song.id, self.song.tempo)

    def _on_current_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        self.song = self.library.get(current.data(0, Qt.ItemDataRole.UserRole)) if current else None
        preferences = self.preferences()
        for widget in (self.mode_combo, self.tempo_spin, self.difficulty_combo, self.start_button):
            widget.setEnabled(self.song is not None)
        if self.song is None:
            self.song_title.setText("")
            self.estimate_label.setText("")
            return
        self.song_title.setText(self.song.title)
        widgets = (self.mode_combo, self.tempo_spin, self.difficulty_combo)
        for widget in widgets:
            widget.blockSignals(True)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(preferences.mode))
        self.tempo_spin.setValue(preferences.tempo)
        self.difficulty_combo.setCurrentIndex(self.difficulty_combo.findData(preferences.difficulty))
        for widget in widgets:
            widget.blockSignals(False)
        self._update_estimate()
        self._update_mode()
        self.song_selected.emit(self.song.id)

    def _on_preferences_changed(self) -> None:
        preferences = self.preferences()
        if preferences is None:
            return
        # Qt returns combo box data as plain strings.
        preferences.mode = Mode(self.mode_combo.currentData())
        preferences.tempo = self.tempo_spin.value()
        preferences.difficulty = Difficulty(self.difficulty_combo.currentData())
        self.store.save()
        self._update_estimate()
        self._update_mode()

    def _on_metronome_toggled(self, checked: bool) -> None:
        self.store.settings.metronome_sound = checked
        self.store.save()

    def _update_mode(self) -> None:
        mode = Mode(self.mode_combo.currentData())
        self.mode_description.setText(strings.MODE_DESCRIPTIONS[mode])
        self.metronome_check.setVisible(mode is Mode.RHYTHM)

    def _update_estimate(self) -> None:
        length = format_length(song_seconds(self.song, self.tempo_spin.value()))
        self.estimate_label.setText(strings.LIBRARY_ESTIMATE.format(length=length))

    def _start(self) -> None:
        if self.song is not None:
            self.start_requested.emit(self.song.id)
