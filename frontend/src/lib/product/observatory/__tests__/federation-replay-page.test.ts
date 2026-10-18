// @vitest-environment jsdom
// The journal of a finished run stays open on the server until every evaluation and export has settled (minutes later); replay must start at the terminal event,
// not wait for the socket to close (a long-idle socket was reported to the user as "disconnected before replay data was complete").
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Page from '../../../../routes/app/observatory/federation-replay/+page.svelte';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FakeSocket, fakeBackend } from '../../__tests__/support';
import { eventStream } from '../../federation/__tests__/fixtures';

const RUN = 'FL10RUN-TEST00000001';
const studioRun = { run_id: RUN, run_length: 3, engine: 'FL10_10R', origin: 'LIVE', run_type: 'LIVE_RUN', algorithm: 'FEDPROX', secagg_mode: 'PLAIN', source_mode: 'LIVE_MONITORED_SITE_00', monitored_site: 2, status: 'COMPLETED', planned_rounds: 3 };

class ClientSideSocket extends FakeSocket { sent: string[] = []; send(event: unknown): void { this.sent.push(String(event)); } }   // records what the BROWSER sends (the Clerk authenticate frame)
let store: ProductStore;
beforeEach(() => {
	FakeSocket.reset();
	vi.stubGlobal('WebSocket', ClientSideSocket);
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	const backend = Object.assign(fakeBackend(), { studioRuns: () => Promise.resolve([studioRun as never]) });
	store = new ProductStore(new FrontendAuth({ createClient: () => backend }), (cb: () => void) => { cb(); return 0; }, (u) => new FakeSocket(u));
	setProductStore(store);
});
afterEach(() => { cleanup(); setProductStore(null); vi.unstubAllGlobals(); });

describe('federation journal replay of a run whose journal is still open', () => {
	it('names the live-monitored site in the run list and starts replay at the terminal event without a socket close', async () => {
		store.authState = { ...store.authState, mode: 'CLERK' };
		vi.spyOn(store.auth, 'getSessionToken').mockResolvedValue('clerk-token');
		render(Page);
		await waitFor(() => expect([...(screen.getByRole('combobox') as HTMLSelectElement).options].some((o) => o.value === RUN)).toBe(true), { timeout: 5000 });
		expect((screen.getByRole('combobox') as HTMLSelectElement).textContent).toContain('LIVE-MONITORED SITE_02');
		await fireEvent.change(screen.getByRole('combobox'), { target: { value: RUN } });
		const socket = FakeSocket.last as ClientSideSocket;
		socket.open();
		await waitFor(() => expect(socket.sent.some((m) => m.includes('"authenticate"') && m.includes('clerk-token'))).toBe(true), { timeout: 5000 });   // owner-scoped journal: the Clerk token must be sent
		for (const event of eventStream({ run: RUN })) socket.onmessage?.({ data: JSON.stringify(event) });           // the terminal event arrives; the server keeps the socket open
		await waitFor(() => expect(screen.getByTestId('fed-replay-controls')).toBeTruthy(), { timeout: 5000 });
		expect(screen.queryByRole('alert')).toBeNull();
		expect(socket.closed).toBe(true);
	});
});

// The extended engine (10-round, pretrained 3-round, pretrained-V2 hardware) records its candidate in the run record, not as a journal event.
// The replay must not show "No candidate event yet" at the END of such a run; it shows the candidate from the run record there, and the pending note before.
const CANDIDATE = { candidate_id: 'FL10_CANDIDATE_X', state_sha256: 'ab'.repeat(32), promoted: false, deployed: false, label: 'ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL' };
async function replayOf(descriptor: Record<string, unknown>) {
	const run = { ...studioRun, ...descriptor, run_id: String(descriptor.run_id) };
	const backend = Object.assign(fakeBackend(), { studioRuns: () => Promise.resolve([run as never]) });
	store = new ProductStore(new FrontendAuth({ createClient: () => backend }), (cb: () => void) => { cb(); return 0; }, (u) => new FakeSocket(u));
	setProductStore(store);
	store.authState = { ...store.authState, mode: 'CLERK' };
	vi.spyOn(store.auth, 'getSessionToken').mockResolvedValue('clerk-token');
	render(Page);
	await waitFor(() => expect([...(screen.getByRole('combobox') as HTMLSelectElement).options].some((o) => o.value === run.run_id)).toBe(true), { timeout: 5000 });
	await fireEvent.change(screen.getByRole('combobox'), { target: { value: run.run_id } });
	const socket = FakeSocket.last as ClientSideSocket;
	socket.open();
	await waitFor(() => expect(socket.sent.some((m) => m.includes('"authenticate"'))).toBe(true), { timeout: 5000 });
	// the extended engine writes no candidate events and reports no candidate ids on completion: drop them from the fixture and renumber so the journal stays contiguous
	const journal = eventStream({ run: run.run_id }).filter((e) => !String(e.event_type).startsWith('candidate.')).map((e, i) => {
		const event = { ...e, sequence_index: i, event_id: `${run.run_id}-FEV${String(i).padStart(6, '0')}` } as typeof e & { payload: Record<string, unknown> };
		if (event.event_type === 'federation.completed') event.payload = { ...event.payload, candidate_ids: [] };
		return event;
	});
	for (const event of journal) socket.onmessage?.({ data: JSON.stringify(event) });
	await waitFor(() => expect(screen.getByTestId('fed-replay-controls')).toBeTruthy(), { timeout: 5000 });
}
const scrubTo = async (end: boolean) => { const slider = screen.getByRole('slider') as HTMLInputElement; await fireEvent.input(slider, { target: { value: end ? slider.max : '0' } }); };

describe('candidate panel of an extended-engine replay', () => {
	it('is pending at the start, then shows the candidate from the run record at the end and says where it comes from', async () => {
		await replayOf({ run_id: 'FL10RUN-CAND00000001', candidate: CANDIDATE, base_model: { model_id: 'MODEL_V2_FINAL' } });
		expect(screen.getByTestId('replay-candidate-pending')).toBeTruthy();                                   // replay starts at the first event: no candidate yet
		expect(screen.queryByTestId('candidate-summary')).toBeNull();                                          // never revealed before the final round
		await scrubTo(true);
		await waitFor(() => expect(screen.getByTestId('candidate-id').textContent).toBe('FL10_CANDIDATE_X'));
		expect(screen.getByTestId('replay-candidate-from-record').textContent).toContain('journal has no candidate event');
		expect(screen.queryByText(/No candidate event yet/)).toBeNull();
		await scrubTo(false);
		await waitFor(() => expect(screen.getByTestId('replay-candidate-pending')).toBeTruthy());
	});
	it('"Jump to candidate" goes to the end of such a run, where its candidate is shown', async () => {
		await replayOf({ run_id: 'FL10RUN-CAND00000004', candidate: CANDIDATE, base_model: { model_id: 'MODEL_V2_FINAL' } });
		await fireEvent.click(screen.getByText('Jump to candidate'));
		await waitFor(() => expect(screen.getByTestId('candidate-summary')).toBeTruthy());
	});
	it('a pretrained-V2 recorded-hardware run is treated the same way', async () => {
		await replayOf({ run_id: 'HDFLRUN-CAND00000002', engine: 'HARDWARE_DEMO', source_mode: 'RECORDED_HARDWARE', candidate: CANDIDATE, base_model: { model_id: 'MODEL_V2_FINAL' } });
		await scrubTo(true);
		await waitFor(() => expect(screen.getByTestId('candidate-summary')).toBeTruthy());
	});
	it('a tabular recorded-hardware run has no candidate, so the journal lifecycle (and its honest "no candidate") stays', async () => {
		await replayOf({ run_id: 'HDFLRUN-TAB000000003', engine: 'HARDWARE_DEMO', source_mode: 'RECORDED_HARDWARE', candidate: null, base_model: { model_id: 'HARDWARE_DEMO_MODEL_V1' } });
		expect(screen.queryByTestId('candidate-summary')).toBeNull();
		expect(screen.getByTestId('candidate-lifecycle')).toBeTruthy();
	});
});
