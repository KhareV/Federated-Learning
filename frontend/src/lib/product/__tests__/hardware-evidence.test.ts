// @vitest-environment jsdom
// The hardware evidence page says WHY nothing was scored, instead of a bare "Unavailable".
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import HardwareEvidence from '$lib/components/product/HardwareEvidence.svelte';
import type { HardwareSession } from '../api';
import { FrontendAuth } from '../auth';
import { ProductStore, setProductStore } from '../state.svelte';
import { FakeSocket, fakeBackend } from './support';
import { parseHardwareTimeline } from '../history/types';

const BOUNDARY = 'RECORDED_HARDWARE_RESAMPLED_EXPERIMENTAL_DERIVED_TIMELINE_NOT_VALID_NOT_DIAGNOSTIC';
const immediate = (cb: () => void) => { cb(); return 0; };
const session = { session_id: 'HW-REC-2026-10-13-01-x', status: 'STOPPED', record_count: 53, readings: Array.from({ length: 53 }, (_, i) => ({ ordinal: i + 1, id: `d${i}`, ingested_at: '2026-10-13T09:00:00Z', ecg: 2048, bpm: 74, spo2: 92, collection: 'c' })) } as unknown as HardwareSession;
const timeline = (over: Record<string, unknown>) => parseHardwareTimeline({
	session_id: 'HW-1', timeline_version: 'CAPSTONE_SESSION_TIMELINE_V1', device_lifecycle: [], waveform_previews: [], time_domains: { source_timeline: 'SOURCE_TIMELINE', device_lifecycle: 'PRODUCT_CLOCK' },
	time_domain_explanation: 'x', claim_boundary: BOUNDARY, label: 'EXPERIMENTAL', source_kind: 'RECORDED_HARDWARE_RESAMPLED', assumptions: {}, source_timeline: [], complete: true,
	windows_total: 6, windows_scored: 0, windows_pending: 0, windows_unusable: 6, unusable_reasons: { LONG_GAP_SPAN: 6, FLATLINE: 4, CLIPPING: 2 }, ...over });

let answer: ReturnType<typeof timeline>;
beforeEach(() => {
	FakeSocket.reset();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	const backend = Object.assign(fakeBackend(), { hardwareSessionTimeline: () => Promise.resolve(answer) });
	setProductStore(new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u)));
});
afterEach(() => { cleanup(); setProductStore(null); });

describe('hardware session evidence when the quality gate rejects windows', () => {
	it('explains that no window reached the model, with the reasons, instead of a bare Unavailable', async () => {
		answer = timeline({});
		render(HardwareEvidence, { props: { session } });
		const note = await screen.findByTestId('hardware-evidence-none-scored');
		expect(note.textContent).toContain('No window reached the model');
		expect(note.textContent).toContain('0 of 6');
		expect(note.textContent).toContain('long gap (no readings for over 1 s) ×6');
		expect(note.textContent).toContain('flatline ×4');
		expect(note.textContent).toContain('clipping (at the ADC rail) ×2');
		expect(screen.getByTestId('hardware-evidence-summary').textContent).not.toContain('Unavailable');
	});
	it('lists the rejection reasons without the big notice when some windows were scored', async () => {
		answer = timeline({ windows_total: 57, windows_scored: 49, windows_unusable: 8, unusable_reasons: { CLIPPING: 8 } });
		render(HardwareEvidence, { props: { session } });
		await waitFor(() => expect(screen.getByTestId('hardware-evidence-rejected').textContent).toContain('8 of 57 windows were rejected by the quality gate: clipping (at the ADC rail) ×8'));
		expect(screen.getByTestId('hardware-evidence-rejected').textContent).toContain('accepts complete windows of any grade as experimental training data; they are never counted as VALID');
		expect(screen.queryByTestId('hardware-evidence-none-scored')).toBeNull();
	});
});
