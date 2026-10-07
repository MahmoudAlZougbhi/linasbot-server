"""Owner Q&A answers a repeated question without calling the model."""

from services.owner_portal.owner_qa import match_owner_qa


def test_exact_question_returns_the_askers_language(monkeypatch):
    monkeypatch.setattr(
        "services.owner_portal.owner_qa.list_qa",
        lambda: [
            {
                "id": "q1",
                "variants": [
                    {"language": "en", "question": "How much is it?", "answer": "It is 20."},
                    {"language": "ar", "question": "كم السعر؟", "answer": "عشرون."},
                ],
            }
        ],
    )
    hit = match_owner_qa("كم السعر؟", "ar")
    assert hit is not None
    assert hit["hit"] == "exact"
    assert hit["answer"] == "عشرون."
    assert hit["score"] == 1.0
