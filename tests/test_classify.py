import pytest

from leadengine.classify import classify, is_contractor_listed


@pytest.mark.parametrize("text,expected", [
    ("Construct new single family dwelling with attached garage", "new_construction"),
    ("New 2-story SFD", "new_construction"),
    ("Build 12x16 deck on rear of dwelling", "deck"),
    ("Screened porch over existing patio", "deck"),
    ("Construct 24x30 detached garage", "garage_framing"),
    ("Second story addition over existing", "addition"),
    ("Sunroom addition 14x16 on existing slab", "addition"),
    ("Kitchen and bath remodel", "kitchen"),
    ("Primary bathroom remodel - new shower, vanity, tile", "bath"),
    ("Repair rotten floor joists and sister rafters", "house_framing"),
    ("Interior renovation of dwelling", "remodel"),
])
def test_positive_job_types(text, expected):
    c = classify(kind="permit", title=text)
    assert c.relevant
    assert c.job_type == expected


@pytest.mark.parametrize("text,permit_type", [
    ("Replace garage door", None),
    ("Reroof with architectural shingles", None),
    ("200A service upgrade", "Electrical"),
    ("HVAC changeout", "Residential Mechanical"),
    ("In-ground swimming pool", None),
    ("6ft privacy fence", None),
    ("Janitorial services", None),
])
def test_noise_is_dropped(text, permit_type):
    assert not classify(kind="permit", title=text, permit_type=permit_type).relevant


def test_trade_permit_still_counts_when_description_names_our_work():
    c = classify(kind="permit", title="Kitchen remodel - new circuits", permit_type="Electrical")
    assert c.job_type == "kitchen"


def test_structured_permit_fields_detect_new_home():
    c = classify(kind="permit", title="Permit", permit_type="Building / New", hints=["Single Family Dwelling"])
    assert c.job_type == "new_construction"
    assert c.customer_type == "builder"


def test_customer_types():
    assert classify(kind="permit", title="deck", contractor_name="Owner").customer_type == "homeowner"
    assert classify(kind="permit", title="deck", contractor_name="ABC Decks LLC").customer_type == "builder"
    assert classify(kind="bid", title="Deck replacement").customer_type == "public"
    assert classify(kind="request", title="need a deck built").customer_type == "homeowner"
    assert classify(kind="permit", title="Interior alterations to retail tenant space").customer_type == "builder"


def test_contractor_listed():
    assert not is_contractor_listed(None)
    assert not is_contractor_listed("OWNER")
    assert not is_contractor_listed("Homeowner")
    assert is_contractor_listed("Smith Framing Inc")


def test_fields_do_not_bleed_into_each_other():
    # "New" work type + "Residential" use type must not read as "new residential".
    c = classify(kind="permit", title="Building Residential · New — 1214 W Little Creek Rd",
                 description="Construct 24x30 detached garage", permit_type="Building Residential / New",
                 hints=["Residential", "New"])
    assert c.job_type == "garage_framing"


def test_deck_filed_as_generic_addition_is_a_deck():
    c = classify(kind="permit", title="Building · Addition — 733 Graydon Ave", permit_type="Building / Addition",
                 hints=["Deck", "Residential", "Addition"])
    assert c.job_type == "deck"
