// @vitest-environment jsdom
// The upgrade shortlist panel: an evidence checklist per stored candidate. It ranks and explains; it never promotes, registers or deploys anything.
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import UpgradeShortlist from '$lib/components/product/studio/UpgradeShortlist.svelte';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FakeSocket, fakeBackend } from '../../__tests__/support';
import { parseUpgradeShortlist } from '../parse';

const immediate = (cb: () => void) => { cb(); return 0; };
const check = (id: string, status: string, detail = 'd') => ({ id, status, detail });
const entry = (over: Record<string, unknown>) => ({ candidate_id: 'C', label: 'ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL', cohort: 'REALISTIC', source_kind: 'SYNTHETIC_COHORT', run_length: 10, round_id: 10, rank: 1, tier: 'NOT_SHORTLISTED',
	failing: ['S4'], passing: ['S5'], not_evidenced: ['S1', 'S2', 'S3', 'S6', 'S7'], checks: [check('S1', 'NOT_EVIDENCED'), check('S4', 'FAIL', 'trained on a synthetic cohort'), check('S5', 'PASS')], promoted: false, deployed: false, ...over });
const RAW = (entries: unknown[]) => ({ policy_id: 'UPGRADE_SHORTLIST_POLICY_V1', criteria: [{ id: 'S1', title: 'Scored on real, unseen ECG', rule: 'r' }, { id: 'S4', title: 'Trained on real-ECG labels', rule: 'r' }],
	released_model: { model_id: 'MODEL_V2_FINAL', role: 'released monitoring model (unchanged)', real_ecg_auroc: 0.9109, ci95: [0.8956, 0.9259] }, external_check: 'reports/ptbxl/external_check_v1.json', entries, note: 'A shortlist is not an upgrade. Nothing here promotes, registers or deploys a model.' });

function install(payload: unknown) {
	FakeSocket.reset();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	const backend = Object.assign(fakeBackend(), { studioUpgradeShortlist: () => Promise.resolve(parseUpgradeShortlist(payload)) });
	setProductStore(new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u)));
}
afterEach(() => { cleanup(); setProductStore(null); });

describe('upgrade shortlist', () => {
	it('says a shortlist is not an upgrade, names the unchanged released model, and ranks candidates with the criteria that fail', async () => {
		install(RAW([entry({ candidate_id: 'RESEARCH_FL_V2_FL001_R50', cohort: 'REAL_ECG', rank: 1, tier: 'COMPARABLE_NOT_BETTER', failing: ['S3'], passing: ['S1', 'S2', 'S4', 'S5'] }), entry({ candidate_id: 'FL10_CANDIDATE_HDFLRUN-X', rank: 2 })]));
		render(UpgradeShortlist);
		await waitFor(() => expect(screen.getByTestId('shortlist-entries')).toBeTruthy());
		expect(screen.getByTestId('shortlist-boundary').textContent).toContain('NOT AN UPGRADE');
		expect(screen.getByTestId('shortlist-summary').textContent).toContain('0');
		expect(screen.getByTestId('shortlist-summary').textContent).toContain('MODEL_V2_FINAL');
		expect(screen.getByTestId('shortlist-summary').textContent).toContain('0.911');
		const tiers = screen.getAllByTestId('shortlist-tier').map((t) => t.textContent);
		expect(tiers).toEqual(['MATCHES THE RELEASED MODEL · NOT BETTER', 'NOT SHORTLISTED']);
		expect(screen.getAllByRole('listitem').some((li) => li.getAttribute('data-candidate') === 'FL10_CANDIDATE_HDFLRUN-X')).toBe(true);
		expect(screen.queryAllByRole('button')).toEqual([]);                                             // read-only: no control that could deploy or promote
	});
	it('pins promoted and deployed to false whatever the payload says', () => {
		expect(parseUpgradeShortlist(RAW([entry({ deployed: true })])).entries[0].deployed).toBe(false);
	});
	it('explains an empty library', async () => {
		install(RAW([]));
		render(UpgradeShortlist);
		await waitFor(() => expect(screen.getByTestId('shortlist-empty').textContent).toContain('nothing to rank'));
	});
});
