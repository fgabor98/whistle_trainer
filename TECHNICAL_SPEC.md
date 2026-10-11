# Whistle Trainer Technical Specification

This document describes how Whistle Trainer is built. Product behavior, UI, assessment rules, and default values are defined in [PROJECT_SPEC.md](PROJECT_SPEC.md); when the two disagree, the product specification wins and this document must be corrected.

## Decisions

| Area | Decision |
| --- | --- |
| Language and UI | Python 3.12 with PySide6 (Qt 6). |
| Audio I/O | Qt Multimedia (`QAudioSource`, `QAudioSink`, `QMediaDevices`), which uses PipeWire/PulseAudio. PortAudio was dropped: the version in Ubuntu 24.04 only offers raw ALSA devices, not the PipeWire devices by name. |
| Signal processing | NumPy; pitch detection with the YIN algorithm. |
| Song format | MusicXML subset (single melodic line), parsed with the standard library. |
| Bundled songs | Public domain: Ode to Joy, Twinkle Twinkle Little Star, Frère Jacques, plus an introductory exercise. |
| Score rendering | Custom QPainter drawing with the Bravura SMuFL music font (SIL Open Font License). |
| Octave display | Written one octave below sounding pitch; note names show the sounding octave. |
| Listen tone | Synthesized whistle-like tone generated in the app. |
| Window layout | One window with switchable pages. |
| UI language | English only; all user-facing strings kept in one module. |
| Platform and install | Ubuntu 24.04 with PipeWire as the reference system; run from source via a setup script and desktop launcher. |
| Testing | pytest with synthetic audio for assessment rules, pytest-qt smoke tests, and a manual microphone checklist. |

## Project layout

```
whistle_trainer/
  __main__.py            Entry point: python -m whistle_trainer
  app.py                 QApplication, main window, page navigation, service wiring
  strings.py             All user-facing text
  config.py              Default values from the product spec, in one place
  music/
    model.py             Song, Event, Pitch, TimeSignature, KeySignature
    musicxml.py          MusicXML subset parser and validation
    library.py           Loading the bundled songs
    transpose.py         Transposition and enharmonic spelling
    timing.py            Beats to seconds, event schedule
  audio/
    devices.py           Input/output device listing and monitoring
    capture.py           Capture and analysis worker thread
    playback.py          Output stream, mixer, scheduled sounds
    synth.py             Whistle tone and metronome click synthesis
  pitch/
    yin.py               YIN pitch estimator
    bandpass.py          Streaming FIR band-pass filter
    analyzer.py          Framing, level, frame classification
    display.py           Smoothed "detected note" for the UI
    calibration.py       Audio setup measurements and thresholds
  assessment/
    frames.py            AnalysisFrame and frame classes
    hold.py              Hold tracking for one target note (shared by the engines)
    guided.py            Guided mode engine
    rhythm.py            Continuous rhythm mode engine
  storage/
    jsonfile.py          Atomic JSON writes and unreadable-file recovery
    settings.py          Settings persistence
    progress.py          Per-song, per-mode progress persistence
  ui/
    pages/               library.py, setup.py, test_input.py, listen.py, practice.py, summary.py
    score_layout.py      Horizontal layout of the staff in staff spaces (no Qt)
    score_view.py        Staff rendering, highlighting, scrolling, note selection
    guidance.py          Guidance text shared by Test input and Practice
    meters.py            Input level meter, pitch meter, hold indicator
    beat_indicator.py    Count-in and visual beats
  resources/
    songs/*.musicxml
    fonts/Bravura.otf, fonts/OFL.txt   Music font and its license
tests/
scripts/
  setup.sh               Creates .venv and installs dependencies
  install-desktop.sh     Installs a .desktop launcher for the current user
run.sh                   Starts the app from the project's .venv
requirements.txt         Pinned dependency versions
requirements-dev.txt     Adds test tools
pyproject.toml           Project metadata and pytest settings
```

## Architecture

The app has four layers, and dependencies only point downward:

1. **UI** (`ui/`, `app.py`): Qt widgets and pages. Holds no assessment logic.
2. **Session** (the practice page's session control, and the Listen player from milestone 5): starts and stops capture and playback, feeds frames to the engine for the chosen mode, schedules the count-in and metronome, and handles pause, retry, restart, and input loss. A separate session module was planned, but with two modes the page's session control stayed small enough to keep in one place.
3. **Engines** (`assessment/guided.py`, `assessment/rhythm.py`, `pitch/`, `music/`): pure Python with no Qt or audio-device dependencies. Fully testable with synthetic input.
4. **I/O** (`audio/`, `storage/`): devices and files.

### Threads

| Thread | Work |
| --- | --- |
| Capture worker (QThread) | Owns the `QAudioSource`, reads samples as they arrive (about every 20 ms), runs the analyzer, and emits each batch of frames to the main thread through a queued Qt signal. |
| Qt main thread | Feeds frame batches to the active engine, updates the UI, and owns the `QAudioSink` for playback. |

Engines run on the main thread. This does not affect accuracy: assessment depends only on frame timestamps from the capture clock, never on when a batch arrives, so a busy UI can delay feedback but cannot change a result. Analysis, the expensive part, stays on the worker.

### Clock

Assessment time is the capture clock: the number of samples received since capture started, divided by the sample rate. Each analysis frame's timestamp is the time of its window's center sample, corrected for the band-pass filter's delay. Rhythm schedules and visual beats are expressed on this clock. Qt Multimedia provides no hardware timestamps, so the capture clock is related to the system's monotonic clock: on each read, the capture worker computes `monotonic now − samples received / rate` and keeps the smallest value seen since capture started (samples only ever arrive late, so the smallest offset is the best estimate). Visual beats convert the monotonic time to the capture clock with this offset, and metronome clicks are scheduled at `beat time + offset` on the output (see Playback service). Engines never read the system clock themselves; they only use frame timestamps, which makes them deterministic in tests.

## Audio input and analysis

### Capture

- Mono, 48 kHz, float32, with a requested 20 ms buffer. If the device does not support this format, use its preferred format (8, 16, or 32-bit integer or float, any sample rate and channel count) and convert. Analysis parameters are defined in seconds and converted to samples.
- Multi-channel inputs are mixed to mono.
- Audio is held only in memory and discarded after analysis, as the product specification requires. Nothing is written to disk.

### Frames

- Analysis window 2048 samples (about 43 ms), hop 10 ms. Each hop produces one `AnalysisFrame`.
- Before YIN and level measurement, apply a band-pass filter of 400 Hz to 4.5 kHz to remove hum and hiss outside the whistle range: a linear-phase FIR filter of 1025 taps with a Hann window (about 10.7 ms delay), applied by FFT convolution. Mains hum (50 Hz) is attenuated by more than 80 dB; 500 Hz to 4.2 kHz passes unchanged.
- Expected total delay from sound to screen: about 11 ms filter delay + 21 ms window center offset + 10 ms hop + 20 ms capture buffer + up to 17 ms display refresh, about 80 ms, within the 150 ms visible feedback target. To be confirmed with a real microphone.

`AnalysisFrame` fields: `time`, `level_db` (RMS in dBFS), `f0_hz` (or none), `confidence` (0 to 1), `frame_class`.

### Pitch detection (YIN)

- Standard YIN with cumulative mean normalized difference, absolute threshold 0.15, and parabolic interpolation of the chosen lag.
- Search range 450 Hz to 4.2 kHz, covering the supported whistle range (about A4 to C8) with margin.
- `confidence = 1 - d'(τ)` at the chosen lag.
- Octave errors: YIN picks the first dip under the threshold, which avoids most octave-down errors. A whistle is close to a pure tone, so octave errors are rare; tests must cover them anyway.

### Frame classes

Each frame is classified using the calibrated activity threshold:

| Class | Condition |
| --- | --- |
| `QUIET` | `level_db` below the activity threshold. |
| `PITCHED` | Level at or above the threshold, a pitch in range, and `confidence ≥ 0.8`. |
| `UNCLEAR` | Level at or above the threshold but not `PITCHED`. |

Assessment uses only frame classes, pitch, and timestamps. Loudness never passes a note on its own.

### Detected note display

The "reliable detected note" shown in the UI is smoothed separately from assessment: the median pitch of the last 5 `PITCHED` frames, changing the displayed note only after the new note has been stable for 50 ms. When no frame has been `PITCHED` for 150 ms, show "No clear pitch". This smoothing never feeds assessment, so it cannot delay or alter scoring.

### Audio setup calibration

1. **Silence:** record 3 seconds while the user stays quiet. Noise floor = 95th percentile of frame levels.
2. **Steady whistle:** record until 1.5 seconds of `PITCHED`-quality frames are collected (provisional threshold: noise floor + 6 dB), up to 10 seconds. Whistle level = median level of those frames.
3. **Threshold:** activity threshold = midpoint in dB between noise floor and whistle level, and at least noise floor + 6 dB.
4. **Usability:** if the whistle is less than 12 dB above the noise floor, or no steady pitch is found, show the setup problem message from the product specification.
5. **Optional range:** the user whistles comfortable low and high notes; the median pitch of each is stored as the practice range and used to suggest a transposition in the library.

Calibration results are stored per input device id. Until an input is set up, an activity threshold of −50 dBFS is used.

### Devices

- List inputs and outputs from `QMediaDevices`. Devices are identified by their id, the PipeWire/PulseAudio node name (for example `alsa_input.usb-…`), which stays the same between sessions; the description is saved alongside it for display.
- A saved device that is missing is shown as "(not connected)" and stays selected; the app never switches to another device by itself.
- `QMediaDevices` reports connected and disconnected devices, and the lists update immediately. A reconnected device is not opened again until the user chooses it or starts setup.
- A source error, or the current input disappearing from the device list, is treated as input loss: capture stops and the input problem message is shown.

## Music model and songs

### Model

- `Pitch`: MIDI number for the sounding pitch, plus spelling (step, alter) for display.
- `Event`: a note or rest with its index, sounding pitch (notes only), total duration in quarter notes as a `Fraction`, and its notated parts. A tied chain is one `Event` whose notated parts are the individual written notes, so it is assessed as one hold but drawn as written.
- `Song`: id (file name without extension), title, key signature, time signature, default tempo, events, measures, sounding range, and length in beats.

### Timing

`seconds = quarter_notes × 60 / tempo`, with tempo in quarter-note beats per minute. Event start times are cumulative sums of durations. The time signature only affects display and the metronome accent.

### MusicXML subset

Supported:

- `score-partwise` with exactly one part and one voice.
- `work-title` or `movement-title` for the title.
- `divisions`, `key`, `time`, `clef` (treble only), `transpose` (`chromatic` and `octave-change`).
- `note` with `pitch` (step, alter, octave) or `rest`, `duration`, `type`, `dot`, `tie` (start/stop), and `measure` boundaries.
- `sound tempo` or `metronome` for the default tempo; 60 if missing.

Sounding pitch = written pitch + `chromatic` + 12 × `octave-change`. Bundled songs are written an octave below sounding pitch with `octave-change` 1, matching the score display decision. Files without a `transpose` element are interpreted the same way, so that songs exported from MuseScore with a plain treble instrument also display correctly.

Anything else that affects the melody (chords, multiple voices, staves or parts, grace notes, tuplets, microtones, repeats and jumps, key or time signature changes after the first measure) is rejected with a clear message naming the file and measure. Dynamics, lyrics, slurs, and layout elements are ignored. The parser validates that each measure's durations match the time signature. Only the first measure (a pickup) and the last measure may be shorter; no measure may be longer or empty. A whole-measure rest may omit its note type; for other notes without a type, the type is derived from the duration.

### Bundled arrangements

All in 4/4 and G major, sounding within D5 to E6, default tempo 60:

| Song | Sounding range | Notes |
| --- | --- | --- |
| Introductory exercise | G5 to B5 | Whole, half, and quarter notes; a tied note; a repeated note; a rest. |
| Twinkle Twinkle Little Star | G5 to E6 | Quarter and half notes. |
| Ode to Joy | D5 to D6 | Includes the dotted quarter and eighth. |
| Frère Jacques | D5 to E6 | Includes the eighth-note phrase. |

The shortest note is an eighth (0.5 seconds at 60 bpm), following the product specification's caution about very short notes.

### Transposition

- Range −12 to +12 semitones in half steps, default 0.
- Transposing shifts every sounding pitch and the key signature. The new key is the one with the fewest accidentals for the transposed tonic (for example F♯ major rather than G♭ major, F major rather than E♯ major), and notes are spelled in that key.
- The library suggests the transposition that best centers the song's range inside the user's measured practice range, if one was measured. It is shown as a suggestion only.

## Assessment engines

Both engines are state machines fed one frame at a time:

```python
class GuidedEngine:
    def start(self, event_index: int) -> None: ...      # make an event current
    def feed(self, frame: AnalysisFrame) -> GuidedUpdate: ...
    def reset_current(self) -> None: ...                # pause, reference playback, settings change
```

`GuidedUpdate` reports the assessed event, hold status and progress, pitch deviation in cents, whether a repeated note is waiting for a release, whether a retry was counted, and whether the song is finished. The engine keeps completed events and retries per event. The rhythm engine follows the same pattern and adds event failures with a reason.

Hold timing lives in `HoldTracker` (`assessment/hold.py`), shared by notes, rests, and the Test input page. It counts credit in whole frames so long holds do not drift.

All thresholds come from `config.py`, using the product specification's defaults: pitch tolerance (Easy ±40 cents, Standard ±25 cents), stable pitch confirmation 100 ms, grace period 100 ms, repeated-note release 100 ms, onset window 20 percent of duration capped at 150 ms, hold and rest threshold 80 percent.

### Shared definitions

- **Accepted frame:** `PITCHED`, and within the tolerance of the target's sounding pitch: `|1200 × log2(f0 / f_target)| ≤ tolerance`. An octave error is about 1200 cents off, so it can never be accepted.
- **Stable confirmation:** an uninterrupted run of accepted frames lasting the confirmation time (capped at the event's duration). When confirmation completes, credit for the whole run, including the confirmation time, is added at once.
- **Interruption:** any non-accepted frame after confirmation. Credit does not grow during an interruption. If it lasts longer than the grace period, it becomes a failure (rhythm) or reset (guided).
- **Attack:** the start of an accepted run that began after a release. A **release** is at least 100 ms in which no frame is `PITCHED` or `UNCLEAR`. Each note event needs its own attack if it has the same pitch as the previous note; the previous note's run cannot carry over. When the pitch changes, a new accepted run counts as an attack without a release.
- **Quiet frame (rests):** `QUIET`. Any `PITCHED` or `UNCLEAR` frame interrupts rest credit.

### Guided engine

Per note event:

1. **Waiting:** no penalty for silence, unclear input, or wrong pitches before a confirmed attempt. Pitch guidance ("Whistle higher/lower") is shown for `PITCHED` frames.
2. **Confirming:** accepted frames accumulate; a non-accepted frame before confirmation returns to Waiting without counting a retry.
3. **Holding:** credit grows with each accepted frame's hop time. Credit reaching the required duration passes the event immediately.
4. **Interrupted:** credit is frozen. Recovery within the grace period continues Holding. Exceeding the grace period resets credit, counts one retry, and returns to Waiting; the next accepted frame starts a new attempt.

A note with the same pitch as the previous note (including after a tied chain) first waits for a release: 100 ms of `QUIET` frames after it becomes current. Until then accepted frames are ignored and the guidance says "Stop briefly, then whistle this note again". Notes of a different pitch need no release, so moving between notes without a break is fine.

Rest events use the same structure with quiet frames instead of accepted frames, no confirmation step, and no retries counted for silence that has not started. A retry is counted when started rest credit is reset by input longer than the grace period. The guidance for rests is always "Take a breath".

### Rhythm engine

On start, the engine builds a schedule: four count-in beats, then each event `i` with start `s_i` and end `e_i`, from the selected position onward.

Per note event:

- **Onset window:** `w = min(0.2 × duration, 150 ms)`. Input before `s_0 − w` is ignored (warm-up).
- **Onset:** the start time of the first accepted run that completes stable confirmation (back-dated to the run's first frame). The event fails as "late or missing start" if no onset falls inside `[s_i − w, s_i + w]`, as soon as `s_i + w` passes without one. Runs for the next note are tracked from the moment the current note begins, so a sound that started before the window, such as a held repeated note, is never mistaken for an onset.
- **Credit:** only accepted time inside `[s_i, e_i]` counts. Early pitch establishes the onset but earns no credit.
- **Interruption failure:** after the onset and until credit reaches 80 percent of the duration, an interruption longer than the grace period fails the event as "note interrupted". After reaching 80 percent, the user may release early without penalty, which also leaves time for the release before a repeated note.
- **Result:** at `e_i`, the event passes if credit is at least 80 percent of the duration; otherwise it fails as "note too short". Passing never happens before `e_i`.

Rest events pass at `e_i` if quiet credit inside the interval is at least 80 percent and no active or unclear stretch exceeded the grace period; otherwise they fail as "rest not quiet". Frames inside the next note's early onset window that match the next note's pitch count as quiet. Without this, starting the next note early, which its onset window allows, would fail the rest before it.

Failure reasons and their messages: "late or missing start", "note interrupted" (a break longer than the grace period before 80 percent, which includes stopping too early), "note too short" (less than 80 percent without one long break, for example many short breaks or wavering pitch), and "rest not quiet".

On failure, the engine stops, the beat and clicks stop, the failed event is marked with ✗, and the page shows the reason with Retry. Capture keeps running. Retry rebuilds the schedule from the failed event with a new count-in. Failures are counted per event, as retries.

The count-in starts `COUNT_IN_LEAD_S` (0.5 s) after the latest frame received when listening starts, after Resume, or after Retry. This leaves time to schedule the first clicks ahead of the output buffer. Pausing stops the beat; resuming always uses a new count-in.

### Reference playback and self-hearing protection

Hear target note plays a 1-second whistle tone of the current note. While capture is running, frames up to 300 ms after the tone ends (on the capture clock) are discarded, the detected-note display is cleared, and unfinished progress is reset when the tone starts, so the app's own sound can never complete a note. In guided mode it is available at any time during practice. In rhythm mode it is only available while stopped (paused, or after a failure), and the next count-in waits for Retry. The metronome is excluded from this protection.

The metronome click is short (20 ms) and broadband, so it is classified as `UNCLEAR` or `QUIET` rather than accepted; the product specification recommends headphones for it. This is covered by a test with the click mixed into a synthetic whistle.

## Sound output

### Whistle synthesis

Each note is rendered on demand at 48 kHz:

- Sine at the sounding frequency, plus a second harmonic at −30 dB.
- Vibrato: 5 Hz, ±8 cents, fading in after 200 ms.
- Envelope: 15 ms attack, 40 ms release; tied notes are one sound.
- Breath noise at −35 dB, kept in a narrow band around the fundamental: white noise smoothed to a few hundred hertz of bandwidth, then ring-modulated by the tone. Seeded per note, so a note sounds the same each time.
- Output at a fixed level of −12 dBFS peak.

The metronome click is a 20 ms decaying burst at 2 kHz for beat one and 1.5 kHz for other beats.

### Playback service

A single `QAudioSink` on the selected output device (default: system default) in push mode, with a requested 40 ms buffer. A 5 ms timer keeps the buffer full, writing silence when nothing is scheduled, so the output position advances steadily. A sound scheduled for monotonic time `T` is placed at output sample `processed + (T − now) × rate`, where `processed` comes from `processedUSecs()`; a sound that is already too late plays as soon as possible. Overlapping sounds are mixed and clipped to ±1. The output is opened only when needed: for the metronome in rhythm mode, for Hear target note, and in Listen mode. It is closed when practice stops, pauses, or finishes, and when leaving the Listen page. Measured on the reference system, the written position stays 20 to 40 ms ahead of what has been played.

### Listen mode player

- **Play song:** plans all events from the current position at the selected tempo and transposition, starting 150 ms after the click. Notes are rendered and scheduled up to 1 second ahead of time, so playback starts immediately even for long songs. A 20 ms timer moves the highlight to each event at its planned start. Stop clears the scheduled notes and keeps the position on the last played event; Play resumes from there, or from the beginning after the end was reached.
- **Tempo and transposition** can be changed on the page; they are the song's saved preferences, shared with practice.
- **Next/Previous note and clicking a note:** stop any current playback, move the position, and play that single event; rests are highlighted silently.
- Input capture is never started in Listen mode, and no progress is changed.
- **Practice from here** starts practice at the highlighted note.

## User interface

### Pages

A single `QMainWindow` with a `QStackedWidget`:

| Page | Notes |
| --- | --- |
| Library | Song list with length, range, and progress in the selected mode ("—", "12 of 42 notes", "✓ Completed", "✓ Completed 3×"); Show note names; Reset all data (with confirmation). Preparation panel: mode (Guided or Rhythm, with a one-line description), metronome sound option (rhythm mode, saved globally), tempo, difficulty, transposition with the transposed range and, if a range was measured, a suggestion with Use; estimated length; Start practice; Continue from note n (when saved progress has an unfinished note); Listen; Reset progress (with confirmation); Audio setup. The introductory exercise is listed first. |
| Audio setup | Input and output selectors, live level meter, detected note, step-by-step calibration with status text, Measure my range, and Test input. |
| Test input | Whistle one selectable target note (C5 to C7, default the middle of the measured range, else B5) with the detected note, pitch meter, hold indicator for a 1-second hold, guidance text, and Try again. Uses the guided-mode hold rules. |
| Listen | Score view (clickable), the highlighted note with its length in beats, Previous note, Play song/Stop, Next note, Practice from here, tempo, and transposition. |
| Practice | Song title as page title, "Note n of m", score view, target note and octave (or "Rest"), detected note, pitch meter, hold indicator ("Hold" or "Quiet"; in rhythm mode against the 80 percent requirement), guidance ("Get ready… n" during the count-in, "Whistle G5 now" in rhythm mode), beat indicator (rhythm), and controls: Pause/Resume and Restart song; Retry after a rhythm failure; Audio setup when the input is missing or lost; Hear note; Restart section when a section is chosen. While paused, a panel offers mode, tempo, difficulty, and transposition, and the score becomes clickable: click sets the start, Shift+click sets the end of a section (shaded on the score), and Clear section returns to the whole song. Changes keep the current position and discard unfinished progress. Listening starts when practice is started; returning to the page (for example from Audio setup) stays paused until Resume. Finishing opens the summary. |
| Summary | "Song complete!" or "Section complete!", a note when every note of the song is now completed in the mode, mode, what was practiced (whole song, "Measure 5", "Measures 3–4", or "From measure 5 to the end"), active practice time, retries, the three notes with the most retries, and buttons: Practice measure n again (the measure with the most retries, if any), Repeat (same section or song), Restart song (whole song), and Library. Back returns to the library. |

A header bar shows the page title, a Back button, and the listening indicator whenever capture is active.

### Score view

- Custom `QWidget` drawn with `QPainter`. The melody is laid out as one continuous staff line that scrolls horizontally; the current event is kept about one third from the left, with smooth animated scrolling.
- Glyphs come from the Bravura font (SMuFL code points): clef, key and time signatures, note heads, stems, flags, dots, ties, rests, accidentals, and ledger lines. A pair of undotted eighth notes that fills one beat is beamed: both stems take the direction of their average position, and the beam's slope is limited to one staff space.
- Accidentals follow the key signature and are remembered until the end of the measure; tied continuations do not repeat them.
- The staff spacing scales with the widget height (7 to 16 pixels per staff space), and the content is centered vertically.
- Note spacing is proportional to duration with a minimum width so note names fit.
- Note names are drawn below each note with the sounding octave (for example "B5") and can be hidden in settings.
- States are shown with color and shape: current event (highlight band, highlight color, bold note name), completed (dimmed, with a check mark above), failed (cross, rhythm mode), upcoming (normal). Colors come from the Qt palette so light and dark system themes both work.
- Clicking or tapping a note selects it (Listen, and Practice while paused); the view reports the event under the pointer and whether Shift was held.
- A chosen section is shown as a lightly shaded band with a line at each end.

### Practice widgets

- **Pitch meter:** horizontal scale of ±100 cents around the target, with the tolerance band shaded and a marker for the current pitch; arrow and text "Whistle higher" or "Whistle lower" outside the band.
- **Hold indicator:** progress bar filling with credited time; frozen during grace interruptions, with the text "Keep going" while frozen.
- **Beat indicator:** one dot per beat of the measure; the current beat is filled and enlarged, refreshed every 20 ms from the capture clock. The count-in beat number is shown in the guidance ("Get ready… 3"). The dots go blank when the beat stops.

### Keyboard shortcuts

Space: Play/Stop in Listen, Pause/Resume in Practice. Left and Right arrows: Previous and Next note in Listen. H: Hear target note. R: Retry (rhythm mode). Escape: back to the library from any page.

## Persistence

Files are stored using XDG directories through `platformdirs`:

- `~/.config/whistle-trainer/settings.json`: devices, calibration per input, notation preference, last used mode, difficulty, tempo, and transposition per song.
- `~/.local/share/whistle-trainer/progress.json`: per song id and mode: completed event indices, next unfinished event index, retry counts per event, active practice time, and completion records with dates.

Progress is updated after every batch of frames and saved on pause, input loss, leaving the practice page, finishing, and closing the app:

- Completed events accumulate across sessions; section practice only adds the events actually completed.
- The next unfinished event is the current position when practice stops; after reaching the end of the song it returns to the beginning, and after a section it is the note after the section. The library offers "Continue from note n" when it is past the first note.
- Retries (guided retries and rhythm failures) and active practice time are added as they happen.
- A completion record (the date) is added when practice reaches the end of the song and every event has been completed in that mode.
- Progress is kept per mode; switching modes while paused keeps the position but does not mark anything as practiced in the other mode.
- Reset progress removes one song's progress in both modes; Reset all data deletes both files after confirmation.

Both files include a `schema_version`. Writes are atomic (write to a temporary file, then rename). A corrupt file is renamed with a `.corrupt` suffix and replaced by defaults, with a message to the user. If a song file changes so that its event count differs from saved progress, that song's progress is reset with a message.

## Testing

### Automated (pytest)

- **YIN:** pure and noisy sines across the whistle range are detected within 5 cents; noise alone gives low confidence; a sine with a strong second harmonic is not reported an octave high.
- **Frame classification and calibration:** synthetic noise floors and whistle levels produce the expected thresholds and usability results.
- **Engines:** frame sequences built by a test helper (for example "accepted 1000 ms at B5, quiet 80 ms, accepted 500 ms") are fed with timestamps. Every row of the product specification's acceptance table has at least one test: hold durations with confirmation, 80 ms dropout freeze, resets beyond the grace period, octave errors, repeated notes, ties, guided and rhythm rests, rhythm onset at ±150 ms and 250 ms late, 900 ms vs. 700 ms credit, no early advance at 800 ms, and retry after failure.
- **Audio pipeline:** synthesized whistle audio (including vibrato, dropouts, and background noise) runs through the full analyzer and engine to confirm the same results as the frame-level tests.
- **Self-hearing:** the playback synth's output fed back as input never passes a note.
- **Music:** MusicXML parsing of all bundled songs, rejection of unsupported features, tie merging, transposition and spelling, schedule timing.
- **Persistence:** round trip, atomic write, corrupt-file recovery, schema version.
- **UI smoke (pytest-qt):** each page opens, navigation works, Listen mode drives the highlight with a fake playback clock.

### Manual checklist

Kept in `tests/MANUAL_CHECKS.md`: setup with a built-in and a USB microphone, quiet room and background noise (fan, music at low volume), reference playback through speakers, unplugging the input during practice, full run of each song in both modes. Record microphones, settings, measured whistle ranges, and limitations, as the product specification requires.

## Installation and running

- System packages on Ubuntu 24.04: `python3-venv`, `libpulse0` (audio through PipeWire's PulseAudio interface), `libxcb-cursor0` (needed by Qt 6 on X11).
- `scripts/setup.sh` checks for these, creates `.venv`, and installs pinned versions from `requirements.txt` (PySide6-Essentials, PySide6-Addons for Qt Multimedia, numpy, platformdirs). `scripts/setup.sh --dev` installs `requirements-dev.txt`, which adds pytest and pytest-qt.
- `./run.sh` starts the app; `scripts/install-desktop.sh` adds a launcher to the application menu.
- The app works offline; there is no network access at runtime.

## Implementation milestones

These follow the product specification's delivery order:

1. **Foundation:** project skeleton, config, music model, MusicXML parser, bundled songs, persistence.
2. **Pitch prototype:** capture, YIN, frame classification, calibration page, single-note practice with pitch meter. Validate whistle range, responsiveness, and tolerances with a real microphone; update defaults in both specifications if needed.
3. **Guided mode:** guided engine with durations, interruptions, repeated notes, ties, and rests; practice page.
4. **Rhythm mode:** schedule, count-in, metronome, rhythm engine, Retry.
5. **Complete app:** full score view, library, transposition, Listen mode, summaries, progress.
6. **Release:** setup scripts, desktop launcher, manual checklist on the reference system.

## Remaining validation

These need measurements during milestone 2 rather than decisions now:

- Comfortable whistle range of real users and whether D5 to E6 suits most people.
- Whether the YIN confidence threshold of 0.8 and the activity threshold formula work with typical microphones and noise.
- Real input-to-display latency on the reference system.
- Minimum practical note duration for reliable acceptance.
