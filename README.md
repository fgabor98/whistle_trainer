# Whistle Trainer

Whistle Trainer helps you learn to whistle melodies from simplified sheet music. It listens through your microphone and lets you move on only when you whistle the right note for the right length.

## Requirements

- Linux (tested on Ubuntu 24.04 with PipeWire)
- Python 3.12 or newer
- These system packages:

```bash
sudo apt install python3-venv libpulse0 libxcb-cursor0
```

## Installation

From the project folder:

```bash
scripts/setup.sh
```

This creates a private Python environment in `.venv` and installs the app's dependencies. Nothing is installed system-wide.

## Starting the app

```bash
./run.sh
```

## Using Whistle Trainer

### 1. Set up your microphone

Press **Audio setup…** in the library.

1. Choose your microphone under **Input**. The app lists your PipeWire/PulseAudio devices by name and marks the system default. The **Activity** meter shows that sound is coming in. Choose where the app's sounds play under **Output**.
2. Press **Start setup**. Stay quiet for about 3 seconds while the background is measured, then whistle one steady, comfortable note until setup completes. The app shows the measured levels and saves them for this microphone.
3. Optionally press **Measure my range**, then whistle your lowest comfortable note and hold it for two seconds. After a short pause to take a breath, do the same with your highest comfortable note. You have up to 15 seconds for each, so you can feel your way down or up to it. The library then suggests a transposition for each song so that it fits your range.

If setup reports a problem, follow its suggestion (whistle closer, raise the input volume, or reduce background noise) and press **Repeat setup**. Repeat setup when you change rooms or microphones.

The app never switches microphones on its own. If your microphone is unplugged, it says so and stops listening until you choose an input again. A **● Listening** indicator in the top right corner shows whenever the microphone is in use: only on the Audio setup, Test input, and practice pages.

**Test input** lets you try a single note: pick a target and a difficulty, and whistle until the bar fills (1 second). Tick **Random note** for ear and pitch training: the app picks a random note from your comfortable range (or D5–E6 if you have not measured it), and each time you hit it, a new one appears after a moment. **New note** skips to another one, and the counter shows how many notes you have hit.

### 2. Choose a song

The library lists the songs with their length at their own tempo, their range, and your progress in the selected mode ("12 of 42 notes", "✓ Completed").

| Song | Range | Tempo | Length |
| --- | --- | --- | --- |
| Introductory exercise | G5–B5 | 60 bpm | 0:28 |
| Frère Jacques | D5–E6 | 100 bpm | 0:19 |
| Ode to Joy | D5–D6 | 100 bpm | 0:38 |
| Twinkle Twinkle Little Star | G5–E6 | 90 bpm | 0:32 |

Select a song to prepare it in the panel on the right. Mode, difficulty, and transposition are remembered for each song:

- **Mode:** **Guided** waits for you at every note; **Rhythm** keeps the beat after a count-in.
- **Tempo:** 30 to 120 beats per minute. Each song starts at its own tempo every time you select it; a slower tempo makes every note last longer. A changed tempo is used for Listen and Practice until you select another song or restart the app.
- **Difficulty:** **Easy** accepts notes within ±40 cents of the target, **Standard** within ±25 cents (a semitone is 100 cents).
- **Transposition:** moves the whole song up or down by semitones. If you measured your range, the panel suggests a transposition; press **Use** to apply it.

Then press **Listen…** to hear the song, **Start practice** (or double-click the song) to practice from the beginning, or **Continue from note n** to pick up where you stopped last time.

**Show note names** below the list turns the note names on the score on or off.

### 3. Listen to the song

The Listen page plays the song from the computer so you can hear how it should sound. The microphone is not used.

- **Sound:** **Piano** (a recorded concert grand, the default) or **Whistle** (a whistle-like tone, the sound you will imitate). The choice is remembered and also used by **Hear note** during practice.

- **Play song** plays from the highlighted note to the end; the highlight follows the notes. **Stop** keeps your place.
- **Previous note** and **Next note** (or the arrow keys) play one note at a time. Click any note to hear it. Rests are highlighted silently.
- Change the tempo and transposition here too; practice uses the same settings.
- **Practice from here** starts practice at the highlighted note.

### 4. Practice

The score shows the melody with note names. The current note is highlighted, and the notes you complete are marked with ✓. Notes are drawn an octave lower than they sound, as is usual for whistle and piccolo music; the names show the real pitch.

In **guided** mode:

- Whistle the highlighted note and hold it for its written length at the chosen tempo. At 60 bpm a quarter note is 1 second, a half note 2 seconds, and a whole note 4 seconds. The bar shows how long you have held it.
- Start whenever you are ready: silence before a note is never counted against you.
- **Rests** say "Take a breath": stay quiet for the rest's length.
- **Repeated notes** (the same note twice) need a short break between them. If you keep whistling, the app asks you to stop briefly and whistle the note again.
- **Tied notes** (joined by a curve) are one long note: hold them together without a break.
- A short break in a note (under a tenth of a second) pauses the bar; a longer break starts that note again and counts as a retry.

In **rhythm** mode, a four-beat count-in ("Get ready… 1, 2, 3, 4" and dots for each beat) starts the song, and it moves on with the beat whether or not you are ready:

- Start each note on its beat. You have a little leeway: up to a fifth of the note's length early or late, and at most 0.15 seconds.
- Hold each note for at least 80 percent of its length. You may let go a little early, for example to breathe before the next note.
- Stay quiet during rests, and stop briefly between repeated notes.
- If something goes wrong, the song stops at that note, marks it with ✗, and says what happened. Press **Retry** to count in again from that note; notes you already played stay completed.
- Tick **Metronome sound (use headphones)** in the preparation panel to hear a click on every beat, higher on beat one. The beat dots work without sound.

**Hear note** plays the note you should whistle. The app ignores the microphone while it plays, so it never mistakes its own sound for yours, and the note then starts over. In rhythm mode it is available when paused or after a mistake.

**Pause** stops listening. While paused you can:

- change the mode, tempo, difficulty, or transposition; practice continues from the same note;
- click a note to start from there, and Shift+click a later note to practice just that **section**, which is shaded on the score. **Restart section** starts it again, and **Clear section** returns to the whole song.

**Resume** continues (with a new count-in in rhythm mode). If the microphone is unplugged, practice pauses and never resumes by itself.

### 5. Review

When you reach the end of the song or section, the summary shows the mode, what you practiced, your active practice time, the number of retries, and the notes that needed the most retries. It can offer to **practice the hardest measure again**, or you can **Repeat** the same song or section, **Restart song** from the beginning, or go back to the **Library**.

Your progress is saved as you practice, for each song and mode. A song counts as completed in a mode once you have completed every note of it in that mode.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| Space | Play or stop (Listen); pause or resume (Practice) |
| Left / Right | Previous / next note (Listen) |
| H | Hear note (Practice) |
| R | Retry (rhythm mode) |
| Escape | Back to the library |

## Your data

Microphone audio is analyzed in memory and immediately discarded. It is never recorded or sent anywhere.

Settings are saved in `~/.config/whistle-trainer/` and progress in `~/.local/share/whistle-trainer/`. If one of these files becomes unreadable, the app starts with defaults, keeps the old file with a `.corrupt` suffix, and tells you.

**Reset progress…** in the preparation panel clears one song's progress, and **Reset all data…** below the song list clears all settings and progress. Both ask first.

## Credits

- Music font: [Bravura](https://github.com/steinbergmedia/bravura) by Steinberg Media Technologies, SIL Open Font License.
- Piano sound: [Salamander Grand Piano V3](https://archive.org/details/SalamanderGrandPianoV3) by Alexander Holm, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). The bundled samples were converted, retuned to exact pitch, and shortened; see `whistle_trainer/resources/sounds/piano/CREDITS.txt`.

## For developers

Install the test tools and run the tests:

```bash
scripts/setup.sh --dev
.venv/bin/python -m pytest
```

Product behavior is described in [PROJECT_SPEC.md](PROJECT_SPEC.md) and the technical design in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).
