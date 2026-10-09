from scripts.ops.cleanup_linas_qa_leftovers import PRODUCT_IDS, keep_product, plan


def test_only_labelled_products_match() -> None:
    assert len(PRODUCT_IDS) == 39
    rows = [
        {"id": next(iter(PRODUCT_IDS)), "name": "QA-LINAS-APP-P01"},
        {"id": next(iter(PRODUCT_IDS)), "name": "Real serum"},
        {"id": "not-listed", "name": "QA-LINAS-APP-P99"},
    ]
    assert plan(rows)["matched"] == 1
    assert keep_product("not-listed", "QA-LINAS-APP-P99") is False
