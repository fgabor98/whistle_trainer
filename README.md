# Whistle Trainer

Whistle Trainer helps you learn to whistle melodies from simplified sheet music. It listens through your microphone and lets you move on only when you whistle the right note for the right length.

The app is in early development. This README describes only what works today.

## Requirements

- Linux (tested on Ubuntu 24.04 with PipeWire)
- Python 3.12 or newer
- These system packages:

```bash
sudo apt install python3-venv libportaudio2 libxcb-cursor0
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

## Your data

Settings are saved in `~/.config/whistle-trainer/` and progress in `~/.local/share/whistle-trainer/`. If one of these files becomes unreadable, the app starts with defaults, keeps the old file with a `.corrupt` suffix, and tells you.

## For developers

Install the test tools and run the tests:

```bash
scripts/setup.sh --dev
.venv/bin/python -m pytest
```

Product behavior is described in [PROJECT_SPEC.md](PROJECT_SPEC.md) and the technical design in [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md).
