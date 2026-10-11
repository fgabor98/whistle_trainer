from fractions import Fraction

import pytest

from conftest import DEFAULT_ATTRIBUTES, note, score, whole
from whistle_trainer.music.library import INTRO_SONG_ID, load_songs
from whistle_trainer.music.model import EventKind, KeySignature
from whistle_trainer.music.musicxml import SongFormatError

TIE_START = '<tie type="start"/>'
TIE_STOP = '<tie type="stop"/>'


def test_reads_title_time_and_events(parse):
    song = parse(score(note("C5") + note("D5") + note("rest") + note("E5")))
    assert song.title == "Test song"
    assert song.time.beats == 4 and song.time.beat_type == 4
    assert [e.kind for e in song.events] == [EventKind.NOTE, EventKind.NOTE, EventKind.REST, EventKind.NOTE]
    assert [e.start for e in song.events] == [0, 1, 2, 3]
    assert [e.index for e in song.events] == [0, 1, 2, 3]
    assert song.length == 4


def test_title_falls_back_to_movement_title_then_id(parse):
    text = score(whole(), title="").replace("<work><work-title></work-title></work>", "")
    assert parse(text).title == "test"
    text = text.replace("<part-list>", "<movement-title>Movement</movement-title><part-list>")
    assert parse(text).title == "Movement"


def test_without_transpose_element_sounds_an_octave_higher(parse):
    song = parse(score(whole("G4")))
    assert song.events[0].pitch.name == "G5"


def test_transpose_element_is_applied(parse):
    attributes = DEFAULT_ATTRIBUTES.replace(
        "</attributes>", "<transpose><chromatic>-2</chromatic><diatonic>-1</diatonic></transpose></attributes>"
    )
    song = parse(score(whole("D5"), attributes=attributes))
    assert song.events[0].pitch.name == "C5"
    # Written in C major, a B♭ instrument sounds in B♭ major.
    assert song.key == KeySignature(-2)


def test_octave_only_transpose_keeps_spelling(parse):
    attributes = DEFAULT_ATTRIBUTES.replace(
        "</attributes>", "<transpose><chromatic>0</chromatic><octave-change>1</octave-change></transpose></attributes>"
    )
    song = parse(score(whole("F#4"), attributes=attributes))
    assert song.events[0].pitch.name == "F♯5"


def test_ties_merge_into_one_event_across_barlines(parse):
    song = parse(score(
        note("C5", 4, "half") + note("D5", 4, "half", TIE_START),
        note("D5", 2, "quarter", TIE_STOP + TIE_START) + note("D5", 2, "quarter", TIE_STOP) + note("E5", 4, "half"),
    ))
    assert len(song.events) == 3
    tied = song.events[1]
    assert tied.duration == 4 and tied.start == 2 and tied.is_tied
    assert [p.measure_index for p in tied.parts] == [0, 1, 1]
    assert song.events[2].start == 6


def test_dotted_and_eighth_notes(parse):
    song = parse(score(note("C5", 3, "quarter", dots=1) + note("D5", 1, "eighth") + note("E5", 4, "half")))
    assert [e.duration for e in song.events] == [Fraction(3, 2), Fraction(1, 2), 2]
    assert song.events[0].parts[0].dots == 1


def test_whole_measure_rest_without_type(parse):
    song = parse(score(whole(), '<note><rest measure="yes"/><duration>8</duration></note>', whole()))
    rest = song.events[1]
    assert rest.kind is EventKind.REST and rest.duration == 4 and rest.parts[0].note_type is None


def test_missing_type_is_derived_from_duration(parse):
    song = parse(score(note("C5", 6, None) + note("D5", 2, None)))
    assert song.events[0].parts[0].note_type == "half"
    assert song.events[0].parts[0].dots == 1


def test_divisions_can_change(parse):
    second = '<attributes><divisions>4</divisions></attributes>' + note("D5", 16, "whole")
    song = parse(score(whole(), second))
    assert song.events[1].duration == 4


def test_pickup_and_short_last_measure_are_allowed(parse):
    song = parse(score(note("C5"), whole(), note("D5", 6, "half", dots=1)))
    assert [m.duration for m in song.measures] == [1, 4, 3]
    assert song.events[1].start == 1


@pytest.mark.parametrize("header, expected", [
    ("", 60),
    ('<direction><sound tempo="96"/></direction>', 96),
    ('<direction><direction-type><metronome><beat-unit>half</beat-unit>'
     '<per-minute>40</per-minute></metronome></direction-type></direction>', 80),
    ('<direction><direction-type><metronome><beat-unit>quarter</beat-unit><beat-unit-dot/>'
     '<per-minute>40</per-minute></metronome></direction-type></direction>', 60),
    ('<sound tempo="200"/>', 120),
    ('<sound tempo="10"/>', 30),
])
def test_tempo(parse, header, expected):
    assert parse(score(header + whole())).tempo == expected


@pytest.mark.parametrize("text, message", [
    ("<not-xml", "not valid XML"),
    ("<score-timewise/>", "partwise"),
    (score(whole()).replace("</part></score-partwise>", '</part><part id="P2"></part></score-partwise>'), "exactly one part"),
    (score(note("C5") + "<note><chord/><pitch><step>E</step><octave>5</octave></pitch><duration>2</duration></note>"
           + note() + note() + note()), "chords"),
    (score(whole() + "<backup><duration>8</duration></backup>" + whole()), "voices"),
    (score(note("C5", extra="<voice>1</voice>") + note("D5", extra="<voice>2</voice>") + note() + note()), "voices"),
    (score("<note><grace/><pitch><step>C</step><octave>5</octave></pitch><type>eighth</type></note>" + whole()), "grace"),
    (score(note("C5", 1, "quarter") * 4), "does not match its written type"),
    (score(note("C5", 5, None) + note("C5", 3, None)), "cannot be written as one note"),
    (score(whole() + '<barline><repeat direction="backward"/></barline>'), "repeats"),
    (score('<direction><sound dacapo="yes"/></direction>' + whole()), "jumps"),
    (score(whole(), attributes=DEFAULT_ATTRIBUTES.replace("<sign>G</sign>", "<sign>F</sign>")), "treble"),
    (score(whole(), whole(), attributes=DEFAULT_ATTRIBUTES.replace("<time>", "<!--").replace("</time>", "-->")), "time signature"),
    (score(whole(), note("C5") * 3, whole()), "requires 4"),
    (score(whole() + note()), "requires 4"),
    (score(note("C5", 4, "half", TIE_START) + note("D5", 4, "half", TIE_STOP)), "different pitch"),
    (score(note("C5", 4, "half", TIE_START) + note("C5", 4, "half")), "does not end"),
    (score(whole("C5", TIE_START)), "does not end"),
    (score(note("C5", 4, "half") + note("C5", 4, "half", TIE_STOP)), "ends without starting"),
    (score(note("rest", 8, "whole", TIE_START)), "rests cannot be tied"),
    (score(whole("rest")), "no notes"),
    (score(whole().replace("<step>C</step>", "<step>C</step><alter>0.5</alter>")), "microtones"),
    (score(whole(), "<print/>"), "is empty"),
])
def test_rejects_unsupported_content(parse, text, message):
    with pytest.raises(SongFormatError, match=message):
        parse(text)


def test_error_names_file_and_measure(parse):
    with pytest.raises(SongFormatError) as info:
        parse(score(whole(), whole() + "<backup><duration>8</duration></backup>"))
    assert info.value.measure == "2"
    assert str(info.value) == "test, measure 2: multiple voices are not supported"


def test_ignores_lyrics_dynamics_and_slurs(parse):
    extra = "<lyric><text>la</text></lyric><notations><slur type=\"start\"/></notations>"
    dynamics = "<direction><direction-type><dynamics><p/></dynamics></direction-type></direction>"
    song = parse(score(dynamics + whole().replace("</note>", extra + "</note>")))
    assert len(song.events) == 1


EXPECTED_SONGS = {
    "introductory-exercise": ("Introductory exercise", "G5", "B5"),
    "twinkle-twinkle-little-star": ("Twinkle Twinkle Little Star", "G5", "E6"),
    "ode-to-joy": ("Ode to Joy", "D5", "D6"),
    "frere-jacques": ("Frère Jacques", "D5", "E6"),
}


def test_bundled_songs_load_with_expected_ranges():
    library = load_songs()
    assert library.errors == []
    assert library.songs[0].id == INTRO_SONG_ID
    assert {s.id: (s.title, s.lowest.name, s.highest.name) for s in library.songs} == EXPECTED_SONGS
    for song in library.songs:
        assert song.key == KeySignature(1)
        assert song.time.beats == 4 and song.time.beat_type == 4
        assert song.tempo == {"introductory-exercise": 60, "twinkle-twinkle-little-star": 90,
                              "ode-to-joy": 100, "frere-jacques": 100}[song.id]
        # The shortest note is an eighth.
        assert min(e.duration for e in song.events) >= Fraction(1, 2)


def test_introductory_exercise_covers_the_basics():
    song = load_songs().get(INTRO_SONG_ID)
    notes = song.notes
    assert any(e.kind is EventKind.REST for e in song.events)
    assert any(e.is_tied for e in notes)
    assert any(a.pitch == b.pitch and b.start == a.end for a, b in zip(notes, notes[1:]))
    assert {p.note_type for e in notes for p in e.parts} >= {"whole", "half", "quarter"}


def test_load_errors_are_collected(tmp_path):
    (tmp_path / "good.musicxml").write_text(score(whole()), encoding="utf-8")
    (tmp_path / "bad.musicxml").write_text("<broken", encoding="utf-8")
    library = load_songs(tmp_path)
    assert [s.id for s in library.songs] == ["good"]
    assert [e.file for e in library.errors] == ["bad.musicxml"]


TRIPLET = "<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>"
SIX = DEFAULT_ATTRIBUTES.replace("<divisions>2</divisions>", "<divisions>6</divisions>")


def test_triplets_are_read_with_their_sounding_length(parse):
    triplet_eighth = note("C5", 2, "eighth", TRIPLET)
    triplet_quarter = note("D5", 4, "quarter", TRIPLET)
    song = parse(score(triplet_eighth * 3 + triplet_quarter + note("E5", 2, "eighth", TRIPLET)
                       + note("F5", 12, "half"), attributes=SIX))
    assert [e.duration for e in song.events] == [Fraction(1, 3)] * 3 + [Fraction(2, 3), Fraction(1, 3), 2]
    assert [e.start for e in song.events][3:5] == [1, Fraction(5, 3)]
    assert song.events[0].parts[0].tuplet == (3, 2)
    assert song.events[5].parts[0].tuplet is None
    assert song.length == 4


@pytest.mark.parametrize("text, message", [
    (score(note("C5", 3, "eighth", TRIPLET) + note("C5", 21, "half", dots=2), attributes=SIX),
     "does not match its written type"),
    (score(note("C5", 2, None, TRIPLET) + note("C5", 22, None), attributes=SIX), "no written type"),
    (score(note("C5", 2, "eighth", TRIPLET.replace("</time-modification>",
                                                   "<normal-type>quarter</normal-type></time-modification>")) * 3
           + note("C5", 18, "half", dots=1), attributes=SIX), "different normal note type"),
])
def test_rejects_invalid_tuplets(parse, text, message):
    with pytest.raises(SongFormatError, match=message):
        parse(text)


def test_key_and_time_changes_apply_from_their_measure(parse):
    three_four = "<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>"
    d_major = "<attributes><key><fifths>2</fifths></key></attributes>"
    song = parse(score(whole(), three_four + note("C5", 6, "half", dots=1), d_major + note("D5", 6, "half", dots=1)))
    assert [(m.time.beats, m.time.beat_type) for m in song.measures] == [(4, 4), (3, 4), (3, 4)]
    assert [m.key.fifths for m in song.measures] == [0, 0, 2]
    assert song.time == song.measures[0].time and song.key == song.measures[0].key
    assert song.length == 10


def test_measure_length_follows_the_current_time_signature(parse):
    three_four = "<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>"
    with pytest.raises(SongFormatError, match="requires 3"):
        parse(score(whole(), three_four + whole(), whole()))


@pytest.mark.parametrize("change", [
    "<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>",
    "<attributes><key><fifths>2</fifths></key></attributes>",
])
def test_changes_in_the_middle_of_a_measure_are_rejected(parse, change):
    with pytest.raises(SongFormatError, match="must be at the start of a measure"):
        parse(score(note("C5", 4, "half") + change + note("C5", 4, "half")))


def test_implicit_measures_may_be_short(parse):
    text = score(whole(), note("C5", 4, "half"), whole()).replace('<measure number="2">', '<measure number="2" implicit="yes">')
    assert parse(text).measures[1].duration == 2


def test_chromatic_transposition_applies_to_every_measure_key(parse):
    attributes = DEFAULT_ATTRIBUTES.replace(
        "</attributes>", "<transpose><chromatic>-2</chromatic><diatonic>-1</diatonic></transpose></attributes>")
    song = parse(score(whole(), "<attributes><key><fifths>1</fifths></key></attributes>" + whole(), attributes=attributes))
    assert [m.key.fifths for m in song.measures] == [-2, -1]  # B♭ and F major sounding
