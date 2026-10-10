"""Guided mode: the song waits for each note or rest to be completed.

Rules from PROJECT_SPEC.md "Guided mode" and TECHNICAL_SPEC.md "Guided engine":
- A note passes after its written duration of accepted pitch at the tempo,
  including the stable confirmation time.
- A rest passes after its written duration of quiet input.
- A note with the same pitch as the previous note needs a release (100 ms
  without active input) before its attempt can start, so one continuous
  whistle can never clear two written notes. Tied notes are one event.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from whistle_trainer import config
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.assessment.hold import HoldStatus, HoldTracker, frames_for
from whistle_trainer.music.model import Event, Song
from whistle_trainer.music.timing import seconds


@dataclass(frozen=True)
class GuidedUpdate:
    index: int  # the event this frame was assessed against
    status: HoldStatus
    progress: float  # credited time as a fraction of the required time
    credit_s: float
    required_s: float
    cents: float | None  # this frame's deviation from the target note, if pitched
    needs_release: bool  # a repeated note is waiting for a release
    retry: bool  # this frame ended an attempt that had started holding
    finished: bool  # every event from the start position has passed


class GuidedEngine:
    def __init__(self, song: Song, tempo: float, tolerance_cents: float, hop_s: float, start_index: int = 0,
                 end_index: int | None = None):
        self.song = song
        self.end_index = len(song.events) if end_index is None else end_index  # exclusive
        self.tempo = tempo
        self.tolerance_cents = tolerance_cents
        self.hop_s = hop_s
        self.release_frames = frames_for(config.REPEATED_NOTE_RELEASE_S, hop_s)
        self.retries: dict[int, int] = {}
        self.completed: set[int] = set()
        self.start(start_index)

    @property
    def event(self) -> Event:
        return self.song.events[self.position]

    @property
    def finished(self) -> bool:
        return self.position >= self.end_index

    def required_s(self, event: Event) -> float:
        return seconds(event.duration, self.tempo)

    def start(self, index: int) -> None:
        """Make an event current, discarding any unfinished attempt."""
        self.position = index
        self.needs_release = False
        self._quiet_run = 0
        if self.finished:
            self.tracker = None
            return
        event = self.event
        previous = self.song.events[index - 1] if index > 0 else None
        self.needs_release = (
            event.is_note and previous is not None and previous.is_note
            and previous.pitch.midi == event.pitch.midi
        )
        confirmation = config.STABLE_CONFIRMATION_S if event.is_note else 0.0
        self.tracker = HoldTracker(self.required_s(event), confirmation, config.GRACE_PERIOD_S, self.hop_s)

    def reset_current(self) -> None:
        """Pause or settings change: restart the current event without a retry."""
        if not self.finished:
            self.start(self.position)

    def cents(self, frame: AnalysisFrame) -> float | None:
        if self.finished or not self.event.is_note:
            return None
        return frame.cents_from(self.event.pitch.frequency())

    def feed(self, frame: AnalysisFrame) -> GuidedUpdate:
        if self.finished:
            return GuidedUpdate(self.position, HoldStatus.PASSED, 1.0, 0.0, 0.0, None, False, False, True)
        index, event, tracker = self.position, self.event, self.tracker
        cents = self.cents(frame)
        retry = False
        needs_release = self.needs_release
        if needs_release:
            self._quiet_run = self._quiet_run + 1 if frame.frame_class is FrameClass.QUIET else 0
            if self._quiet_run >= self.release_frames:
                self.needs_release = False
        else:
            if event.is_note:
                acceptable = cents is not None and abs(cents) <= self.tolerance_cents
            else:
                acceptable = frame.frame_class is FrameClass.QUIET
            retry = tracker.feed(acceptable)
            if retry:
                self.retries[index] = self.retries.get(index, 0) + 1

        update = GuidedUpdate(
            index=index,
            status=tracker.status,
            progress=tracker.progress,
            credit_s=tracker.credit_s,
            required_s=self.required_s(event),
            cents=cents,
            needs_release=needs_release,
            retry=retry,
            finished=False,
        )
        if tracker.status is HoldStatus.PASSED:
            self.completed.add(index)
            self.start(index + 1)
            if self.finished:
                update = replace(update, finished=True)
        return update
