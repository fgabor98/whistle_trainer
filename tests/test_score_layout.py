from conftest import DEFAULT_ATTRIBUTES, note, score, whole
from whistle_trainer.music.library import load_songs
from whistle_trainer.music.model import Pitch
from whistle_trainer.ui.score_layout import key_alters, layout_song, staff_position
from whistle_trainer.ui.score_view import ScoreView

TIE_START = '<tie type="start"/>'
TIE_STOP = '<tie type="stop"/>'
G_MAJOR = DEFAULT_ATTRIBUTES.replace("<fifths>0</fifths>", "<fifths>1</fifths>")


def test_staff_positions():
    assert staff_position(Pitch("E", 0, 4)) == 0
    assert staff_position(Pitch("F", 0, 5)) == 8
    assert staff_position(Pitch("C", 0, 4)) == -2
    assert staff_position(Pitch("A", 0, 5)) == 10


def test_key_alters():
    assert key_alters(1) == {"F": 1}
    assert key_alters(-2) == {"B": -1, "E": -1}
    assert key_alters(0) == {}


def test_notes_are_drawn_an_octave_below_sounding(parse):
    layout = layout_song(parse(score(whole("G4"))))  # sounds G5
    assert layout.parts[0].position == 2
    assert layout.events[0].label == "G5"


def test_accidentals_follow_key_and_measure(parse):
    song = parse(score(
        note("F#4") + note("F4") + note("F4") + note("F#4"),
        note("F#4") * 4,
        attributes=G_MAJOR,
    ))
    accidentals = [p.accidental for p in layout_song(song).parts]
    assert accidentals == [None, 0, None, 1, None, None, None, None]


def test_tied_parts_share_an_event_and_no_repeated_accidental(parse):
    song = parse(score(
        note("C5") * 2 + note("Bb4", 4, "half", TIE_START),
        note("Bb4", 4, "half", TIE_STOP) + note("C5", 4, "half"),
    ))
    layout = layout_song(song)
    tied = layout.events[2]
    assert len(tied.parts) == 2
    assert tied.parts[0].tied_to_next and not tied.parts[1].tied_to_next
    assert [p.accidental for p in tied.parts] == [-1, None]
    assert len(layout.barlines) == 2  # between the measures, and the final barline


def test_stem_direction_and_rests(parse):
    layout = layout_song(parse(score(note("A4") + note("B4") + note("rest") + note("D5"))))
    assert [p.stem_up for p in layout.parts if p.position is not None] == [True, False, False]
    assert layout.parts[2].position is None


def test_events_advance_left_to_right_and_longer_notes_take_more_space(parse):
    layout = layout_song(parse(score(note("C5", 1, "eighth") * 2 + note("C5", 2) + note("C5", 4, "half"))))
    xs = [p.x for p in layout.parts]
    assert xs == sorted(xs)
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    assert gaps[2] > gaps[1]  # a quarter takes more space than an eighth
    assert layout.width > xs[-1]


def test_all_bundled_songs_lay_out():
    for song in load_songs().songs:
        layout = layout_song(song)
        assert len(layout.events) == len(song.events)
        assert all(e.right > e.left for e in layout.events)


def test_score_view_scrolls_to_keep_current_note_visible(qtbot):
    view = ScoreView()
    qtbot.addWidget(view)
    view.resize(600, 240)
    view.set_song(load_songs().get("ode-to-joy"))
    view.set_current(0, animate=False)
    assert view.scroll == 0
    view.set_current(40, animate=False)
    center = view.x_for(view.layout_data.events[40].center)
    assert abs(center - 200) < 1
    view.grab()  # paints without errors


TRIPLET = "<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>"
SIX = DEFAULT_ATTRIBUTES.replace("<divisions>2</divisions>", "<divisions>6</divisions>")


def test_triplets_are_grouped_until_a_full_beat(parse):
    song = parse(score(
        note("C5", 2, "eighth", TRIPLET) * 3            # one group of three eighths
        + note("D5", 4, "quarter", TRIPLET) + note("E5", 2, "eighth", TRIPLET)  # quarter + eighth
        + note("F5", 6, "quarter") + note("G5", 6, "quarter"),
        attributes=SIX,
    ))
    layout = layout_song(song)
    assert layout.tuplets == [(0, 2, 3), (3, 4, 3)]
    assert layout.beams == []  # triplet eighths are not beamed as pairs


def test_triplets_draw_without_errors(parse, qtbot):
    song = parse(score(note("C5", 2, "eighth", TRIPLET) * 3 + note("D5", 18, "half", dots=1), attributes=SIX))
    view = ScoreView()
    qtbot.addWidget(view)
    view.resize(600, 240)
    view.set_song(song)
    view.set_current(0, animate=False)
    view.grab()
