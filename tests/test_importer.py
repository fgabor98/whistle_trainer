"""Importer tests on small made-up piano scores."""

import zipfile
from fractions import Fraction

import pytest

from whistle_trainer.music.importer import (
    ScoreImportError,
    _decompose,
    extract,
    read_score,
    read_score_text,
    safe_file_name,
    save,
)
from whistle_trainer.music.musicxml import parse_file


def n(pitch: str, duration: int, staff: int = 1, voice: int = 1, chord: bool = False, extra: str = "",
      note_type: str = "quarter") -> str:
    """A note; pitch like "C5", "F#4", or "rest"."""
    if pitch == "rest":
        body = "<rest/>"
    else:
        step, accidental, octave = pitch[0], pitch[1:-1], pitch[-1]
        alter = {"": "", "#": "<alter>1</alter>", "b": "<alter>-1</alter>"}[accidental]
        body = f"<pitch><step>{step}</step>{alter}<octave>{octave}</octave></pitch>"
    return (f"<note>{'<chord/>' if chord else ''}{body}<duration>{duration}</duration>{extra}"
            f"<voice>{voice}</voice><type>{note_type}</type><staff>{staff}</staff></note>")


def backup(duration: int) -> str:
    return f"<backup><duration>{duration}</duration></backup>"


ATTRIBUTES = ("<attributes><divisions>1</divisions><key><fifths>0</fifths></key>"
              "<time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves>"
              "<clef number=\"1\"><sign>G</sign><line>2</line></clef>"
              "<clef number=\"2\"><sign>F</sign><line>4</line></clef></attributes>")


def piano(*measures: str, attributes: str = ATTRIBUTES, title: str = "Test Piece", extra_parts: str = "",
          part_list_extra: str = "", first_name: str = "Piano") -> str:
    body = "".join(f'<measure number="{i}">{attributes if i == 1 else ""}{m}</measure>'
                   for i, m in enumerate(measures, start=1))
    return (f'<?xml version="1.0"?><score-partwise version="4.0"><work><work-title>{title}</work-title></work>'
            f'<part-list><score-part id="P1"><part-name>{first_name}</part-name></score-part>{part_list_extra}</part-list>'
            f'<part id="P1">{body}</part>{extra_parts}</score-partwise>')


def names(result) -> list[str]:
    return [e.pitch.name if e.pitch else "rest" for e in result.song.events]


def melody_measure(*pitches: str) -> str:
    """Four quarter notes in the right hand over a whole-note bass."""
    return "".join(n(p, 1) for p in pitches) + backup(4) + n("C3", 4, staff=2, note_type="whole")


def test_right_hand_top_notes_become_the_melody():
    text = piano(
        n("B5", 1) + n("G5", 1, chord=True) + n("D5", 1, chord=True) + n("A5", 1) + n("G5", 2, note_type="half")
        + backup(4) + n("C3", 4, staff=2, note_type="whole"),
    )
    score = read_score_text(text, "test.musicxml")
    assert [c.label for c in score.candidates] == ["Piano, upper staff", "Piano, lower staff"]
    assert score.default_candidate == 0
    result = extract(score, 0)
    assert names(result) == ["B5", "A5", "G5"]  # chord notes under E5 are left out
    assert [e.duration for e in result.song.events] == [1, 1, 2]
    assert result.report.notes_left_out == 2
    assert result.report.octave_shift == 0


def test_accompaniment_under_a_held_melody_note_is_left_out():
    text = piano(
        n("D6", 4, note_type="whole") + backup(4)
        + n("B5", 1, voice=2) + n("A5", 1, voice=2) + n("G5", 2, voice=2, note_type="half")
        + backup(4) + n("C3", 4, staff=2, note_type="whole"),
    )
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert names(result) == ["D6"] and result.song.events[0].duration == 4


def test_a_new_higher_note_cuts_the_previous_one_short():
    text = piano(n("G5", 2, note_type="half") + backup(2) + n("rest", 1, voice=2) + n("B5", 3, voice=2,
                 note_type="half", extra="<dot/>") + backup(4) + n("C3", 4, staff=2, note_type="whole"))
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert names(result) == ["G5", "B5"]
    assert [e.duration for e in result.song.events] == [1, 3]


def test_lower_staff_can_be_chosen():
    text = piano(melody_measure("C5", "D5", "E5", "F5"))
    result = extract(read_score_text(text, "t.musicxml"), 1)
    assert result.report.line == "Piano, lower staff"
    assert names(result) == ["C6"]  # C3 moved up three octaves into the whistle range
    assert result.report.octave_shift == 36


def test_vocal_part_is_the_default_line():
    vocal = ('<part id="P2"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>'
             '<time><beats>4</beats><beat-type>4</beat-type></time></attributes>'
             + n("A4", 2, note_type="half") + n("B4", 2, note_type="half") + "</measure></part>")
    text = piano(melody_measure("C5", "D5", "E5", "F5"), extra_parts=vocal,
                 part_list_extra='<score-part id="P2"><part-name>Voice</part-name></score-part>')
    score = read_score_text(text, "t.musicxml")
    assert score.candidates[score.default_candidate].label == "Voice"
    assert names(extract(score, score.default_candidate)) == ["A5", "B5"]


def test_melody_is_moved_by_octaves_into_the_whistle_range():
    result = extract(read_score_text(piano(melody_measure("C4", "E4", "G4", "C5")), "t.musicxml"), 0)
    assert names(result) == ["C5", "E5", "G5", "C6"]
    assert result.report.octave_shift == 12


def test_repeats_and_endings_are_written_out():
    text = piano(
        '<barline location="left"><repeat direction="forward"/></barline>' + melody_measure("G5", "G5", "G5", "G5"),
        '<barline location="left"><ending number="1" type="start"/></barline>' + melody_measure("A5", "A5", "A5", "A5")
        + '<barline location="right"><ending number="1" type="stop"/><repeat direction="backward"/></barline>',
        '<barline location="left"><ending number="2" type="start"/></barline>' + melody_measure("B5", "B5", "B5", "B5")
        + '<barline location="right"><ending number="2" type="discontinue"/></barline>',
        melody_measure("C6", "C6", "C6", "C6"),
    )
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert [names(result)[i] for i in range(0, 16, 4)] == ["G5", "A5", "G5", "B5"]
    assert names(result)[16] == "C6" and len(result.song.measures) == 5
    assert result.report.measures_written_out == 1


def test_repeat_times_attribute():
    text = piano(melody_measure("G5", "A5", "B5", "C6") + '<barline location="right"><repeat direction="backward" times="3"/></barline>')
    assert len(extract(read_score_text(text, "t.musicxml"), 0).song.measures) == 3


def test_da_capo_al_fine():
    text = piano(
        melody_measure("G5", "G5", "G5", "G5") + '<direction><direction-type><words>Fine</words></direction-type><sound fine="yes"/></direction>',
        melody_measure("A5", "A5", "A5", "A5") + '<direction><direction-type><words>D.C. al Fine</words></direction-type><sound dacapo="yes"/></direction>',
    )
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert [m for m in (names(result)[i] for i in range(0, 12, 4))] == ["G5", "A5", "G5"]
    assert len(result.song.measures) == 3


def test_dal_segno_al_coda():
    text = piano(
        melody_measure("G5", "G5", "G5", "G5"),
        '<direction><direction-type><segno/></direction-type><sound segno="segno"/></direction>' + melody_measure("A5", "A5", "A5", "A5"),
        melody_measure("B5", "B5", "B5", "B5") + '<direction><direction-type><words>To Coda</words></direction-type><sound tocoda="coda"/></direction>',
        melody_measure("C6", "C6", "C6", "C6") + '<direction><direction-type><words>D.S. al Coda</words></direction-type><sound dalsegno="segno"/></direction>',
        '<direction><direction-type><coda/></direction-type><sound coda="coda"/></direction>' + melody_measure("D6", "D6", "D6", "D6"),
    )
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert [names(result)[i] for i in range(0, len(result.song.events), 4)] == ["G5", "A5", "B5", "C6", "A5", "B5", "D6"]


def test_unresolvable_jump_is_reported():
    text = piano(melody_measure("G5", "G5", "G5", "G5") + '<direction><sound dalsegno="segno"/></direction>')
    with pytest.raises(ScoreImportError, match="no segno"):
        read_score_text(text, "t.musicxml")


def test_grace_notes_are_removed_and_counted():
    grace = '<note><grace/><pitch><step>F</step><octave>5</octave></pitch><voice>1</voice><type>eighth</type><staff>1</staff></note>'
    result = extract(read_score_text(piano(grace + melody_measure("G5", "A5", "B5", "C6")), "t.musicxml"), 0)
    assert names(result) == ["G5", "A5", "B5", "C6"] and result.report.grace_notes_removed == 1


def test_triplets_keep_their_notation():
    triplet = "<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>"
    attributes = ATTRIBUTES.replace("<divisions>1</divisions>", "<divisions>3</divisions>")
    text = piano(n("G5", 1, extra=triplet, note_type="eighth") + n("A5", 1, extra=triplet, note_type="eighth")
                 + n("B5", 1, extra=triplet, note_type="eighth") + n("C6", 9, note_type="half", extra="<dot/>")
                 + backup(12) + n("C3", 12, staff=2, note_type="whole"), attributes=attributes)
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert [e.duration for e in result.song.events] == [Fraction(1, 3)] * 3 + [3]
    assert [e.parts[0].tuplet for e in result.song.events] == [(3, 2)] * 3 + [None]
    assert result.report.notes_rounded == 0


def test_quintuplets_are_rounded_and_counted():
    five = "<time-modification><actual-notes>5</actual-notes><normal-notes>4</normal-notes></time-modification>"
    attributes = ATTRIBUTES.replace("<divisions>1</divisions>", "<divisions>5</divisions>")
    quintuplet = "".join(n(p, 1, extra=five, note_type="16th") for p in ("G5", "A5", "B5", "C6", "D6"))
    text = piano(quintuplet + n("E6", 15, note_type="half", extra="<dot/>") + backup(20)
                 + n("C3", 20, staff=2, note_type="whole"), attributes=attributes)
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert names(result)[-1] == "E6" and sum(e.duration for e in result.song.events) == 4
    assert result.report.notes_rounded >= 3


def test_key_and_time_changes_and_pickup_are_kept():
    change = "<attributes><key><fifths>2</fifths></key><time><beats>3</beats><beat-type>4</beat-type></time></attributes>"
    text = piano(n("D5", 1) + backup(1) + n("G2", 1, staff=2),
                 melody_measure("G5", "A5", "B5", "C6"),
                 change + n("C#6", 3, note_type="half", extra="<dot/>") + backup(3) + n("D3", 3, staff=2, note_type="half", extra="<dot/>"))
    text = text.replace('<measure number="1">', '<measure number="1" implicit="yes">')
    result = extract(read_score_text(text, "t.musicxml"), 0)
    song = result.song
    assert [m.duration for m in song.measures] == [1, 4, 3]
    assert [(m.time.beats, m.key.fifths) for m in song.measures] == [(4, 0), (4, 0), (3, 2)]
    assert names(result)[-1] == "C♯6"


def test_rests_fill_gaps_and_empty_measures():
    text = piano(n("G5", 1) + n("rest", 3, note_type="half", extra="<dot/>") + backup(4) + n("C3", 4, staff=2, note_type="whole"),
                 n("rest", 4, note_type="whole") + backup(4) + n("C3", 4, staff=2, note_type="whole"),
                 melody_measure("A5", "B5", "C6", "D6"))
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert names(result)[:3] == ["G5", "rest", "rest"]
    assert result.song.events[2].parts[0].note_type is None  # a whole-measure rest


def test_ties_across_the_barline_are_one_note():
    text = piano(n("G5", 3, note_type="half", extra="<dot/>") + n("A5", 1, extra='<tie type="start"/>')
                 + backup(4) + n("C3", 4, staff=2, note_type="whole"),
                 n("A5", 2, note_type="half", extra='<tie type="stop"/>') + n("B5", 2, note_type="half")
                 + backup(4) + n("C3", 4, staff=2, note_type="whole"))
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert names(result) == ["G5", "A5", "B5"]
    assert result.song.events[1].duration == 3 and result.song.events[1].is_tied


def test_compressed_mxl_files(tmp_path):
    path = tmp_path / "song.mxl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
        archive.writestr("score.xml", piano(melody_measure("G5", "A5", "B5", "C6")))
    assert names(extract(read_score(path), 0)) == ["G5", "A5", "B5", "C6"]


@pytest.mark.parametrize("text, message", [
    ("<oops", "not valid MusicXML"),
    ("<score-timewise/>", "Timewise"),
    ('<score-partwise><part-list/><part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>'
     + n("rest", 4, note_type="whole") + "</measure></part></score-partwise>", "no notes"),
])
def test_unusable_files_are_reported(text, message):
    with pytest.raises(ScoreImportError, match=message):
        read_score_text(text, "t.musicxml")


def test_every_length_on_the_grid_can_be_written():
    assert all(_decompose(units) is not None for units in range(2, 24 * 8))


def test_saved_file_loads_and_names_are_unique(tmp_path):
    result = extract(read_score_text(piano(melody_measure("G5", "A5", "B5", "C6")), "t.musicxml"), 0)
    first = save(result, "My Song!", tmp_path)
    second = save(result, "My Song!", tmp_path)
    assert (first.name, second.name) == ("my-song.musicxml", "my-song-2.musicxml")
    song = parse_file(first)
    assert song.title == "My Song!" and [e.pitch.name for e in song.events] == ["G5", "A5", "B5", "C6"]
    assert safe_file_name("???", tmp_path).name == "song.musicxml"


def test_measures_are_fitted_to_their_time_signature():
    overfull = melody_measure("G5", "A5", "B5", "C6") + n("D6", 1)  # five beats in 4/4
    underfull = n("G5", 1) + n("A5", 1) + backup(2) + n("C3", 2, staff=2, note_type="half")  # two beats
    text = piano(melody_measure("G5", "A5", "B5", "C6"), overfull, underfull, melody_measure("G5", "A5", "B5", "C6"))
    result = extract(read_score_text(text, "t.musicxml"), 0)
    assert [m.duration for m in result.song.measures] == [4, 4, 4, 4]
    assert "D6" not in names(result)  # cut at the barline
    assert names(result)[10] == "rest"  # the short measure is filled
    assert (result.report.measures_too_long, result.report.measures_too_short) == (1, 1)
