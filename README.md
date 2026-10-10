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

The app remembers the last song you selected.

### Set up your microphone

Press **Audio setup…** in the library.

1. Choose your microphone under **Input**. The app lists your PipeWire/PulseAudio devices by name and marks the system default. The **Activity** meter shows that sound is coming in. The **Output** choice is saved for later features.
2. Press **Start setup**. Stay quiet for about 3 seconds while the background is measured, then whistle one steady, comfortable note until setup completes. The app shows the measured levels and saves them for this microphone.
3. Optionally press **Measure my range**, then whistle your lowest and highest comfortable notes. Later milestones will use this range to suggest transposing songs.

If setup reports a problem, follow its suggestion (whistle closer, raise the input volume, or reduce background noise) and press **Repeat setup**. Repeat setup when you change rooms or microphones.

The app never switches microphones on its own. If your microphone is unplugged, it says so and stops listening until you choose an input again. A **● Listening** indicator in the top right corner shows whenever the microphone is in use; it is only in use on the Audio setup and Test input pages.

### Test your whistle

After setup, press **Test input**. Pick a target note and a difficulty, then whistle:

- **Whistle higher / Whistle lower** tells you which way to move. The pitch meter shows how far off you are; the shaded band is the accepted range (Easy ±40 cents, Standard ±25 cents; a semitone is 100 cents).
- **Hold this note** means you are on target: hold it until the bar fills (1 second).
- **Keep going** means you briefly broke off; continue within a moment and your progress is kept.
- **No clear pitch** means the app hears sound but no clear whistle.

Press **Try again** to repeat, or choose another note.

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
