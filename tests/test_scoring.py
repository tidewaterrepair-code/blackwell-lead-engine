from datetime import timedelta

from pegasus.db import utcnow
from pegasus.intel.scoring import ScoreInput, dedupe_key, normalize_address, score


def test_bigger_newer_closer_scores_higher():
    now = utcnow()
    strong = score(ScoreInput(kind="permit", est_value=400_000, posted_at=now, lat=36.86, lng=-76.12),
                   base_lat=36.85, base_lng=-76.13, now=now)
    weak = score(ScoreInput(kind="permit", est_value=3_000, posted_at=now - timedelta(days=60), lat=37.5, lng=-77.4,
                            contractor_listed=True), base_lat=36.85, base_lng=-76.13, now=now)
    assert 0 <= weak.value < strong.value <= 100
    assert "Close by" in strong.reasons and "Fresh" in strong.reasons


def test_predictions_score_by_probability_and_window():
    now = utcnow()
    open_now = score(ScoreInput(kind="permit", est_value=None, posted_at=now, window_start=now - timedelta(days=1),
                                window_end=now + timedelta(days=20), probability=0.85), now=now)
    far_off = score(ScoreInput(kind="permit", est_value=None, posted_at=now, window_start=now + timedelta(days=200),
                               window_end=now + timedelta(days=400), probability=0.2), now=now)
    assert open_now.value > far_off.value
    assert "Window open now" in open_now.reasons


def test_closed_bids_score_zero_and_motivation_drives_real_estate():
    now = utcnow()
    assert score(ScoreInput(kind="bid", est_value=None, posted_at=now, due_at=now - timedelta(days=1)), now=now).value == 0
    hot = score(ScoreInput(kind="foreclosure", est_value=None, posted_at=now, trade_group="realestate", motivation=90),
                now=now)
    cold = score(ScoreInput(kind="sale", est_value=None, posted_at=now, trade_group="realestate", motivation=0),
                 now=now)
    assert hot.value > cold.value and "Highly motivated" in hot.reasons


def test_address_normalization_and_dedupe_key():
    assert normalize_address("1214 West Little Creek Road, Norfolk VA") == "1214 w little creek rd"
    assert normalize_address("516 Dunstan Lane Apt 4") == "516 dunstan ln"
    assert dedupe_key("1214 W. Little Creek Rd", "deck") == dedupe_key("1214 West Little Creek Road", "deck")
    assert dedupe_key("Lot 4 Willow Bend", "deck") is None
