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
    QMessageBox,
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
from whistle_trainer.music.transpose import spell_midi, suggest_transposition, transpose_song
from whistle_trainer.storage.progress import ProgressStore
from whistle_trainer.storage.settings import SettingsStore, SongPreferences


def format_length(total_seconds: float) -> str:
    minutes, seconds = divmod(round(total_seconds), 60)
    return f"{minutes}:{seconds:02d}"


class LibraryPage(QWidget):
    song_selected = Signal(str)  # song id
    start_requested = Signal(str, int)  # song id, first event
    listen_requested = Signal(str)  # song id
    audio_setup_requested = Signal()
    reset_all_requested = Signal()

    def __init__(self, library: SongLibrary, settings: SettingsStore, progress: ProgressStore,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.library = library
        self.store = settings
        self.progress = progress
        self.song: Song | None = None
        self.suggested: int | None = None
        self.confirm = self._ask

        self.song_list = QTreeWidget()
        self.song_list.setRootIsDecorated(False)
        self.song_list.setHeaderLabels([strings.LIBRARY_COLUMN_TITLE, strings.LIBRARY_COLUMN_LENGTH,
                                        strings.LIBRARY_COLUMN_RANGE, strings.LIBRARY_COLUMN_PROGRESS])
        header = self.song_list.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for song in library.songs:
            item = QTreeWidgetItem([song.title, format_length(song_seconds(song, song.tempo)),
                                    f"{song.lowest.name}–{song.highest.name}", ""])
            item.setData(0, Qt.ItemDataRole.UserRole, song.id)
            self.song_list.addTopLevelItem(item)
        self.song_list.itemActivated.connect(lambda _item, _column: self._start(0))

        hint = QLabel(strings.LIBRARY_LENGTH_HINT)
        hint.setWordWrap(True)
        self.note_names_check = QCheckBox(strings.LIBRARY_SHOW_NOTE_NAMES)
        self.note_names_check.setChecked(settings.settings.show_note_names)
        self.note_names_check.toggled.connect(self._on_note_names_toggled)
        self.reset_all_button = QPushButton(strings.LIBRARY_RESET_ALL)
        self.reset_all_button.clicked.connect(self._reset_all)
        below = QHBoxLayout()
        below.addWidget(self.note_names_check)
        below.addStretch()
        below.addWidget(self.reset_all_button)
        songs = QVBoxLayout()
        songs.addWidget(self.song_list)
        songs.addWidget(hint)
        songs.addLayout(below)
        if not library.songs:
            songs.insertWidget(0, QLabel(strings.LIBRARY_NO_SONGS))
        if library.errors:
            details = "\n".join(str(error) for error in library.errors)
            errors = QLabel(f"{strings.LIBRARY_LOAD_ERRORS}\n{details}")
            errors.setWordWrap(True)
            errors.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            songs.addWidget(errors)

        layout = QHBoxLayout(self)
        layout.addLayout(songs, stretch=2)
        layout.addWidget(self._build_panel(), stretch=1)

        self.song_list.currentItemChanged.connect(self._on_current_changed)
        self.refresh()
        if self.song_list.topLevelItemCount():
            self.song_list.setCurrentItem(self.song_list.topLevelItem(0))
        else:
            self._on_current_changed(None, None)

    def _build_panel(self) -> QGroupBox:
        self.song_title = QLabel()
        title_font = self.song_title.font()
        title_font.setPointSizeF(title_font.pointSizeF() * 1.3)
        title_font.setBold(True)
        self.song_title.setFont(title_font)
        self.song_title.setWordWrap(True)
        self.mode_combo = QComboBox()
        for mode in Mode:
            self.mode_combo.addItem(strings.MODE_NAMES[mode], mode)
        self.mode_description = QLabel()
        self.mode_description.setWordWrap(True)
        self.metronome_check = QCheckBox(strings.LIBRARY_METRONOME)
        self.metronome_check.setChecked(self.store.settings.metronome_sound)
        self.metronome_check.toggled.connect(self._on_metronome_toggled)
        self.tempo_spin = QSpinBox()
        self.tempo_spin.setRange(config.MIN_TEMPO, config.MAX_TEMPO)
        self.tempo_spin.setSuffix(strings.LIBRARY_TEMPO_SUFFIX)
        self.difficulty_combo = QComboBox()
        for difficulty in Difficulty:
            self.difficulty_combo.addItem(strings.DIFFICULTY_NAMES[difficulty], difficulty)
        self.transposition_spin = QSpinBox()
        self.transposition_spin.setRange(config.MIN_TRANSPOSITION, config.MAX_TRANSPOSITION)
        self.transposition_spin.setSuffix(strings.TRANSPOSITION_SUFFIX)
        for widget in (self.mode_combo, self.difficulty_combo):
            widget.currentIndexChanged.connect(self._on_preferences_changed)
        for widget in (self.tempo_spin, self.transposition_spin):
            widget.valueChanged.connect(self._on_preferences_changed)
        self.range_label = QLabel()
        self.suggestion_label = QLabel()
        self.suggestion_label.setWordWrap(True)
        self.use_suggestion_button = QPushButton(strings.LIBRARY_USE_SUGGESTION)
        self.use_suggestion_button.clicked.connect(self._use_suggestion)
        suggestion = QHBoxLayout()
        suggestion.addWidget(self.suggestion_label, stretch=1)
        suggestion.addWidget(self.use_suggestion_button)
        self.estimate_label = QLabel()
        self.estimate_label.setWordWrap(True)

        self.start_button = QPushButton(strings.LIBRARY_START)
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(lambda: self._start(0))
        self.continue_button = QPushButton()
        self.continue_button.clicked.connect(lambda: self._start(self._continue_index()))
        self.listen_button = QPushButton(strings.LIBRARY_LISTEN)
        self.listen_button.clicked.connect(lambda: self.song and self.listen_requested.emit(self.song.id))
        self.reset_song_button = QPushButton(strings.LIBRARY_RESET_SONG)
        self.reset_song_button.clicked.connect(self._reset_song)
        self.audio_setup_button = QPushButton(strings.LIBRARY_AUDIO_SETUP)
        self.audio_setup_button.clicked.connect(self.audio_setup_requested)

        form = QFormLayout()
        form.addRow(strings.LIBRARY_MODE, self.mode_combo)
        form.addRow(strings.LIBRARY_TEMPO, self.tempo_spin)
        form.addRow(strings.LIBRARY_DIFFICULTY, self.difficulty_combo)
        form.addRow(strings.LIBRARY_TRANSPOSITION, self.transposition_spin)
        panel = QGroupBox()
        panel_layout = QVBoxLayout(panel)
        panel_layout.addWidget(self.song_title)
        panel_layout.addLayout(form)
        panel_layout.addWidget(self.mode_description)
        panel_layout.addWidget(self.metronome_check)
        panel_layout.addWidget(self.range_label)
        panel_layout.addLayout(suggestion)
        panel_layout.addWidget(self.estimate_label)
        panel_layout.addWidget(self.start_button)
        panel_layout.addWidget(self.continue_button)
        panel_layout.addWidget(self.listen_button)
        panel_layout.addStretch()
        panel_layout.addWidget(self.reset_song_button)
        panel_layout.addWidget(self.audio_setup_button)
        panel.setMinimumWidth(320)
        return panel

    # Lifecycle

    def activate(self) -> None:
        self.refresh()
        self._update_panel()

    def refresh(self) -> None:
        """Update the progress column from the saved progress."""
        for i in range(self.song_list.topLevelItemCount()):
            item = self.song_list.topLevelItem(i)
            song = self.library.get(item.data(0, Qt.ItemDataRole.UserRole))
            item.setText(3, self._progress_text(song))

    def _progress_text(self, song: Song) -> str:
        mode = self.store.settings.preferences_for(song.id, song.tempo).mode
        progress = self.progress.songs.get(song.id, {}).get(mode)
        if progress is None:
            return strings.LIBRARY_PROGRESS_NONE
        count = len(progress.completions)
        if count:
            return strings.LIBRARY_PROGRESS_COMPLETE if count == 1 else \
                strings.LIBRARY_PROGRESS_COMPLETE_TIMES.format(count=count)
        if not progress.completed:
            return strings.LIBRARY_PROGRESS_NONE
        return strings.LIBRARY_PROGRESS_NOTES.format(done=len(progress.completed), total=progress.event_count)

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

    def _practice_range(self) -> tuple[int, int] | None:
        calibration = self.store.settings.calibrations.get(self.store.settings.input_device or "")
        if calibration is None or calibration.practice_low_midi is None or calibration.practice_high_midi is None:
            return None
        return calibration.practice_low_midi, calibration.practice_high_midi

    def _continue_index(self) -> int:
        """The next unfinished note saved for this song and mode, or 0 if there is none."""
        preferences = self.preferences()
        progress = self.progress.songs.get(self.song.id, {}).get(preferences.mode) if preferences else None
        if progress is None or not 0 < progress.next_index < len(self.song.events):
            return 0
        return progress.next_index

    # Panel

    def _on_current_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        self.song = self.library.get(current.data(0, Qt.ItemDataRole.UserRole)) if current else None
        if self.song is not None:
            # Every song starts at its own tempo; a changed tempo lasts while it stays selected.
            self.preferences().tempo = self.song.tempo
        self._update_panel()
        if self.song is not None:
            self.song_selected.emit(self.song.id)

    def _update_panel(self) -> None:
        preferences = self.preferences()
        widgets = (self.mode_combo, self.tempo_spin, self.difficulty_combo, self.transposition_spin)
        for widget in (*widgets, self.start_button, self.listen_button, self.reset_song_button):
            widget.setEnabled(self.song is not None)
        if self.song is None:
            for label in (self.song_title, self.estimate_label, self.range_label, self.suggestion_label):
                label.setText("")
            self.continue_button.hide()
            self.use_suggestion_button.hide()
            return
        self.song_title.setText(self.song.title)
        for widget in widgets:
            widget.blockSignals(True)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(preferences.mode))
        self.tempo_spin.setValue(preferences.tempo)
        self.difficulty_combo.setCurrentIndex(self.difficulty_combo.findData(preferences.difficulty))
        self.transposition_spin.setValue(preferences.transposition)
        for widget in widgets:
            widget.blockSignals(False)

        mode = Mode(self.mode_combo.currentData())
        self.mode_description.setText(strings.MODE_DESCRIPTIONS[mode])
        self.metronome_check.setVisible(mode is Mode.RHYTHM)
        length = format_length(song_seconds(self.song, preferences.tempo))
        self.estimate_label.setText(strings.LIBRARY_ESTIMATE.format(length=length))
        transposed = transpose_song(self.song, preferences.transposition)
        self.range_label.setText(strings.LIBRARY_RANGE.format(low=transposed.lowest.name, high=transposed.highest.name))

        practice_range = self._practice_range()
        self.suggested = None
        if practice_range is None:
            self.suggestion_label.hide()
            self.use_suggestion_button.hide()
        else:
            low, high = (spell_midi(m).name for m in practice_range)
            self.suggested = suggest_transposition(self.song, *practice_range)
            fits = self.suggested == preferences.transposition
            self.suggestion_label.setText(strings.LIBRARY_SUGGESTION_FITS.format(low=low, high=high) if fits else
                                          strings.LIBRARY_SUGGESTION.format(low=low, high=high, shift=self.suggested))
            self.suggestion_label.show()
            self.use_suggestion_button.setVisible(not fits)

        continue_index = self._continue_index()
        self.continue_button.setVisible(continue_index > 0)
        self.continue_button.setText(strings.LIBRARY_CONTINUE.format(note=continue_index + 1))

    def _on_preferences_changed(self) -> None:
        preferences = self.preferences()
        if preferences is None:
            return
        # Qt returns combo box data as plain strings.
        preferences.mode = Mode(self.mode_combo.currentData())
        preferences.tempo = self.tempo_spin.value()
        preferences.difficulty = Difficulty(self.difficulty_combo.currentData())
        preferences.transposition = self.transposition_spin.value()
        self.store.save()
        self.refresh()
        self._update_panel()

    def _use_suggestion(self) -> None:
        if self.suggested is not None:
            self.transposition_spin.setValue(self.suggested)

    def _on_metronome_toggled(self, checked: bool) -> None:
        self.store.settings.metronome_sound = checked
        self.store.save()

    def _on_note_names_toggled(self, checked: bool) -> None:
        self.store.settings.show_note_names = checked
        self.store.save()

    def _start(self, start: int) -> None:
        if self.song is not None:
            self.start_requested.emit(self.song.id, start)

    # Resets

    def _ask(self, text: str) -> bool:
        answer = QMessageBox.question(self, strings.APP_NAME, text,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Yes

    def _reset_song(self) -> None:
        if self.song is not None and self.confirm(strings.LIBRARY_RESET_SONG_CONFIRM.format(title=self.song.title)):
            self.progress.reset_song(self.song.id)
            self.progress.save()
            self.refresh()
            self._update_panel()

    def _reset_all(self) -> None:
        if self.confirm(strings.LIBRARY_RESET_ALL_CONFIRM):
            self.reset_all_requested.emit()

    def reload_settings(self) -> None:
        """After all data was cleared: show the defaults."""
        for check, value in ((self.metronome_check, self.store.settings.metronome_sound),
                             (self.note_names_check, self.store.settings.show_note_names)):
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)
        self.refresh()
        self._update_panel()
