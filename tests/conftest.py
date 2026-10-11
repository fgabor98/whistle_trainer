from __future__ import annotations

import os

import pytest

# Run Qt tests without opening windows on the desktop.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from whistle_trainer.music.musicxml import parse_string

DEFAULT_ATTRIBUTES = """
  <attributes>
    <divisions>2</divisions>
    <key><fifths>0</fifths></key>
    <time><beats>4</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef>
  </attributes>"""


def note(pitch: str = "C5", duration: int = 2, note_type: str | None = "quarter",
         extra: str = "", dots: int = 0) -> str:
    """A MusicXML note. pitch is like "C5", "F#4", "Bb4", or "rest"."""
    if pitch == "rest":
        body = "<rest/>"
    else:
        step, accidental, octave = pitch[0], pitch[1:-1], pitch[-1]
        alter = {"": "", "#": "<alter>1</alter>", "b": "<alter>-1</alter>"}[accidental]
        body = f"<pitch><step>{step}</step>{alter}<octave>{octave}</octave></pitch>"
    type_xml = f"<type>{note_type}</type>" if note_type else ""
    return f"<note>{body}<duration>{duration}</duration>{extra}{type_xml}{'<dot/>' * dots}</note>"


def whole(pitch: str = "C5", extra: str = "") -> str:
    return note(pitch, 8, "whole", extra)


def score(*measures: str, attributes: str = DEFAULT_ATTRIBUTES, title: str = "Test song",
          header: str = "") -> str:
    """A one-part score. The first measure gets the attributes."""
    body = "".join(
        f'<measure number="{i}">{attributes if i == 1 else ""}{content}</measure>'
        for i, content in enumerate(measures, start=1)
    )
    return (
        f'<score-partwise version="4.0"><work><work-title>{title}</work-title></work>{header}'
        '<part-list><score-part id="P1"><part-name>Whistle</part-name></score-part></part-list>'
        f'<part id="P1">{body}</part></score-partwise>'
    )


@pytest.fixture
def parse():
    return lambda text: parse_string(text, song_id="test")
