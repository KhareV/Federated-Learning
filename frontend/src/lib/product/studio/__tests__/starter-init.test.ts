// @vitest-environment jsdom
// Starting-model choice: the pretrained V2 (MODEL_V2_FINAL) is the default for BOTH run lengths; the untrained start stays an explicit choice and keeps the original 3-round form untouched.
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import StudioRunStarter from '$lib/components/product/studio/StudioRunStarter.svelte';
import type { StudioCapabilities } from '../types';

afterEach(() => cleanup());
const INITS = [{ id: 'FL_INIT_V2' as const, label: 'Untrained V2-architecture model (FL_INIT_V2) trained from scratch by federated rounds', default: false },
	{ id: 'MODEL_V2_FINAL' as const, label: 'Pretrained MODEL_V2_FINAL fine-tuned by federated rounds on the synthetic engineering-event task', default: true }];
const CAPS: StudioCapabilities = { studio_id: 'S', run_lengths: [3, 10], default_run_length: 3,
	ten_round: { available: true, initialisations: INITS, rounds_by_initialisation: { FL_INIT_V2: [10], MODEL_V2_FINAL: [3, 10] }, default_initialisation: 'MODEL_V2_FINAL', source_modes: ['CANONICAL_SYNTHETIC', 'LIVE_MONITORED_SITE_00'],
		algorithms: ['FEDAVG'], aggregation_modes: ['PLAIN'], unsupported: { FEDPROX: 'not implemented or verified by the extended engine', SECAGG_SHADOW: 'not implemented or verified by the extended engine' }, expected_updates: 80 },
	three_round: { available: true, expected_updates: 24 }, evaluation: { observer_id: 'O', protocol_id: 'P', threshold: 0.5, calibration: 'NONE', cohort_use: 'x', cohort_use_detail: 'd', claim_boundary: 'c' } };
const mount = (caps: StudioCapabilities | null = CAPS) => { const onStartThree = vi.fn(), onStartTen = vi.fn(); render(StudioRunStarter, { props: { capabilities: caps, onStartThree, onStartTen } }); return { onStartThree, onStartTen }; };

describe('starting model', () => {
	it('defaults to the pretrained V2 and offers the untrained start as an explicit choice', () => {
		mount();
		const select = screen.getByTestId('cfg10-init') as HTMLSelectElement;
		expect(select.value).toBe('MODEL_V2_FINAL');
		expect([...select.options].map((o) => o.value)).toEqual(['FL_INIT_V2', 'MODEL_V2_FINAL']);
		expect(screen.getByTestId('cfg10-init-note').textContent).toContain('R0 is the verified pretrained checkpoint');
	});
	it('3 rounds with the default (pretrained) start uses the extended form and sends run_length 3 with the initialisation', async () => {
		const { onStartThree, onStartTen } = mount();
		expect(screen.getByTestId('rounds-3').getAttribute('aria-checked')).toBe('true');
		expect(screen.queryByTestId('cfg-run-type')).toBeNull();                   // the original frozen form is NOT shown for the pretrained start
		expect(screen.getByTestId('cfg10-algorithm-note').textContent).toContain('FedProx is disabled');
		expect(screen.getByTestId('cfg10-submit').textContent).toContain('3-round');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL' });
		expect(onStartThree).not.toHaveBeenCalled();
	});
	it('choosing the untrained start restores the ORIGINAL 3-round form (FedAvg/FedProx, SecAgg shadow) unchanged', async () => {
		mount();
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'FL_INIT_V2' } });
		expect(screen.getByTestId('cfg-run-type')).toBeTruthy();
		expect(screen.queryByTestId('cfg10-submit')).toBeNull();
		expect(screen.getByTestId('cfg10-init-note').textContent).toContain('Original frozen 3-round contract');
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'MODEL_V2_FINAL' } });
		expect(screen.queryByTestId('cfg-run-type')).toBeNull();
	});
	it('10 rounds follows the same choice and carries it in the request', async () => {
		const { onStartTen } = mount();
		await fireEvent.click(screen.getByTestId('rounds-10'));
		expect((screen.getByTestId('cfg10-init') as HTMLSelectElement).value).toBe('MODEL_V2_FINAL');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL' });
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'FL_INIT_V2' } });
		expect(screen.getByTestId('cfg10-init-note').textContent).toContain('fresh untrained model');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'FL_INIT_V2' });
	});
	it('a backend that offers no starting-model choice keeps the original behaviour (original 3-round form, no initialisation in the request)', async () => {
		const legacy = { ...CAPS, ten_round: { ...CAPS.ten_round, initialisations: undefined, rounds_by_initialisation: undefined, default_initialisation: undefined } } as StudioCapabilities;
		const { onStartTen } = mount(legacy);
		expect(screen.queryByTestId('cfg10-init')).toBeNull();
		expect(screen.getByTestId('cfg-run-type')).toBeTruthy();
		await fireEvent.click(screen.getByTestId('rounds-10'));
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC' });
	});
	it('a backend that cannot run 3 rounds from the pretrained start says so and shows the original form instead of pretending', () => {
		const old = { ...CAPS, ten_round: { ...CAPS.ten_round, rounds_by_initialisation: { FL_INIT_V2: [10], MODEL_V2_FINAL: [10] } } } as StudioCapabilities;
		mount(old);
		expect(screen.getByTestId('v2-three-unsupported').textContent).toContain('not offered by the connected backend');
		expect(screen.getByTestId('cfg-run-type')).toBeTruthy();
	});
});
