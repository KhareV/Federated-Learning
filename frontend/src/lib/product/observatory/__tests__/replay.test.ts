import { describe, expect, it } from 'vitest';
import { buildSnapshots } from '../replay.svelte';
import { RUN_ID, eventStream } from '../../federation/__tests__/fixtures';

describe('federation journal replay snapshots', () => {
	it('are independent per event so stepping back shows the earlier state', () => {
		const events = eventStream();
		const snaps = buildSnapshots(RUN_ID, events);
		expect(snaps).not.toBeNull();
		expect(snaps!.length).toBe(events.length);
		expect(snaps![0].updateReadyCount).toBe(0);
		expect(snaps![snaps!.length - 1].updateReadyCount).toBe(24);
		expect(snaps![0]).not.toBe(snaps![snaps!.length - 1]);
	});
	it('refuses a journal that fails integrity validation', () => {
		const events = eventStream();
		expect(buildSnapshots(RUN_ID, [events[0], events[2]])).toBeNull();
	});
});
