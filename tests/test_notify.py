from leadengine.db import Lead, session_scope
from leadengine.notify import build_digest, send_digest
from leadengine.pipeline import add_manual_lead


def test_digest_builds_and_skips_without_smtp():
    with session_scope() as s:
        add_manual_lead(s, {"title": "Second story addition, 1200 sq ft", "est_value": "180000",
                            "city": "Virginia Beach"})
    with session_scope() as s:
        leads = s.query(Lead).all()
        subject, text, html = build_digest(leads)
        assert subject == "1 new construction lead"
        assert "/leads/" in text and "Addition" in html
    # No SMTP configured: nothing is sent, but the qualifying lead is counted.
    assert send_digest() == 1
