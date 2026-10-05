"""Interactive-style demo of the simulated wearable attachment flow (no server, no UI).

    PYTHONPATH=src:. python scripts/run_capstone_device_demo.py [SCENARIO] [--live]

Prints the device lifecycle events and a record summary. ``--live`` paces to source time.
"""

from __future__ import annotations

import asyncio
import sys

from product.devices.scenarios import MONITORING_SCENARIO_IDS, TimingMode, load_scenarios
from product.devices.simulated import SimulatedWearableSource
from product.edge.virtual import VirtualEdgeNode, monitoring_edge_identity


async def main(scenario_id: str, mode: TimingMode) -> None:
    spec = load_scenarios()[scenario_id]
    source = SimulatedWearableSource(spec, mode=mode)
    node = VirtualEdgeNode(monitoring_edge_identity(source.descriptor.device_id), source)
    print(f"{node.identity.edge_node_id} <- {source.descriptor.display_name} "
          f"[SIMULATED, {scenario_id}, seed {spec.seed}, mode {mode.value}]")
    await node.start_live_monitoring(f"DEMO_{scenario_id}")
    count, last = 0, None
    async for record in node.live_records():
        count, last = count + 1, record
    async for event in node.live_events():
        print(f"  #{event.sequence_index:02d} {event.event_type.value:<18} -> "
              f"{event.device_state.value:<12} t_src={event.source_timestamp_us}")
    print(f"records delivered: {count}; last sample_index: {last.sample_index if last else None}"
          f"; final state: {source.connection_state.value}")
    print("engineering simulation only; not a physiological or hardware result")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    chosen = args[0] if args else "DISCONNECT_RECONNECT"
    if chosen not in MONITORING_SCENARIO_IDS:
        raise SystemExit(f"scenario must be one of {MONITORING_SCENARIO_IDS}")
    asyncio.run(main(chosen, TimingMode.LIVE_SPEED if "--live" in sys.argv else
                     TimingMode.ACCELERATED))
