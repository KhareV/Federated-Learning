// @vitest-environment jsdom
// UFL-LITE-002: owner-bound FL PRESENTATION (CLERK + LIVE_RUN only). Presentation only: no FL, API or backend semantics.
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { gotoMock } = vi.hoisted(() => ({ gotoMock: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => ({ goto: gotoMock, afterNavigate: () => {} }));
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/app/federation/live?run=FEDRUN-TEST01') } }));

import ClientGrid from '$lib/components/product/federation/ClientGrid.svelte';
import ClientsPage from '../../../../routes/app/federation/clients/+page.svelte';
import LivePage from '../../../../routes/app/federation/live/+page.svelte';
import RoundsPage from '../../../../routes/app/federation/rounds/+page.svelte';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FederationStore, setFederationStore } from '../state.svelte';
import { CLIENT_LABEL } from '../labels';
import { OWNER_BOUND_CLIENT_ID, ownerBoundClientId, participationRole } from '../participation';
import type { ClientView } from '../live-model';
import { FakeSocket, fakeBackend, resetSeq, systemInfo, type FakeBackend } from '../../__tests__/support';
import { CLIENT_IDS, RUN_ID, eventStream, runFixture } from './fixtures';

const immediate = (cb: () => void) => { cb(); return 0; };
let backend: FakeBackend;
let fed: FederationStore;
const text = () => document.body.textContent ?? '';
const SRC = resolve(__dirname, '../../../..');

async function boot(provider: 'CLERK' | 'DEMO') {
	FakeSocket.reset(); resetSeq();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	backend = fakeBackend(systemInfo({ federation_runtime: 'ENABLED_ENGINEERING', auth_provider: provider, demo_mode: provider === 'DEMO' }));
	const auth = new FrontendAuth({ createClient: () => backend, loadClerk: async () => ({ session: null, load: async () => {}, mountSignIn: () => {}, unmountSignIn: () => {}, signOut: async () => {} }), publishableKey: 'pk_test_x' });
	const product = new ProductStore(auth, immediate, (u) => new FakeSocket(u));
	setProductStore(product);
	await product.init();
	fed = new FederationStore(() => backend, immediate, (u) => new FakeSocket(u));
	setFederationStore(fed);
}
afterEach(() => { cleanup(); fed?.closeLive(); setFederationStore(null); setProductStore(null); });

async function live(provider: 'CLERK' | 'DEMO', runType: 'LIVE_RUN' | 'REPLAY', site00Examples = 93) {
	await boot(provider);
	backend.fed.runs = [runFixture({ run_id: RUN_ID, run_type: runType })];
	render(LivePage);
	await waitFor(() => expect(FakeSocket.instances.length).toBe(1));
	FakeSocket.last.open();
	for (const e of eventStream({ runType })) {
		const p = e.payload as { client_id?: string; local_example_count?: number };
		FakeSocket.last.send(p.client_id === 'SIM_FL_SITE_00' && p.local_example_count !== undefined ? ({ ...e, payload: { ...p, local_example_count: site00Examples } } as typeof e) : e);
	}
	await waitFor(() => expect(screen.getByTestId('run-status').textContent).toContain('COMPLETED'));
}

describe('pure participation helper', () => {
	it('binds SIM_FL_SITE_00 for CLERK + LIVE_RUN', () => {
		expect(ownerBoundClientId('CLERK', 'LIVE_RUN')).toBe('SIM_FL_SITE_00');
		expect(OWNER_BOUND_CLIENT_ID).toBe('SIM_FL_SITE_00');
	});
	it('binds nothing for DEMO + LIVE_RUN, CLERK + REPLAY, DEMO + REPLAY or no run/auth', () => {
		expect(ownerBoundClientId('DEMO', 'LIVE_RUN')).toBeNull();
		expect(ownerBoundClientId('CLERK', 'REPLAY')).toBeNull();
		expect(ownerBoundClientId('DEMO', 'REPLAY')).toBeNull();
		expect(ownerBoundClientId('CLERK', null)).toBeNull();
		expect(ownerBoundClientId(null, 'LIVE_RUN')).toBeNull();
		expect(ownerBoundClientId(undefined, undefined)).toBeNull();
	});
	it('assigns exactly one AUTHENTICATED_OWNER and seven SYNTHETIC_PEER roles, and none when unbound', () => {
		const roles = CLIENT_IDS.map((id) => participationRole(id, 'SIM_FL_SITE_00'));
		expect(roles.filter((r) => r === 'AUTHENTICATED_OWNER')).toHaveLength(1);
		expect(roles.filter((r) => r === 'SYNTHETIC_PEER')).toHaveLength(7);
		expect(roles[0]).toBe('AUTHENTICATED_OWNER');
		expect(CLIENT_IDS.every((id) => participationRole(id, null) === null)).toBe(true);
	});
	it('takes no user identity, token, email or display name and has no network/storage/Svelte state', () => {
		const src = readFileSync(resolve(SRC, 'lib/product/federation/participation.ts'), 'utf8').replace(/\/\/.*$/gm, '');
		expect(ownerBoundClientId.length).toBe(2);
		expect(participationRole.length).toBe(2);
		expect(src).not.toMatch(/user_id|userId|email|display_?name|token|session|cookie|fetch\(|localStorage|sessionStorage|indexedDB|\$state|\$derived|svelte|document|window/i);
	});
});

describe('ClientGrid (display-only prop)', () => {
	const views: ClientView[] = CLIENT_IDS.map((id, i) => ({ clientId: id, state: 'SUBMITTED', localExamples: 90 + i, updateDigests: { 1: 'ab'.repeat(32) }, milestones: { 1: 1 }, reason: null }));
	it('unbound (no prop): the existing presentation with no owner or peer labels', () => {
		render(ClientGrid, { live: views, round: 1 });
		expect(screen.getByTestId('client-grid').getAttribute('aria-label')).toBe('Eight logical clients');
		expect(text()).not.toMatch(/MY EDGE CLIENT|SYNTHETIC PEER|AUTHENTICATED OWNER/);
		expect(CLIENT_IDS.every((id) => text().includes(id))).toBe(true);
	});
	it('bound: exactly one MY EDGE CLIENT card for SIM_FL_SITE_00 and seven SYNTHETIC PEER cards; technical ids unchanged', () => {
		render(ClientGrid, { live: views, round: 1, ownerBoundClientId: 'SIM_FL_SITE_00' });
		expect(screen.getAllByTestId('owner-card-label')).toHaveLength(1);
		expect(screen.getAllByTestId('peer-label')).toHaveLength(7);
		const owner = document.querySelector('[data-role="AUTHENTICATED_OWNER"]') as HTMLElement;
		expect(owner.getAttribute('data-client')).toBe('SIM_FL_SITE_00');
		expect(owner.textContent).toContain('SIM_FL_SITE_00');
		expect(owner.textContent).toContain('MY EDGE CLIENT');
		expect(owner.textContent).toContain('SYNTHETIC ENGINEERING');
		expect(owner.textContent).toContain('NOT YOUR PHYSIOLOGY');
		expect(owner.textContent).toContain('local examples: 90');
		expect([...document.querySelectorAll('[data-client]')].map((e) => e.getAttribute('data-client'))).toEqual(CLIENT_IDS);
		expect(document.querySelectorAll('[data-role="SYNTHETIC_PEER"]')).toHaveLength(7);
	});
});

describe('live page', () => {
	it('CLERK + LIVE_RUN: one owner card, seven peers, owner telemetry derived from the events, precise locality wording', async () => {
		await live('CLERK', 'LIVE_RUN', 93);
		expect(screen.getAllByTestId('owner-card-label')).toHaveLength(1);
		expect(screen.getAllByTestId('peer-label')).toHaveLength(7);
		expect(text().match(/MY EDGE CLIENT/g)?.length).toBeGreaterThanOrEqual(1);
		const card = document.querySelector('[data-client="SIM_FL_SITE_00"]') as HTMLElement;
		expect(card.textContent).toContain('local examples: 93');          // existing telemetry, not a constant
		expect(card.textContent).toContain(CLIENT_LABEL.SUBMITTED);         // state text comes from the existing CLIENT_LABEL map
		expect(card.getAttribute('data-state')).toBe('SUBMITTED');
		expect(card.textContent).toContain('milestone: 100% (completed)');
		expect(card.textContent).toMatch(/update: [0-9a-f]/);
		expect(screen.getByTestId('my-local-examples').textContent).toBe('93');
		expect(screen.getByTestId('my-completed-rounds').textContent).toBe('3 / 3');
		expect(screen.getByTestId('my-updates-produced').textContent).toBe('3 / 3');
		expect(screen.getByTestId('my-raw-examples-sent').textContent).toBe('0');
		expect(screen.getByTestId('my-participation').textContent).toContain("Training examples remain in this client's logical local buffer");
		expect(screen.getByTestId('my-participation').textContent).toContain('All clients execute on one demonstration machine');
		expect(screen.getByTestId('participants-note').textContent).toContain('1 authenticated owner-bound client · 7 synthetic peers');
		expect(screen.getByTestId('participants-note').textContent).toContain('ALL TRAINING DATA IN THIS DEMO IS SYNTHETIC ENGINEERING DATA');
		expect(text()).toContain('Federated participants');
		expect(text()).not.toMatch(/Eight logical clients/);
	});
	it('the owner example count follows the events (77 in, 77 shown) and the summary derives only from milestones and updateDigests', async () => {
		await live('CLERK', 'LIVE_RUN', 77);
		expect(screen.getByTestId('my-local-examples').textContent).toBe('77');
		const view = fed.view.clients.find((c) => c.clientId === 'SIM_FL_SITE_00')!;
		expect(Object.keys(view.updateDigests)).toHaveLength(3);
		expect(Object.values(view.milestones).filter((m) => m === 1)).toHaveLength(3);
	});
	it('CLERK + REPLAY and DEMO + LIVE_RUN / DEMO + REPLAY show no owner binding and keep the existing title', async () => {
		for (const [provider, runType] of [['CLERK', 'REPLAY'], ['DEMO', 'LIVE_RUN'], ['DEMO', 'REPLAY']] as const) {
			await live(provider, runType);
			expect(text(), `${provider}+${runType}`).not.toMatch(/MY EDGE CLIENT|AUTHENTICATED OWNER|SYNTHETIC PEER|MY FEDERATED PARTICIPATION/);
			expect(screen.queryByTestId('my-participation')).toBeNull();
			expect(text()).toContain('Eight logical clients');
			cleanup(); fed.closeLive(); setFederationStore(null); setProductStore(null);
		}
	});
	it('adds no contribution percentage, influence score, consent control or personal/personalized claim', async () => {
		await live('CLERK', 'LIVE_RUN');
		expect(text()).not.toMatch(/contribution|influence|importance score|% of the model|personal model|personalized|personalised|my ECG|my monitoring/i);
		expect(document.querySelectorAll('input, [role="switch"], [type="checkbox"]')).toHaveLength(0);
		expect(text()).not.toMatch(/opt[- ]in|consent|join federation/i);
		expect(text()).not.toMatch(/raw data never leaves your physical device/i);
	});
});

describe('global clients page and rounds page', () => {
	it('the GLOBAL clients view stays unbound even for a CLERK user', async () => {
		await boot('CLERK');
		render(ClientsPage);
		await waitFor(() => expect(CLIENT_IDS.every((id) => text().includes(id))).toBe(true));
		expect(text()).not.toMatch(/MY EDGE CLIENT|AUTHENTICATED OWNER|SYNTHETIC PEER|owner-bound/i);
		expect(readFileSync(resolve(SRC, 'routes/app/federation/clients/+page.svelte'), 'utf8')).not.toMatch(/MY EDGE CLIENT|ownerBound|participation/);
	});
	it('rounds page: a small owner note only for CLERK + LIVE_RUN', async () => {
		await boot('CLERK');
		backend.fed.runs = [runFixture({ run_type: 'LIVE_RUN' })];
		render(RoundsPage);
		await waitFor(() => expect(screen.getByTestId('rounds-owner-note').textContent).toContain('MY EDGE CLIENT: SIM_FL_SITE_00'));
		cleanup(); fed.closeLive(); setFederationStore(null); setProductStore(null);
		await boot('DEMO');
		backend.fed.runs = [runFixture({ run_type: 'LIVE_RUN' })];
		render(RoundsPage);
		await waitFor(() => expect(screen.getByTestId('round-cards').children).toHaveLength(3));
		expect(screen.queryByTestId('rounds-owner-note')).toBeNull();
	});
});

describe('source audit', () => {
	it('presentation files never read user identity and the server types are untouched', () => {
		for (const f of ['lib/components/product/federation/ClientGrid.svelte', 'routes/app/federation/live/+page.svelte', 'routes/app/federation/rounds/+page.svelte']) {
			const t = readFileSync(resolve(SRC, f), 'utf8');
			expect(t, f).not.toMatch(/identity\.|user_id|\.email|display_name|localStorage|sessionStorage|Clerk/);
		}
		const types = readFileSync(resolve(SRC, 'lib/product/federation/types.ts'), 'utf8');
		expect(types).not.toMatch(/participation_role|AUTHENTICATED_OWNER|SYNTHETIC_PEER/);
	});
});
