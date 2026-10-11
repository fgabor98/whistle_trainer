# Whistle Trainer Product Specification Draft

Whistle Trainer teaches users to whistle simplified melodies from familiar songs. It displays a score, listens through a selected audio input, and advances when the user produces the correct pitch for the required duration.

This draft builds on [initial_instructions.md](initial_instructions.md). It specifies product behavior and UI; implementation language and architecture remain open.

## Confirmed requirements and proposed scope

Confirmed requirements:

- Linux is the first supported platform.
- Music uses traditional staff notation with note names shown.
- Users can select a PC audio input; the app detects the whistle's dominant pitch.
- Both pitch and duration determine progress. Incorrect notes cannot be skipped automatically.
- Both guided practice and continuous rhythm practice are available.
- A listen mode plays the loaded song from the computer so users can hear how each note sounds, either the whole song with one click or one note at a time.

Everything else below is proposed for review. Numeric defaults need validation with real whistles and supported devices.

The first version is a local, single-user app that works offline after installation, requires no account or development tools, and saves settings and progress. It includes three short, recognizable melody arrangements and an introductory exercise. Each arrangement has one melodic line suitable for whistling.

Accompaniment, lyrics, harmony, automatic transcription from audio or PDF, and a song editor are outside the scope. Users can add their own songs by importing a MusicXML score, from which the app extracts a whistle melody (see Adding your own songs). Audio inputs are those available through the supported OS; capturing arbitrary applications is not assumed.

## Setup and practice flow

1. **Set up audio:** Select an input, check its activity meter, then stay quiet and whistle a steady note to establish useful input levels. Optionally try comfortable low and high notes to suggest a practice range: each note is held for a few seconds, with a short pause after the low note before the high note is measured. If input is unusable, suggest checking the device, distance, or volume.
2. **Choose a song:** Review its length, pitch range, and saved progress. Select mode, tempo, difficulty, and transposition; optionally open Listen mode to hear the melody. Duration estimates use the selected tempo and exclude waiting and retries.
3. **Practice:** Follow the highlighted note, pitch guidance, and hold indicator. Guided mode waits for each attempt. Rhythm mode starts with a count-in and follows the beat until a mistake requires a retry.
4. **Finish or return later:** Stop listening, show a summary, and offer Repeat, Restart, or Library. Reopening the app offers saved progress with capture off until practice starts.

## Screens and controls

| Screen | Main content and actions |
| --- | --- |
| Song library and preparation | Song title, length, range, progress, introductory exercise, mode, tempo, difficulty, transposition, preview, Start, Audio setup, Add song, and Remove song for added songs. |
| Add song | Chosen file, title, the melody line used and the others available, what was simplified, Play preview, and Add. |
| Audio setup | Input selector, activity meter, reliable detected note, setup status, Test input, and Repeat setup. Identify unavailable devices without silently switching inputs. Test input offers a chosen target note, or random target notes that change to a new one each time the current one is hit. |
| Listen | Score with the playing note highlighted, Play song, Stop, Previous note, Next note, tempo, transposition, sound (Whistle or Piano), and Practice. Capture is off. |
| Practice | Score with current and upcoming notes, target name and octave, reliable detected note, pitch direction, hold progress, selected input, and listening status. Rhythm mode adds visual beats and a count-in. |
| Summary | Mode, completed song or section, active practice time, notes needing the most retries, and replay options. |

The score is the main visual element. Scroll smoothly as needed, keeping the current note prominent. Use plain instructions such as “Whistle higher,” “Hold this note,” and “Take a breath.” Unreliable input shows “No clear pitch.” Use text and symbols alongside color.

Practice controls include Pause or Resume, Hear target note, Restart section or song, and Library. While paused, users can select a section or starting note and change mode, tempo, difficulty, or transposition. A section is chosen on the score while paused: clicking a note sets where practice starts, and Shift+clicking a note sets where the section ends. The section is shaded on the score until it is cleared. The summary offers to practice again the measure that needed the most retries, which selects it as a section.

An optional audible metronome is intended for headphone use; visual beats alone must support rhythm practice. Neither mode plays melody accompaniment during assessment.

In guided mode, a retry is a failed attempt after accepted pitch starts a hold; silence before starting is not a retry. In rhythm mode, each failed event counts once, including missed notes and failed rests. The summary can suggest replaying the section with the most retries.

## Assessment rules

### Pitch and articulation

Each target includes its octave. Wrong pitches, including octave errors, cannot pass; silence, weak input, and unreliable pitch earn no hold credit. Loudness alone never passes a note. Feedback should tolerate small fluctuations without flickering or advancing accidentally.

Transposition moves the entire melody while preserving intervals and updates the score, target pitches, and preview together.

Separate repeated notes require a brief release and a fresh whistle attack. Tied notes form one continuous hold with their combined duration. Moving to a different pitch does not require silence. One attack cannot satisfy two separately written notes, even when timing windows overlap.

### Guided mode

Tempo determines the required hold: at 60 beats per minute, a quarter note requires one second and an eighth note half a second. Dotted notes and ties use their total written duration.

Users start whenever ready, without a countdown or late-start penalty. Hold progress begins after stable pitch confirmation, with that confirmation time included. Only accepted pitch time counts. Success advances immediately; holding longer never reverses it.

An interruption within the grace period freezes progress without adding credit. A longer interruption resets the current hold while preserving completed notes. Separate short attempts cannot accumulate into a successful long hold.

Rests display “Take a breath” and require quiet input for their written duration. Quiet means below the calibrated activity threshold; a clear pitch anywhere in the supported whistle range, or strong or unclear activity, earns no rest credit. Brief interruptions freeze rest progress; longer ones reset it. Ordinary background noise below the threshold should not block rests. Unwritten silence between notes is allowed and does not advance the score.

### Continuous rhythm mode

After a four-beat count-in, events follow the chosen tempo. Assess the first onset within its allowed early-start window without penalizing earlier warm-up input.

Each note must start within the onset window and contain accepted pitch for at least 80 percent of its scheduled interval. Early pitch can establish an onset but earns no hold credit before that interval. Stable pitch confirmation dates the onset back to its actual start, avoiding an artificial late penalty.

Short dropouts receive the same grace period as guided mode and earn no credit. A longer interruption fails the event even if total accepted time would be sufficient. Meeting the hold threshold early does not advance early: successful events complete at their scheduled boundary.

Rests require quiet input for at least 80 percent of their scheduled interval, without any active or unclear interruption longer than the grace period. They have no onset requirement. Starting the next note early, within its onset window, does not fail the rest before it. Repeated-note articulation and ties follow the shared rules above.

A missing or wrongly timed onset, insufficient hold, excessive interruption, or failed rest stops the beat at the failed event. Preserve prior successes, explain the problem, and offer Retry with a fresh count-in. Tempo does not adjust automatically. A mode that runs through mistakes and grades the entire performance is outside this version.

### Reference playback

Hear target note plays a short reference, in the sound chosen on the Listen page, while assessment is suspended, followed by a settling period. This prevents the app's own output from completing a note. Return to the same target with unfinished hold progress reset. In rhythm mode, wait for Retry and a new count-in.

Full melody preview is available before practice or while paused through Listen mode.

### Listen mode

Listen mode plays the loaded song from the computer so users can learn how it should sound before whistling it. It never captures or assesses audio, and records no practice progress or retries. Playback uses the selected tempo and transposition at a comfortable fixed volume, in one of two sounds: a recorded classical grand piano (the default), or a clear, whistle-like tone. The choice is remembered and also used by Hear target note.

- **Play song:** One click plays the whole melody from the selected note to the end, observing written durations, ties, and rests. The score highlights and scrolls to each note as it sounds. Stop halts playback and keeps the highlight on the last played note; playing again resumes from there, or from the start after the song has finished.
- **Note by note:** Next note and Previous note move the highlight and play that single note for its written duration at the selected tempo; tied notes play as one sound. Selecting a note on the score plays it and makes it the current position. Rests are highlighted silently with “Rest” and its duration shown.

The target note name and octave are shown for the highlighted note. Starting playback in either way stops any playback already in progress. Practice switches to the chosen practice mode at the highlighted note, with capture off until the user starts.

## Adding your own songs

Users can add a song they have a score of, for example a piano arrangement exported from MuseScore or converted from a PDF by a recognition tool. Converting PDFs is not part of the app. **Add song** in the library opens a MusicXML file (`.musicxml`, `.xml`, or compressed `.mxl`) and turns it into a single whistle melody:

- **Melody line:** if the score has a separate vocal or melody part or staff, that is used; otherwise the top notes of the upper (right-hand) staff. Where several notes start together, the highest one is the melody, and accompaniment notes under a held melody note are left out. The dialog lists the other staves, so a wrong guess can be corrected and previewed.
- **Simplified away:** accompaniment, chords, inner voices, grace notes, ornaments, dynamics, and lyrics. Repeats, first and second endings, and jumps such as D.C., D.S., To Coda, and Fine are written out in full, so the song plays straight through.
- **Kept:** pitches, rhythms including triplets, ties, rests, key and time signature changes, pickup measures, and the tempo marking.
- **Range:** the melody is moved by whole octaves to sit as close as possible to the comfortable whistle range (D5 to E6); the transposition setting and the measured range can then fine-tune it.
- **Rounding:** rhythms the app cannot show, such as quintuplets, are rounded to the nearest sixteenth-note triplet and reported.

The dialog shows the title (editable), the melody line used with its note count and range, and a short report of what was simplified. **Play preview** plays the beginning of the melody, and **Add** saves it. Added songs are stored only on the user's computer, appear in the library like the bundled songs, and can be removed again (with confirmation); removing a song also removes its progress. A file the app cannot use at all, for example one without any notes, is reported with the reason.

## Proposed defaults

| Setting | Starting value |
| --- | --- |
| Mode and difficulty | Guided, Easy. |
| Tempo | Each song's own tempo; adjustable from 30 to 120. Opening a song in Listen or Practice always starts at its own tempo; a changed tempo lasts only while that song stays selected. |
| Pitch tolerance | Easy: ±40 cents; Standard: ±25 cents. A semitone is 100 cents. Confirmed as fair with a real whistle (October 2026). |
| Stable pitch confirmation | 100 milliseconds, counted toward the hold. |
| Interruption grace period | 100 milliseconds; progress freezes during the interruption. |
| Repeated-note release | At least 100 milliseconds without active whistle input. |
| Rhythm count-in | Four beats at the selected tempo. |
| Rhythm onset window | 20 percent of note duration before or after its start, capped at 150 milliseconds each way. |
| Rhythm hold and rest threshold | 80 percent of the scheduled duration. |
| Visible pitch feedback | Aim for a delay of no more than 150 milliseconds on supported setups. |
| Note names | Shown, with an option to hide them. |

For example, the rhythm onset window is ±150 milliseconds for a one-second note and ±100 milliseconds for a half-second note. Cap pitch confirmation at the required note duration if shorter than 100 milliseconds. Avoid very short notes in introductory arrangements until responsiveness and reliable acceptance are validated.

## Pause, recovery, and saved data

Pausing stops capture, preserves completed notes, and resets the unfinished event. Returning to the library or finishing a section also stops capture; leaving or closing the app saves progress.

Input disconnection or denied permission pauses practice, explains the problem, and offers setup. Never switch inputs or resume listening automatically. Resuming after a pause, input recovery, reference playback, or setting change requires a fresh count-in in rhythm mode.

Changes to mode, tempo, difficulty, or transposition preserve the selected position and reset unfinished progress. Update score pitches and durations before resuming.

Save input and setup settings, notation preference, mode, difficulty, transposition, and progress per song and mode. Tempo is not saved. Track completed events and the next unfinished event. Switching modes can carry the selected position over, but does not mark earlier events as practiced in the new mode or compare retry counts between modes.

Mark a whole song complete only when every event has been completed in that mode. Section practice never marks unplayed events complete. Save completion records and offer a reset for individual songs.

Process audio locally and discard it after analysis; do not record or transmit microphone audio. Show a listening indicator whenever capture is active. Clearing all settings and progress requires confirmation.

## Acceptance checks

Verify these behaviors with controlled audio and an actual microphone and whistle:

| Area | Expected behavior |
| --- | --- |
| Guided pitch and hold | A correct one-second target passes after one second of credited pitch, including confirmation. Wrong pitch, octave errors, weak or unclear input, and short attempts do not pass. Silence before starting causes no penalty. |
| Interruptions | An 80-millisecond dropout freezes progress and earns no credit. An interruption beyond the grace period resets a guided attempt or fails a rhythm event. |
| Articulation and ties | A continuous whistle cannot clear separate repeated notes. Two tied half-second notes accept one continuous one-second hold in guided mode. |
| Rests | A guided one-second rest requires one second of credited quiet. Active whistle input cannot pass a rest; rhythm rests obey their scheduled threshold and grace period. |
| Rhythm success | After the count-in, an on-time one-second note with 900 milliseconds of accepted pitch passes at its scheduled end. Reaching 800 milliseconds never advances it early. |
| Rhythm failure and retry | A one-second note started 250 milliseconds late, a missed onset, or only 700 milliseconds of accepted pitch fails. Stop at that event; Retry starts a new count-in without losing earlier successes. |
| Recovery and persistence | Pause stops capture and resets only the unfinished event. Input loss gives a useful message; reconnection never resumes automatically. Relaunch restores settings and position with capture off. Rhythm resumption uses a count-in. |
| Playback and transposition | Reference playback cannot pass a note through speakers. Transposition changes score, target, and preview together. |
| Listen mode | Play song plays every note and rest in order at the selected tempo and transposition with the score highlight in sync. Next and Previous note play exactly one note each. Capture stays off and no progress changes. |
| Completion | Finishing stops capture and offers Repeat. Section completion never marks unplayed parts of a song complete. |

Include quiet-room and representative background-noise checks on supported Linux setups. Record tested microphones, input settings, pitch ranges, and limitations.

## Open decisions and delivery

Initial songs, the supported Linux setup, screen layout, and technology are decided in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md). Review the proposed rhythm retry rules and defaults. Validate comfortable whistle range, useful input levels, and minimum practical note duration.

Suggested delivery order:

1. Review songs, Linux support, timing rules, and screen sketches.
2. Prototype one target note with live guidance; validate range, responsiveness, and pitch tolerance.
3. Add guided durations, interruptions, repeated notes, ties, and rests.
4. Add rhythm mode, count-in, and retry behavior.
5. Complete score display, library, transposition, Listen mode, persistence, and summaries.
6. Package for Linux and verify installation, first launch, recovery, and song practice.
