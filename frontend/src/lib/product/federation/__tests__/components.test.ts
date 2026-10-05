// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { gotoMock } = vi.hoisted(() => ({ gotoMock: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => ({ goto: gotoMock, afterNavigate: () => {} }));
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/app/federation/live?run=FEDRUN-TEST01') } }));

import OverviewPage from '../../../../routes/app/federation/+page.svelte';
import ClientsPage from '../../../../routes/app/federation/clients/+page.svelte';
import RoundsPage from '../../../../routes/app/federation/rounds/+page.svelte';
import LivePage from '../../../../routes/app/federation/live/+page.svelte';
import PrivacyPage from '../../../../routes/app/federation/privacy/+page.svelte';
import ModelsPage from '../../../../routes/app/models/+page.svelte';
import CandidateCard from '$lib/components/product/federation/CandidateCard.svelte';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FederationStore, setFederationStore } from '../state.svelte';
import { FakeSocket, fakeBackend, resetSeq, systemInfo, type FakeBackend } from '../../__tests__/support';
import { CAND, RUN_ID, candidateFixture, eventStream, overviewFixture, registryFixture, runFixture } from './fixtures';

const immediate = (cb: () => void) => { cb(); return 0; };
let backend: FakeBackend;
let fed: FederationStore;

async function boot(system = systemInfo({ federation_runtime: 'ENABLED_ENGINEERING' })) {
	FakeSocket.reset(); resetSeq();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	backend = fakeBackend(system);
	const product = new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u));
	setProductStore(product);
	await product.init();
	fed = new FederationStore(() => backend, immediate, (u) => new FakeSocket(u));
	setFederationStore(fed);
}
beforeEach(async () => { gotoMock.mockClear(); await boot(); });
afterEach(() => { cleanup(); fed.closeLive(); setFederationStore(null); setProductStore(null); });
const text = () => document.body.textContent ?? '';

describe('federation overview + run configuration', () => {
	it('shows real overview values, two-lane architecture and exactly three user-controlled options', async () => {
		backend.fed.overview = overviewFixture({ candidate_count: 2 });
		render(OverviewPage);
		await waitFor(() => expect(text()).toContain('WEARABLE_SIM_FL_COHORT_V1'));
		expect(text()).toContain('ENGINEERING FEDERATION DEMO');
		expect(screen.getByTestId('architecture-lanes').textContent).toContain('Lane A · Released monitoring');
		expect(screen.getByTestId('architecture-lanes').textContent).toContain('MODEL_V2_FINAL');
		expect(screen.getByTestId('architecture-lanes').textContent).not.toContain('CAPSTONE_FL_CANDIDATE');
		expect(document.querySelectorAll('select')).toHaveLength(3);
		expect(document.querySelectorAll('input')).toHaveLength(0);
		const options = (id: string) => [...(screen.getByTestId(id) as HTMLSelectElement).options].map((o) => o.value);
		expect(options('cfg-run-type')).toEqual(['LIVE_RUN', 'REPLAY']);
		expect(options('cfg-algorithm')).toEqual(['FEDAVG', 'FEDPROX']);
		expect(options('cfg-mode')).toEqual(['PLAIN', 'SECAGG_SHADOW']);
		for (const fact of ['FL_SINGLE_RUN', 'FL_INIT_V2']) expect(text()).toContain(fact);
		expect(text()).not.toMatch(/learning rate|batch size|optimizer|\bmu\b|checkpoint|epoch/i);
	});
	it('cold start: the clients panel says PREPARING, requests once and shows no invented client state', async () => {
		backend.fed.clientsDelayMs = 50;
		render(OverviewPage);
		expect(screen.getByTestId('clients-preparing').textContent).toContain('PREPARING 8 SYNTHETIC LOCAL CLIENT DATASETS');
		await waitFor(() => expect(text()).toContain('8 logical clients ready'));
		expect(backend.calls.filter((c) => c === 'federationClients')).toHaveLength(1);
	});
	it('submitting sends exactly the chosen options and navigates to the live page', async () => {
		render(OverviewPage);
		await fireEvent.change(screen.getByTestId('cfg-mode'), { target: { value: 'SECAGG_SHADOW' } });
		await fireEvent.click(screen.getByTestId('cfg-submit'));
		await waitFor(() => expect(gotoMock).toHaveBeenCalledWith(`/app/federation/live?run=${RUN_ID}`));
		expect(backend.federationBodies[0]).toEqual({ run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'SECAGG_SHADOW', planned_rounds: 3, scenario_id: 'FL_SINGLE_RUN' });
	});
	it('an active LIVE run disables starting another LIVE run (REPLAY stays possible)', async () => {
		backend.fed.overview = overviewFixture({ active_live_run: true });
		render(OverviewPage);
		await waitFor(() => expect(text()).toContain('ONE LIVE FEDERATION RUN AT A TIME'));
		expect((screen.getByTestId('cfg-submit') as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.change(screen.getByTestId('cfg-run-type'), { target: { value: 'REPLAY' } });
		expect((screen.getByTestId('cfg-submit') as HTMLButtonElement).disabled).toBe(false);
		expect(text()).not.toMatch(/distributed lock/i);
	});
	it('replay without a source shows the exact message', async () => {
		const { ProductApiError } = await import('../../api');
		backend.fed.createError = new ProductApiError(409, 'INVALID_LIFECYCLE_STATE', 'INVALID_STATE', 'NO_COMPLETED_SOURCE_RUN_FOR_REPLAY');
		render(OverviewPage);
		await fireEvent.change(screen.getByTestId('cfg-run-type'), { target: { value: 'REPLAY' } });
		await fireEvent.click(screen.getByTestId('cfg-submit'));
		await waitFor(() => expect(screen.getByTestId('replay-no-source').textContent).toBe('NO COMPATIBLE LIVE RUN EXISTS YET. COMPLETE A LIVE RUN WITH THIS CONFIGURATION FIRST.'));
		expect(gotoMock).not.toHaveBeenCalled();
	});
});

describe('clients page', () => {
	it('shows the eight synthetic logical clients with the synthetic banner and no raw data or labels', async () => {
		render(ClientsPage);
		await waitFor(() => expect(screen.getByTestId('client-cards').children).toHaveLength(8));
		expect(screen.getByTestId('synthetic-banner').textContent).toContain('SYNTHETIC RESEARCH PARTITIONS');
		expect(text()).toContain('SIM_FL_SITE_00'); expect(text()).toContain('SIM_FL_SITE_07');
		expect(text()).toContain('All eight logical clients currently execute on one demonstration machine.');
		expect(text()).not.toMatch(/hospital(?!s or)|label|participant|SIM_P0/i);
	});
});

describe('live page', () => {
	async function liveWith(events: ReturnType<typeof eventStream>, run = runFixture({ run_id: RUN_ID })) {
		backend.fed.runs = [run];
		render(LivePage);
		await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
		FakeSocket.last.open();
		for (const e of events) FakeSocket.last.send(e);
	}
	it('renders a full SECAGG_SHADOW run from events only: PLAIN aggregate, shadow verified, 24 updates, candidate sandbox', async () => {
		await liveWith(eventStream({ mode: 'SECAGG_SHADOW' }), runFixture({ secagg_mode: 'SECAGG_SHADOW' }));
		await waitFor(() => expect(screen.getByTestId('run-status').textContent).toContain('COMPLETED'));
		expect(screen.getByTestId('update-ready-count').textContent).toBe('24');
		expect(screen.getByTestId('submitted-count').textContent).toBe('24');
		expect(screen.getByTestId('authoritative-aggregate').textContent).toContain('PLAIN');
		expect(screen.getByTestId('secagg-status').textContent).toContain('SHADOW_VERIFIED');
		expect(screen.getByTestId('candidate-live').textContent).toContain(CAND);
		expect(text()).toContain('ACCEPTED TO ENGINEERING SANDBOX REGISTRY');
		expect(screen.getByTestId('candidate-live').textContent).toContain('FALSE');
		expect(text()).not.toMatch(/promoted|deployed to|make default|accuracy|AUPRC|F1\b/i);
	});
	it('REPLAY: persistent no-training badge, historical candidate wording, no new candidate claim', async () => {
		await liveWith(eventStream({ runType: 'REPLAY' }), runFixture({ run_type: 'REPLAY' }));
		await waitFor(() => expect(screen.getByTestId('historical-candidate')).toBeTruthy());
		expect(screen.getByTestId('replay-badge').textContent).toContain('NO TRAINING IS EXECUTING');
		expect(screen.getByTestId('replay-note').textContent).toContain('NO TRAINING IS EXECUTING');
		expect(screen.getByTestId('historical-candidate').textContent).toContain('NO NEW CANDIDATE CREATED');
		expect(text()).not.toMatch(/training in progress|clients are computing/i);
	});
	it('PLAIN run reports SECAGG SHADOW: NOT USED', async () => {
		await liveWith(eventStream());
		await waitFor(() => expect(screen.getByTestId('secagg-status').textContent).toContain('NOT USED'));
	});
	it('a stream integrity failure shows FEDERATION STREAM ERROR', async () => {
		backend.fed.runs = [runFixture()];
		render(LivePage);
		await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
		FakeSocket.last.open();
		const evs = eventStream();
		FakeSocket.last.send(evs[0]); FakeSocket.last.send(evs[5]);
		await waitFor(() => expect(screen.getByTestId('stream-error').textContent).toContain('FEDERATION STREAM ERROR'));
	});
	it('a failed run shows the engineering error and no candidate', async () => {
		await liveWith(eventStream({ failAfterRound: 1 }));
		await waitFor(() => expect(text()).toContain('ERROR TEST_FAILURE'));
		expect(screen.queryByTestId('candidate-live')).toBeNull();
	});
});

describe('rounds, privacy and models pages', () => {
	it('rounds: persisted round cards, rounds 1-2 candidate NONE, final candidate, lineage without MODEL_V2_FINAL', async () => {
		backend.fed.runs = [runFixture({ candidate_ids: [CAND] })];
		render(RoundsPage);
		await waitFor(() => expect(screen.getByTestId('round-cards').children).toHaveLength(3));
		const cards = [...screen.getByTestId('round-cards').children].map((c) => c.textContent ?? '');
		expect(cards[0]).toContain('NONE'); expect(cards[1]).toContain('NONE'); expect(cards[2]).toContain(CAND);
		expect(cards.every((c) => c.includes('8 / 8'))).toBe(true);
		expect(screen.getByTestId('lineage').textContent).toContain('FL_INIT_V2');
		expect(screen.getByTestId('lineage').textContent).not.toContain('MODEL_V2_FINAL');
	});
	it('privacy: round-1-only shadow wording, plain authoritative aggregation, limitations, no DP/anonymity claim', async () => {
		backend.fed.runs = [runFixture({ secagg_mode: 'SECAGG_SHADOW' })];
		render(PrivacyPage);
		await waitFor(() => expect(text()).toContain('ROUND-1 PROTECTED-AGGREGATION SHADOW'));
		expect(text()).toContain('Authoritative aggregation remains PLAIN');
		expect(text()).toContain('No differential privacy.'); expect(text()).toContain('No anonymity guarantee.');
		expect(text()).not.toMatch(/SECURE FEDERATION|PRIVATE FEDERATION|ANONYMOUS TRAINING|HIPAA/i);
		await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
		FakeSocket.last.open();
		for (const e of eventStream({ mode: 'SECAGG_SHADOW' }).slice(0, 80)) FakeSocket.last.send(e);
		await waitFor(() => expect(screen.getByTestId('privacy-secagg').textContent).toContain('SHADOW_VERIFIED'));
	});
	it('models: two separated namespaces, MODEL_V2_FINAL RELEASED_DEFAULT, candidate production_deployed FALSE, no deploy/promote controls', async () => {
		backend.fed.registry = registryFixture([candidateFixture()]);
		render(ModelsPage);
		await waitFor(() => expect(screen.getByTestId('candidates').children).toHaveLength(1));
		expect(screen.getByTestId('released-models').textContent).toContain('MODEL_V2_FINAL');
		expect(screen.getByTestId('released-models').textContent).toContain('RELEASED_DEFAULT');
		expect(screen.getByTestId('released-models').textContent).not.toContain('CAPSTONE_FL_CANDIDATE');
		expect(screen.getByTestId('candidates').textContent).not.toContain('MODEL_V2_FINAL');
		expect(screen.getByTestId('production-deployed').textContent).toBe('FALSE');
		expect(screen.queryAllByRole('button').filter((b) => /deploy|promote|default|switch|inference/i.test(b.textContent ?? ''))).toEqual([]);
	});
	it('candidate card: rejected wording and per-check results only when reported', () => {
		render(CandidateCard, { candidate: candidateFixture({ governance_status: 'REJECTED', validation_status: 'FAILED', sandbox_status: 'NOT_IN_SANDBOX' }) });
		expect(screen.getByTestId('rejected-copy').textContent).toContain('REJECTED BY ENGINEERING GOVERNANCE');
		expect(text()).toContain('Per-check results are shown only when reported');
		expect(text()).toContain('engineering, not clinical or performance validation');
	});
});
