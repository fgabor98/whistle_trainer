# Whistle Trainer

Whistle Trainer helps you learn to whistle melodies from simplified sheet music. It listens through your microphone and lets you move on only when you whistle the right note for the right length.

The app is in early development. This README describes only what works today.

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

## What you can do now

### Browse the song library

The library lists the bundled songs with:

- **Length:** playing time at the song's default tempo, not counting waiting or retries.
- **Range:** the lowest and highest note you will whistle.

| Song | Range | Length |
| --- | --- | --- |
| Introductory exercise | G5–B5 | 0:28 |
| Frère Jacques | D5–E6 | 0:32 |
| Ode to Joy | D5–D6 | 1:04 |
| Twinkle Twinkle Little Star | G5–E6 | 0:48 |

Select a song to see its preparation panel on the right:

- **Tempo:** 30 to 120 beats per minute. At a slower tempo every note must be held longer. The estimated length updates as you change it.
- **Difficulty:** **Easy** accepts notes within ±40 cents of the target, **Standard** within ±25 cents (a semitone is 100 cents).

Tempo and difficulty are remembered for each song, and the app remembers the last song you selected.

### Set up your microphone

Press **Audio setup…** in the library.

1. Choose your microphone under **Input**. The app lists your PipeWire/PulseAudio devices by name and marks the system default. The **Activity** meter shows that sound is coming in. The **Output** choice is saved for later features.
2. Press **Start setup**. Stay quiet for about 3 seconds while the background is measured, then whistle one steady, comfortable note until setup completes. The app shows the measured levels and saves them for this microphone.
3. Optionally press **Measure my range**, then whistle your lowest and highest comfortable notes. Later milestones will use this range to suggest transposing songs.

If setup reports a problem, follow its suggestion (whistle closer, raise the input volume, or reduce background noise) and press **Repeat setup**. Repeat setup when you change rooms or microphones.

The app never switches microphones on its own. If your microphone is unplugged, it says so and stops listening until you choose an input again. A **● Listening** indicator in the top right corner shows whenever the microphone is in use; it is only in use on the Audio setup, Test input, and practice pages.

### Test your whistle

After setup, press **Test input**. Pick a target note and a difficulty, then whistle:

- **Whistle higher / Whistle lower** tells you which way to move. The pitch meter shows how far off you are; the shaded band is the accepted range (Easy ±40 cents, Standard ±25 cents; a semitone is 100 cents).
- **Hold this note** means you are on target: hold it until the bar fills (1 second).
- **Keep going** means you briefly broke off; continue within a moment and your progress is kept.
- **No clear pitch** means the app hears sound but no clear whistle.

Press **Try again** to repeat, or choose another note.

### Practice a song

Select a song and press **Start practice** (or double-click the song). The microphone must be set up first; if it is not, the page explains this and offers **Audio setup…**.

Choose a **Mode** in the preparation panel:

- **Guided:** the song waits for you at every note.
- **Rhythm:** after a count-in, the song keeps the beat (see below).

- The score shows the melody with note names. The current note is highlighted, and completed notes are marked with ✓. Notes are drawn an octave lower than they sound, as is usual for whistle and piccolo music; the names show the real pitch.
- Whistle the highlighted note and hold it for its written length at the chosen tempo. At 60 bpm a quarter note is 1 second, a half note 2 seconds, and a whole note 4 seconds. The bar shows how long you have held it.
- Start whenever you are ready: silence before a note is never counted against you.
- **Rests** say "Take a breath": stay quiet for the rest's length.
- **Repeated notes** (the same note twice) need a short break between them. If you keep whistling, the app asks you to stop briefly and whistle the note again.
- **Tied notes** (joined by a curve) are one long note: hold them together without a break.
- A short break in a note (under a tenth of a second) pauses the bar; a longer break starts that note again and counts as a retry.

In both modes, **Pause** stops listening and starts the current note over when you press **Resume**. **Restart song** goes back to the beginning. If the microphone is unplugged, practice pauses and never resumes by itself. At the end, the app shows your active practice time and number of retries, with **Repeat** and **Library** buttons.

### Rhythm mode

Rhythm mode is for practicing in time. After a four-beat count-in ("Get ready… 1, 2, 3, 4" and dots for each beat), the song moves on with the beat whether or not you are ready:

- Start each note on its beat. You have a little leeway: up to a fifth of the note's length early or late, and at most 0.15 seconds.
- Hold each note for at least 80 percent of its length. You may let go a little early, for example to breathe before the next note.
- Stay quiet during rests.
- Repeated notes need a fresh start: stop briefly between them.

If something goes wrong, the song stops at that note, marks it with ✗, and says what happened. Press **Retry** to count in again from that note; notes you already played stay completed. Pausing also leads to a new count-in when you resume.

Tick **Metronome sound (use headphones)** in the preparation panel to hear a click on every beat, with a higher click on beat one. The beat dots work without sound, and the clicks are best heard through headphones so the microphone does not pick them up.

## Your data

Microphone audio is analyzed in memory and immediately discarded. It is never recorded or sent anywhere.

Settings are saved in `~/.config/whistle-trainer/` and progress in `~/.local/share/whistle-trainer/`. If one of these files becomes unreadable, the app starts with defaults, keeps the old file with a `.corrupt` suffix, and tells you.

## For developers

Install the test tools and run the tests:

```bash
scripts/setup.sh --dev
.venv/bin/python -m pytest
```

Product behavior is described in [PROJECT_SPEC.md](PROJECT_SPEC.md) and the technical design in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).
