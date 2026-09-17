from kasauti.imagecheck import analyze_lens


def test_title_year_hint_from_undated_matches():
    raw = {
        "visual_matches": [
            {"title": "2004 Indian Ocean earthquake and tsunami - Wikipedia",
             "link": "https://en.wikipedia.org/wiki/2004_tsunami"},
            {"title": "Remembering the 2004 tsunami disaster",
             "link": "https://example.com/a"},
            {"title": "Deadliest disasters of the past 100 years",
             "link": "https://example.com/b"},
        ]
    }
    analysis = analyze_lens("https://img.example/x.jpg", raw)
    assert analysis.title_year_hint == 2004
    assert analysis.earliest_date is None
    assert "2004" in analysis.note


def test_dated_match_beats_title_hint():
    raw = {
        "visual_matches": [
            {"title": "Chennai floods 2015 - Wikipedia",
             "link": "https://en.wikipedia.org/wiki/2015_floods",
             "date": "Dec 3, 2015"},
        ]
    }
    analysis = analyze_lens("https://img.example/x.jpg", raw)
    assert analysis.earliest_date is not None
    assert analysis.earliest_date.year == 2015
    assert "2015-12-03" in analysis.note


def test_no_matches_note_is_neutral():
    analysis = analyze_lens("https://img.example/x.jpg", {})
    assert analysis.matches == []
    assert "neither confirms nor debunks" in analysis.note
