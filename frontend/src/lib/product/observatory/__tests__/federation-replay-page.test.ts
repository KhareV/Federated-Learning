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
