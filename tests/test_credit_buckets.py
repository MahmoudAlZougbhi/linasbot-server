from services.credit_buckets import split_credit_remaining


def test_spend_membership_before_purchased() -> None:
    split = split_credit_remaining(included=41300, purchased=12500, available=38200)
    assert split["credits_used"] == 15600
    assert split["membership_credits_remaining"] == 25700
    assert split["purchased_credits_remaining"] == 12500


def test_purchased_starts_after_included_is_gone() -> None:
    split = split_credit_remaining(included=41300, purchased=12500, available=3800)
    assert split["membership_credits_remaining"] == 0
    assert split["purchased_credits_remaining"] == 3800


def test_empty_balance() -> None:
    split = split_credit_remaining(included=7000, purchased=0, available=0)
    assert split["membership_credits_remaining"] == 0
    assert split["purchased_credits_remaining"] == 0
    assert split["credits_used"] == 7000


def test_leftover_above_allowance_counts_as_bought() -> None:
    split = split_credit_remaining(included=7000, purchased=0, available=9000)
    assert split["membership_credits_remaining"] == 7000
    assert split["purchased_credits_remaining"] == 2000
