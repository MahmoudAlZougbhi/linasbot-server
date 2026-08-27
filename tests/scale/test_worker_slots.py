"""In-node claim slots follow desired replicas only when autoscale apply is on."""

from __future__ import annotations

from services.scale.replica_controller import set_controller_redis_for_tests
from services.scale.worker_slots import slot_count_for


def test_slots_stay_at_base_when_apply_off(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_AUTOSCALE_APPLY", raising=False)
    monkeypatch.setenv("LINAS_QUEUE_CONCURRENCY_HIGH", "8")
    from importlib import reload

    import services.queues.config as config
    import services.omnichannel.worker_pool as pool
    import services.scale.worker_slots as slots

    reload(config)
    reload(pool)
    reload(slots)
    assert slots.slot_count_for("high_priority") == 8


def test_slots_split_desired_across_nodes(monkeypatch) -> None:
    import fakeredis

    fake = fakeredis.FakeRedis(decode_responses=True)
    set_controller_redis_for_tests(fake)
    monkeypatch.setenv("LINAS_AUTOSCALE_APPLY", "true")
    monkeypatch.setenv("LINAS_CLUSTER_NODES", "2")
    monkeypatch.setenv("LINAS_QUEUE_CONCURRENCY_HIGH", "8")
    fake.set("linas:scale:desired:workers", "8")
    from importlib import reload

    import services.queues.config as config
    import services.omnichannel.worker_pool as pool
    import services.scale.worker_slots as slots

    reload(config)
    reload(pool)
    reload(slots)
    assert slots.slot_count_for("high_priority") == 4
    set_controller_redis_for_tests(None)
