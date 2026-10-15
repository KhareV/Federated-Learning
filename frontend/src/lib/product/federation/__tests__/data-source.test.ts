// @vitest-environment jsdom
// One Live-page design for every run: only the data source differs (synthetic cohort vs. the user's recorded hardware windows).
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import ClientGrid from '$lib/components/product/federation/ClientGrid.svelte';
import FederationBanner from '$lib/components/product/federation/FederationBanner.svelte';
import { HARDWARE_CLIENT_IDS, SYNTHETIC_CLIENT_IDS, clientIdsFor, clientShortName, runDataSource } from '../data-source';

afterEach(cleanup);

describe('run data source', () => {
	it('is HARDWARE only for recorded-hardware runs', () => {
		expect(runDataSource('HDFLRUN-ABC')).toBe('HARDWARE');
		expect(runDataSource('x', 'HARDWARE_DEMO')).toBe('HARDWARE');
		expect(runDataSource('FL10RUN-ABC', 'FL10_10R')).toBe('SYNTHETIC');
		expect(runDataSource(null)).toBe('SYNTHETIC');
	});
	it('maps to the eight logical client ids of each source', () => {
		expect(clientIdsFor('SYNTHETIC')).toEqual(SYNTHETIC_CLIENT_IDS);
		expect(clientIdsFor('HARDWARE')).toEqual(HARDWARE_CLIENT_IDS);
		expect(clientShortName('RECORDED_DEMO_CLIENT_03')).toBe('Client 03');
		expect(clientShortName('SIM_FL_SITE_03')).toBe('Site 03');
	});
});

describe('the unchanged components render either source', () => {
	it('ClientGrid defaults to the synthetic cohort exactly as before', () => {
		render(ClientGrid, { props: { live: [], round: 1 } });
		expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual(SYNTHETIC_CLIENT_IDS.map((id) => `Show details for ${id}`));
		expect(screen.queryByTestId('hardware-card-label')).toBeNull();
	});
	it('ClientGrid shows the user\'s recorded windows for a hardware run, with no synthetic peers', () => {
		render(ClientGrid, { props: { live: [], round: 1, dataSource: 'HARDWARE' } });
		expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label'))).toEqual(HARDWARE_CLIENT_IDS.map((id) => `Show details for ${id}`));
		expect(screen.getAllByTestId('hardware-card-label')).toHaveLength(8);
		expect(screen.queryByTestId('peer-label')).toBeNull();
	});
	it('the claim strip names the data source and never calls hardware clients simulated', () => {
		render(FederationBanner, { props: { dataSource: 'HARDWARE' } });
		const text = screen.getByRole('note').textContent ?? '';
		expect(text).toContain('RECORDED HARDWARE DATA');
		expect(text).toContain('SYNTHETIC LABELS');
		expect(text).not.toContain('SIMULATED CLIENTS');
		cleanup();
		render(FederationBanner, { props: {} });
		expect(screen.getByRole('note').textContent).toContain('SIMULATED CLIENTS');
	});
});
