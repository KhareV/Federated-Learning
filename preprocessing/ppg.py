"""Canonical PPG causal filtering at the canonical 100-Hz rate.

Owns: the PPG filter identity (PREPROC_V1_PPG_FILTER_V1, StatefulPPGFilter) and independent
red/IR channel state. Does not resample (BIDMC's 125 Hz PLETH source is out of T012 scope --
no unrequested 125->100 resampling freeze is introduced here), and does not derive SpO2,
pulse rate, PPG quality, or any cross-modal/multimodal consistency signal -- those are later
tasks. Red and IR values are never mixed into one filter instance.
"""

from __future__ import annotations

from typing import Any

from preprocessing.filters import FilterSpec, StatefulSOSFilter, load_filter_spec

PPG_FILTER_ID = "PREPROC_V1_PPG_FILTER_V1"

CHANNEL_RED = "RED"
CHANNEL_IR = "IR"


class StatefulPPGFilter(StatefulSOSFilter):
    """Thin identity-bound wrapper: always PREPROC_V1_PPG_FILTER_V1 (0.5-8 Hz, fs=100 Hz,
    4th-order Butterworth bandpass, SOS)."""

    def __init__(self, spec: FilterSpec | None = None) -> None:
        super().__init__(spec or load_filter_spec(PPG_FILTER_ID))
        if self.spec.filter_id != PPG_FILTER_ID:
            raise ValueError(
                f"StatefulPPGFilter requires {PPG_FILTER_ID}, got {self.spec.filter_id}"
            )


class DualChannelPPGFilter:
    """Independent StatefulPPGFilter instances for the red and infrared channels -- never
    combined into one filter or one SOS state. Each channel supports the same chunked
    process()/reset() contract as the underlying StatefulSOSFilter."""

    def __init__(self, spec: FilterSpec | None = None) -> None:
        shared_spec = spec or load_filter_spec(PPG_FILTER_ID)
        self.channels = {
            CHANNEL_RED: StatefulPPGFilter(shared_spec),
            CHANNEL_IR: StatefulPPGFilter(shared_spec),
        }

    def process(self, channel: str, samples: Any) -> Any:
        if channel not in self.channels:
            raise ValueError(f"unknown PPG channel {channel!r}; expected RED or IR")
        return self.channels[channel].process(samples)

    def reset(self, *, segment_id: int | None = None) -> None:
        for filter_instance in self.channels.values():
            filter_instance.reset(segment_id=segment_id)

    def state_metadata(self) -> dict[str, dict[str, Any]]:
        return {
            channel: filter_instance.state_metadata()
            for channel, filter_instance in self.channels.items()
        }
