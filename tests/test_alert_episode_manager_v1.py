from __future__ import annotations

from fusion.episode_manager import AlertEpisodeManager, load_alert_policy
from tests.test_fusion_state_machine_v1 import observation


def machine() -> AlertEpisodeManager:
    return AlertEpisodeManager(load_alert_policy())


def test_k2_open_and_no_duplicate_open() -> None:
    manager = machine()
    low = manager.policy.threshold - 0.1
    high = manager.policy.threshold + 0.1
    decisions = [
        manager.process(observation(0, low)),
        manager.process(observation(5_000_000, high)),
        manager.process(observation(10_000_000, high)),
        manager.process(observation(15_000_000, high)),
        manager.process(observation(20_000_000, high)),
    ]
    assert decisions[0].episode_active is False
    assert decisions[1].open_counter == 1
    assert decisions[2].episode_opened is True
    assert decisions[2].episode_count == 1
    assert all(item.episode_count == 1 for item in decisions[2:])
    assert not any(item.episode_opened for item in decisions[3:])


def test_interrupted_open_sequences_restart() -> None:
    for interruption in (("VALID", False), ("DEGRADED", True), ("UNUSABLE", True)):
        manager = machine()
        high = manager.policy.threshold + 0.1
        low = manager.policy.threshold - 0.1
        manager.process(observation(0, high))
        quality, use_high = interruption
        middle = manager.process(
            observation(5_000_000, high if use_high else low, ecg_quality=quality)
        )
        final = manager.process(observation(10_000_000, high))
        assert middle.episode_opened is False
        assert final.episode_opened is False
        assert final.open_counter == 1


def _open(manager: AlertEpisodeManager) -> None:
    high = manager.policy.threshold + 0.1
    manager.process(observation(0, high))
    assert manager.process(observation(5_000_000, high)).episode_opened


def test_m2_close_and_interrupted_close() -> None:
    manager = machine()
    _open(manager)
    low = manager.policy.threshold - 0.1
    high = manager.policy.threshold + 0.1
    first = manager.process(observation(10_000_000, low))
    interrupted = manager.process(observation(15_000_000, high))
    again = manager.process(observation(20_000_000, low))
    closed = manager.process(observation(25_000_000, low))
    assert first.close_counter == 1
    assert interrupted.close_counter == 0
    assert again.close_counter == 1
    assert closed.episode_closed is True
    assert closed.episode_active is False
    assert closed.cooldown_until_us == 55_000_000


def test_active_episode_survives_degraded_and_unusable() -> None:
    manager = machine()
    _open(manager)
    high = manager.policy.threshold + 0.1
    low = manager.policy.threshold - 0.1
    degraded_above = manager.process(observation(10_000_000, high, ecg_quality="DEGRADED"))
    degraded_below = manager.process(observation(15_000_000, low, ecg_quality="DEGRADED"))
    unusable = manager.process(observation(20_000_000, low, ecg_quality="UNUSABLE"))
    first_below = manager.process(observation(25_000_000, low))
    second_below = manager.process(observation(30_000_000, low))
    assert degraded_above.monitoring_state == "RECHECK_SENSOR"
    assert degraded_above.possible_pattern is True
    assert degraded_above.episode_active is True
    assert degraded_below.episode_active is True and degraded_below.close_counter == 0
    assert unusable.monitoring_state == "RECHECK_SENSOR"
    assert unusable.episode_active is True and unusable.close_counter == 0
    assert first_below.episode_active is True and first_below.close_counter == 1
    assert second_below.episode_closed is True


def test_cooldown_exact_boundary_and_fresh_k2() -> None:
    manager = machine()
    _open(manager)
    low = manager.policy.threshold - 0.1
    high = manager.policy.threshold + 0.1
    manager.process(observation(10_000_000, low))
    closed = manager.process(observation(100_000_000, low))
    assert closed.cooldown_until_us == 130_000_000
    before = manager.process(observation(129_999_999, high))
    expiry = manager.process(observation(130_000_000, high))
    reopened = manager.process(observation(135_000_000, high))
    assert before.cooldown_active is True and before.open_counter == 0
    assert expiry.cooldown_active is False and expiry.open_counter == 1
    assert reopened.episode_opened is True and reopened.episode_count == 2


def test_session_reset_clears_all_temporal_state() -> None:
    manager = machine()
    high = manager.policy.threshold + 0.1
    assert manager.process(observation(0, high, session_id="A")).open_counter == 1
    manager.reset("B")
    first_b = manager.process(observation(0, high, session_id="B"))
    assert first_b.open_counter == 1
    assert first_b.episode_active is False
    assert first_b.episode_count == 0


def test_scripted_replay_is_deterministic() -> None:
    def replay() -> list[object]:
        manager = machine()
        high = manager.policy.threshold + 0.1
        low = manager.policy.threshold - 0.1
        return [
            manager.process(observation(index * 5_000_000, probability))
            for index, probability in enumerate((low, high, high, high, low, low, high))
        ]

    assert replay() == replay()
