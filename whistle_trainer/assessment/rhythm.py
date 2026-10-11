"""Continuous rhythm mode: the song follows the beat after a count-in.

Rules from PROJECT_SPEC.md "Continuous rhythm mode" and TECHNICAL_SPEC.md
"Rhythm engine". All times are on the capture clock, taken from frames.

- A note must start inside its onset window and contain accepted pitch for at
  least 80 percent of its scheduled interval. Pitch before the interval
  establishes the onset but earns no credit.
- After the onset, an interruption longer than the grace period fails the
  note, unless it has already earned 80 percent.
- A rest needs 80 percent quiet and no active stretch longer than the grace
  period. Pitch matching the next note inside that note's early onset window
  counts as quiet, so starting the next note early never fails a rest.
- Events pass at their scheduled end; the first failure stops the song.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from whistle_trainer import config
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.assessment.hold import frames_for
from whistle_trainer.music.model import Event, Song
from whistle_trainer.music.timing import beat_seconds, seconds


class RhythmStatus(StrEnum):
    IDLE = "idle"  # not scheduled: before start, paused, or after a failure was handled
    COUNT_IN = "count_in"
    PLAYING = "playing"
    FAILED = "failed"
    FINISHED = "finished"


class FailReason(StrEnum):
    LATE_OR_MISSING = "late_or_missing"
    INTERRUPTED = "interrupted"
    TOO_SHORT = "too_short"
    REST_NOT_QUIET = "rest_not_quiet"


@dataclass
class _EventState:
    start: float
    end: float
    window: float  # onset window on each side (notes only)
    required_frames: int  # 80 percent of the interval
    target_hz: float | None
    confirm_frames: int
    credit_frames: int = 0
    onset: float | None = None
    run_start: float | None = None
    run_frames: int = 0
    run_pending: int = 0  # frames of the unconfirmed run inside the interval
    gap_frames: int = 0
    active_frames: int = 0  # rests: consecutive active frames


@dataclass(frozen=True)
class RhythmUpdate:
    status: RhythmStatus
    index: int  # current event
    progress: float  # credit of the current event as a fraction of its 80 percent requirement
    cents: float | None  # this frame's deviation from the current note, if pitched
    passed: tuple[int, ...] = ()  # events that passed with this frame
    failed: FailReason | None = None


@dataclass
class _Schedule:
    count_in_start: float
    beat: float
    first_start: float
    events: dict[int, _EventState] = field(default_factory=dict)


class RhythmEngine:
    def __init__(self, song: Song, tempo: float, tolerance_cents: float, hop_s: float, start_index: int = 0,
                 end_index: int | None = None):
        self.song = song
        self.end_index = len(song.events) if end_index is None else end_index  # exclusive
        self.tempo = tempo
        self.tolerance_cents = tolerance_cents
        self.hop_s = hop_s
        self.grace_frames = math.floor(config.GRACE_PERIOD_S / hop_s + 1e-6)
        self.position = start_index
        self.status = RhythmStatus.IDLE
        self.failure: FailReason | None = None
        self.completed: set[int] = set()
        self.failures: dict[int, int] = {}  # failed attempts per event
        self.schedule_data: _Schedule | None = None
        self._scheduled_from = start_index

    # Scheduling

    @property
    def finished(self) -> bool:
        return self.position >= self.end_index

    @property
    def event(self) -> Event:
        return self.song.events[self.position]

    def schedule(self, count_in_start: float) -> None:
        """Start a count-in at count_in_start, followed by the song from the current position."""
        beat = beat_seconds(self.song.time, self.tempo)
        first = count_in_start + config.COUNT_IN_BEATS * beat
        schedule = _Schedule(count_in_start, beat, first)
        self._scheduled_from = self.position
        origin = self.song.events[self.position].start
        for event in self.song.events[self.position:self.end_index]:
            start = first + seconds(event.start - origin, self.tempo)
            duration = seconds(event.duration, self.tempo)
            schedule.events[event.index] = _EventState(
                start=start,
                end=start + duration,
                window=min(config.ONSET_WINDOW_FRACTION * duration, config.ONSET_WINDOW_CAP_S),
                required_frames=max(1, frames_for(config.RHYTHM_THRESHOLD_FRACTION * duration, self.hop_s)),
                target_hz=event.pitch.frequency() if event.pitch else None,
                confirm_frames=max(1, min(frames_for(config.STABLE_CONFIRMATION_S, self.hop_s),
                                          frames_for(duration, self.hop_s))),
            )
        self.schedule_data = schedule
        self.status = RhythmStatus.COUNT_IN
        self.failure = None

    def stop(self) -> None:
        """Pause or a settings change: stop the beat; a new count-in is needed."""
        if self.status in (RhythmStatus.COUNT_IN, RhythmStatus.PLAYING, RhythmStatus.FAILED):
            self.status = RhythmStatus.IDLE
        self.schedule_data = None

    def restart(self, index: int = 0) -> None:
        self.stop()
        self.position = index
        self.completed = {i for i in self.completed if i < index}
        self.status = RhythmStatus.IDLE

    def beat_times(self) -> list[float]:
        """Count-in beats followed by the beats of the scheduled song."""
        schedule = self.schedule_data
        if schedule is None:
            return []
        last = schedule.events[self.end_index - 1].end
        count = math.ceil((last - schedule.count_in_start) / schedule.beat - 1e-9)
        return [schedule.count_in_start + i * schedule.beat for i in range(count)]

    def event_times(self, index: int) -> tuple[float, float] | None:
        if self.schedule_data is None or index not in self.schedule_data.events:
            return None
        state = self.schedule_data.events[index]
        return state.start, state.end

    def current_credit(self) -> tuple[float, float]:
        """Credited and required (80 percent) seconds of the current event."""
        if self.finished:
            return 0.0, 0.0
        if self.schedule_data is None:
            duration = seconds(self.event.duration, self.tempo)
            return 0.0, frames_for(config.RHYTHM_THRESHOLD_FRACTION * duration, self.hop_s) * self.hop_s
        state = self.schedule_data.events[self.position]
        return state.credit_frames * self.hop_s, state.required_frames * self.hop_s

    def beat_in_measure(self, beat_index: int) -> int:
        """Position within its measure (0 = downbeat) of a beat from beat_times().

        Count-in beats count from 0; song beats follow the song's measures.
        """
        if beat_index < config.COUNT_IN_BEATS:
            return beat_index % self.song.time.beats
        beat_length = self.song.time.beat_length
        quarters = self.song.events[self._scheduled_from].start + (beat_index - config.COUNT_IN_BEATS) * beat_length
        measure = next((m for m in reversed(self.song.measures) if m.start <= quarters), self.song.measures[0])
        offset = quarters - measure.start
        if measure.index == 0:  # a pickup measure ends on the last beats of a full measure
            offset += self.song.time.measure_length - measure.duration
        return int(offset / beat_length) % self.song.time.beats

    # Assessment

    def _accepted(self, frame: AnalysisFrame, state: _EventState) -> bool:
        cents = frame.cents_from(state.target_hz) if state.target_hz else None
        return cents is not None and abs(cents) <= self.tolerance_cents

    def _update(self, frame: AnalysisFrame | None, passed: tuple[int, ...] = ()) -> RhythmUpdate:
        progress, cents = 0.0, None
        if not self.finished and self.schedule_data is not None:
            state = self.schedule_data.events[self.position]
            progress = min(1.0, state.credit_frames / state.required_frames)
            if frame is not None and state.target_hz:
                cents = frame.cents_from(state.target_hz)
        failed = self.failure if self.status is RhythmStatus.FAILED else None
        return RhythmUpdate(self.status, self.position, progress, cents, passed, failed)

    def feed(self, frame: AnalysisFrame) -> RhythmUpdate:
        if self.status not in (RhythmStatus.COUNT_IN, RhythmStatus.PLAYING):
            return self._update(frame)
        schedule = self.schedule_data
        t = frame.time
        if self.status is RhythmStatus.COUNT_IN and t >= schedule.first_start:
            self.status = RhythmStatus.PLAYING

        passed: list[int] = []
        while not self.finished and t >= schedule.events[self.position].end:
            if not self._finalize(self.position):
                return self._update(frame, tuple(passed))
            passed.append(self.position)
            self.position += 1
        if self.finished:
            self.status = RhythmStatus.FINISHED
            return self._update(frame, tuple(passed))

        next_state = schedule.events.get(self.position + 1)
        next_is_note = next_state is not None and next_state.target_hz is not None
        next_accepts = next_is_note and t >= next_state.start - next_state.window \
            and self._accepted(frame, next_state)
        if not self._feed_event(self.position, frame, next_accepts):
            return self._update(frame, tuple(passed))
        if next_is_note:
            # Track the next note's runs from now on, so a sound that started
            # before its window (such as a held repeated note) is not an onset.
            self._feed_event(self.position + 1, frame, False)
        return self._update(frame, tuple(passed))

    def _fail(self, index: int, reason: FailReason) -> bool:
        self.status = RhythmStatus.FAILED
        self.failure = reason
        self.position = index
        self.failures[index] = self.failures.get(index, 0) + 1
        return False

    def _finalize(self, index: int) -> bool:
        state = self.schedule_data.events[index]
        if state.target_hz is None:
            if state.credit_frames < state.required_frames:
                return self._fail(index, FailReason.REST_NOT_QUIET)
        elif state.onset is None:
            return self._fail(index, FailReason.LATE_OR_MISSING)
        elif state.credit_frames < state.required_frames:
            return self._fail(index, FailReason.TOO_SHORT)
        self.completed.add(index)
        return True

    def _feed_event(self, index: int, frame: AnalysisFrame, next_note_accepts: bool) -> bool:
        """Apply a frame to one event. Returns False if the event failed."""
        state = self.schedule_data.events[index]
        t = frame.time
        inside = state.start <= t < state.end

        if state.target_hz is None:  # rest
            if not inside:
                return True
            if frame.frame_class is FrameClass.QUIET or next_note_accepts:
                state.credit_frames += 1
                state.active_frames = 0
            else:
                state.active_frames += 1
                if state.active_frames > self.grace_frames:
                    return self._fail(index, FailReason.REST_NOT_QUIET)
            return True

        # Before the onset window nothing can fail (warm-up); runs are tracked so that
        # only a sound that starts inside the window counts as an onset.
        if self._accepted(frame, state):
            state.gap_frames = 0
            if state.onset is not None:
                if inside:
                    state.credit_frames += 1
                return True
            if state.run_start is None:
                state.run_start, state.run_frames, state.run_pending = t, 0, 0
            state.run_frames += 1
            if inside:
                state.run_pending += 1
            in_window = state.start - state.window <= state.run_start <= state.start + state.window
            if in_window and state.run_frames >= state.confirm_frames:
                # Stable confirmation dates the onset back to the start of the run.
                state.onset = state.run_start
                state.credit_frames += state.run_pending
            elif not in_window and t > state.start + state.window:
                # A run that began before the window (such as a held repeated note) is not an onset.
                return self._fail(index, FailReason.LATE_OR_MISSING)
            return True

        state.run_start = None
        if state.onset is not None:
            if inside:
                state.gap_frames += 1
                if state.gap_frames > self.grace_frames and state.credit_frames < state.required_frames:
                    return self._fail(index, FailReason.INTERRUPTED)
        elif t > state.start + state.window:
            return self._fail(index, FailReason.LATE_OR_MISSING)
        return True
