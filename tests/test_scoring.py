from datetime import timedelta

from leadengine.db import utcnow
from leadengine.scoring import dedupe_key, normalize_address, score_lead


def test_bigger_newer_closer_scores_higher():
    now = utcnow()
    base = dict(kind="permit", customer_type="homeowner", base_lat=36.85, base_lng=-76.13, now=now)
    strong = score_lead(job_type="new_construction", est_value=400_000, posted_at=now, lat=36.86, lng=-76.12, **base)
    weak = score_lead(job_type="remodel", est_value=3_000, posted_at=now - timedelta(days=60),
                      lat=37.5, lng=-77.4, **base)
    assert 0 <= weak < strong <= 100


def test_other_and_expired_bids_score_zero():
    now = utcnow()
    assert score_lead(job_type="other", kind="permit", customer_type="homeowner", est_value=None, posted_at=now) == 0
    assert score_lead(job_type="deck", kind="bid", customer_type="public", est_value=None, posted_at=now,
                      due_at=now - timedelta(days=1)) == 0


def test_address_normalization_and_dedupe_key():
    assert normalize_address("1214 West Little Creek Road, Norfolk VA") == "1214 w little creek rd"
    assert normalize_address("516 Dunstan Lane Apt 4") == "516 dunstan ln"
    assert dedupe_key("1214 W. Little Creek Rd", "deck") == dedupe_key("1214 West Little Creek Road", "deck")
    assert dedupe_key("Lot 4 Willow Bend", "deck") is None
