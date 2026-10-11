# Manual checks

Checks that need a real microphone and a real whistle. Run them on the reference system (Ubuntu 24.04 with PipeWire) and record the results at the bottom.

## Milestone 2: audio setup and pitch

### Setup

1. Open **Audio setup**. The input list shows your microphones by name, with the system default marked. The **Listening** indicator appears.
2. Make a sound: the activity meter moves.
3. Press **Start setup**, stay quiet for 3 seconds, then whistle one steady note. Setup completes and shows the background level, whistle level, and threshold.
4. Press **Start setup** and stay silent through both steps: after 10 seconds, the "No steady whistle" message appears.
5. Press **Measure my range** and hold your lowest comfortable note for two seconds. A 3-second pause follows, showing the low note, before the high note is asked for; whistling during the pause is ignored. Then hold your highest comfortable note for two seconds. The range is shown.
6. Go **Back**: the Listening indicator disappears.

### Devices

7. Choose a different input: the meter follows the new input, and the choice is remembered after restarting the app.
8. Unplug the selected USB microphone while Audio setup is open: the "input stopped working" message appears and listening stops.
9. Plug it back in: it appears again but listening does not restart until you choose it or press Start setup.
10. Restart the app with the microphone unplugged and open Audio setup: it is shown as "(not connected)" and is not replaced by another input.

### Test input

11. Press **Test input** and whistle the target note. The detected note matches what you whistle, and the hold bar fills in about 1 second.
12. Whistle clearly too low and too high: the guidance says "Whistle higher" or "Whistle lower" and the hold bar does not fill.
13. Whistle the target an octave higher or lower: it never passes.
14. Break off briefly (a quick breath) while holding: the bar pauses ("Keep going"). Stop for longer: the bar resets.
15. Talk, clap, and hum near the microphone: no note passes.
16. Note how quickly the detected note and meter react. They should feel immediate, with a delay of no more than about 150 ms.

### Measurements to record

- Microphone(s) used, and their input volume in the system settings.
- Background, whistle level, and threshold shown after setup, in a quiet room and with background noise (a fan, or music at low volume).
- Measured comfortable range.
- Whether Easy (±40 cents) and Standard (±25 cents) feel fair.
- Notes that were hard to detect, or a detected note that jumped around.

## Milestone 3: guided practice

1. In the library, select a song, change its tempo and difficulty, and restart the app: the difficulty is remembered per song, and the tempo is back at the song's own tempo (60 for the exercise, 90 for Twinkle, 100 for Ode to Joy and Frère Jacques). The estimated length changes with the tempo. A changed tempo is kept when going from Listen to Practice and back to the library, until another song is selected.
2. Press **Start practice** without setting up the microphone: the page explains this and offers **Audio setup…**.
3. Practice the **Introductory exercise** at 60 bpm. The score scrolls smoothly and keeps the current note highlighted; completed notes get a check mark.
4. Whistle each note for its written length: whole notes need 4 seconds, half notes 2, quarter notes 1 at 60 bpm.
5. At a rest ("Take a breath"), stay quiet for its length; whistling during the rest does not let it pass.
6. At the repeated B5 notes, keep whistling: the second B5 does not pass until you stop briefly ("Stop briefly, then whistle this note again").
7. The tied A5 needs one continuous hold of both notes together.
8. Press **Pause** halfway through a note: listening stops and that note starts over on **Resume**.
9. Practice **Ode to Joy** and **Frère Jacques** to the end: the completion message shows practice time and retries.
10. Unplug the microphone during practice: practice pauses with an explanation and does not resume by itself.

## Milestone 4: rhythm mode

1. In the library, choose **Rhythm** for a song: the description changes and the **Metronome sound** option appears. Both choices are remembered.
2. Start the **Introductory exercise** in rhythm mode at 60 bpm without the metronome sound. The beat dots and "Get ready… 1, 2, 3, 4" count in, then the song follows the beat.
3. Whistle each note on the beat: the song continues without waiting, and completed notes get ✓.
4. Start a note clearly late (about half a beat): the song stops at that note, marks it ✗, and explains "did not start on the beat". **Retry** counts in again from that note, and earlier notes stay completed.
5. Whistle during a rest: the song stops with "The rest was not quiet".
6. Hold a repeated note through without a break: the second note fails as not started on the beat.
7. With headphones, enable **Metronome sound**: clicks are heard on every beat, higher on beat one, and they line up with the beat dots and with when the app expects each note. Note any delay you hear between the click and the dots.
8. Try the metronome sound through speakers: clicks leaking into the microphone should not fail notes or rests.
9. **Pause** during rhythm practice: the beat and clicks stop; **Resume** starts with a new count-in.
10. Try 30 bpm and 120 bpm on Frère Jacques (eighth notes): note whether the timing windows feel fair.

## Milestone 5: complete app

1. **Listen:** open **Listen…** for each song. **Play song** plays the melody with a whistle-like tone, and the highlight follows the notes. **Stop** keeps the highlight; **Play song** continues from there. Arrow keys and clicking notes play single notes; rests are silent.
2. Listen with a different tempo and transposition: playback and the score change, and practice uses the same settings.
3. **Transposition:** after measuring your range in Audio setup, the library suggests a transposition. **Use** applies it, and the range shown fits your range.
4. **Hear note** during guided practice: the note plays through the speakers, and the app does not count its own sound as your whistle. The note then starts over.
5. In rhythm mode, **Hear note** works only when paused or after a mistake.
6. **Sections:** pause, click a note, Shift+click a later note: the section is shaded, **Restart section** practices just that part, and finishing it shows "Section complete!".
7. While paused, change mode, tempo, difficulty, and transposition: practice resumes from the same note with the new settings.
8. **Summary:** after a song with some retries, the summary lists the hardest notes and offers to practice that measure again. **Repeat**, **Restart song**, and **Library** work.
9. **Progress:** practice part of a song, close the app, reopen it: the library shows the progress and offers **Continue from note n**. Finish the song: it shows ✓ Completed.
10. **Reset progress…** and **Reset all data…** ask for confirmation first and clear what they say.
11. Untick **Show note names**: the score hides them everywhere.
12. Press **Escape** on any page: you return to the library and the microphone stops.

## Results

| Date | Microphone | Room | Background / whistle / threshold (dB) | Range | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-10 | (not recorded) | | | | Easy ±40 and Standard ±25 cents feel fair. |
