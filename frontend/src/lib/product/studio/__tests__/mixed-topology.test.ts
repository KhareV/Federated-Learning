// @vitest-environment jsdom
// A pretrained-V2 hardware run is ONE recorded client + seven synthetic peers: only the recorded client may claim YOUR RECORDED WINDOWS.
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import ClientGrid from '$lib/components/product/federation/ClientGrid.svelte';
import ClientDetailPanel from '$lib/components/product/federation/ClientDetailPanel.svelte';
import { clientIdsOfRun, isRecordedClient } from '$lib/product/federation/data-source';

const MIXED = ['RECORDED_DEMO_CLIENT_00', ...Array.from({ length: 7 }, (_, i) => `SIM_FL_SITE_0${i + 1}`)];
afterEach(cleanup);

describe('mixed recorded + synthetic topology', () => {
	it('uses the run\'s own client ids and falls back to the namespace default', () => {
		expect(clientIdsOfRun('HARDWARE', MIXED)).toEqual(MIXED);
		expect(clientIdsOfRun('HARDWARE', null)).toHaveLength(8);
		expect(clientIdsOfRun('HARDWARE', null).every(isRecordedClient)).toBe(true);
		expect(clientIdsOfRun('SYNTHETIC', ['x'])).toHaveLength(8);       // a malformed list is never trusted
	});
	it('tags only the recorded client as yours and the seven others as synthetic peers', () => {
		render(ClientGrid, { props: { live: [], dataSource: 'HARDWARE', clientIds: MIXED } });
		expect(screen.getAllByTestId('hardware-card-label')).toHaveLength(1);
		expect(screen.getAllByTestId('hardware-peer-label')).toHaveLength(7);
		const ids = [...document.querySelectorAll('[data-testid="client-grid"] li')].map((x) => x.getAttribute('data-client'));
		expect(ids).toEqual(MIXED);
	});
	it('a pure recorded-hardware run (eight recorded blocks) still tags all eight as yours', () => {
		render(ClientGrid, { props: { live: [], dataSource: 'HARDWARE' } });
		expect(screen.getAllByTestId('hardware-card-label')).toHaveLength(8);
		expect(screen.queryAllByTestId('hardware-peer-label')).toHaveLength(0);
	});
	it('the client detail names a peer as synthetic even inside a hardware run', () => {
		render(ClientDetailPanel, { props: { clientId: 'SIM_FL_SITE_03', client: undefined, dataSource: 'HARDWARE' } });
		expect(screen.getByTestId('client-detail').textContent).toContain('LOGICAL CLIENT');
		expect(screen.getByTestId('client-detail').textContent).not.toContain('YOUR RECORDED WINDOWS');
		cleanup();
		render(ClientDetailPanel, { props: { clientId: 'RECORDED_DEMO_CLIENT_00', client: undefined, dataSource: 'HARDWARE' } });
		expect(screen.getByTestId('client-detail').textContent).toContain('YOUR RECORDED WINDOWS');
	});
});
