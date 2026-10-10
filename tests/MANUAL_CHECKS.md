# Manual checks

Checks that need a real microphone and a real whistle. Run them on the reference system (Ubuntu 24.04 with PipeWire) and record the results at the bottom.

## Milestone 2: audio setup and pitch

### Setup

1. Open **Audio setup**. The input list shows your microphones by name, with the system default marked. The **Listening** indicator appears.
2. Make a sound: the activity meter moves.
3. Press **Start setup**, stay quiet for 3 seconds, then whistle one steady note. Setup completes and shows the background level, whistle level, and threshold.
4. Press **Start setup** and stay silent through both steps: after 10 seconds, the "No steady whistle" message appears.
5. Press **Measure my range** and whistle your lowest and then your highest comfortable note. The range is shown.
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

## Results

| Date | Microphone | Room | Background / whistle / threshold (dB) | Range | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
