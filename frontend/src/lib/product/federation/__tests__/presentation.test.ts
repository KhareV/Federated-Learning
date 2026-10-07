// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { FederationLiveModel } from '../live-model';
import { humanTimeline, localStepIndex, nodeState, roundCounts, stageProgress, stateTransitions, algorithmName, STAGE_LABELS } from '../presentation';
import ProcessStepper from '$lib/components/product/federation/ProcessStepper.svelte';
import RoundProgress from '$lib/components/product/federation/RoundProgress.svelte';
import FederationPipeline from '$lib/components/product/federation/FederationPipeline.svelte';
import LiveVsReplay from '$lib/components/product/federation/LiveVsReplay.svelte';
import ArchitectureLanes from '$lib/components/product/federation/ArchitectureLanes.svelte';
import { RUN_ID, eventStream } from './fixtures';

afterEach(cleanup);
function modelAfter(n?: number, o: Parameters<typeof eventStream>[0] = {}) {
	const m = new FederationLiveModel(RUN_ID);
	for (const e of eventStream(o).slice(0, n)) m.applyRaw(e);
	return m.snapshot;
}

describe('presentation derivations (only from reported state)', () => {
	it('empty view: every stage pending, no counts invented', () => {
		const v = new FederationLiveModel(null).snapshot;
		expect(stageProgress(v).every((s) => s.status === 'pending')).toBe(true);
		expect(humanTimeline(v)).toEqual([]);
		expect(stageProgress(v)).toHaveLength(STAGE_LABELS.length);
	});
	it('full stream: stages are done and counts equal reported events', () => {
		const v = modelAfter();
		expect(stageProgress(v).some((s) => s.status === 'failed')).toBe(false);
		expect(v.updateReadyCount).toBe(24);
		const c = roundCounts(v, 1);
		expect(c.total).toBe(8);
		expect(c.updatesReady).toBeLessThanOrEqual(8);
		expect(humanTimeline(v).length).toBeGreaterThan(0);
		expect(stateTransitions(v, null).length).toBe(v.rounds.length);
	});
	it('node state and local step tolerate unknown clients', () => {
		expect(nodeState(undefined, 1, false)).toBe('WAITING');
		expect(localStepIndex(undefined)).toBeLessThan(1);
	});
	it('algorithm names', () => { expect(algorithmName('FEDPROX')).toBe('FedProx'); expect(algorithmName(null)).toBe('--'); });
});

describe('new components', () => {
	it('pipeline shows all eight steps', () => {
		render(FederationPipeline);
		expect(screen.getByTestId('federation-pipeline').querySelectorAll('li').length).toBe(8);
	});
	it('stepper marks REPLAY without training claims', () => {
		render(ProcessStepper, { view: modelAfter(), replay: true });
		expect(screen.getByTestId('stepper-replay').textContent).toContain('NO TRAINING EXECUTING');
		expect(document.body.textContent).not.toMatch(/training in progress|clients are computing/i);
	});
	it('round progress renders reported counts', () => {
		render(RoundProgress, { view: modelAfter(), plannedRounds: 3 });
		expect(screen.getByTestId('round-progress').textContent).toMatch(/ROUND \d OF 3/);
		expect(document.body.textContent).not.toMatch(/accuracy|loss|%/i);
	});
	it('live vs replay lists both modes', () => {
		render(LiveVsReplay);
		expect(screen.getByTestId('live-vs-replay').textContent).toMatch(/LIVE RUN/);
		expect(screen.getByTestId('live-vs-replay').textContent).toMatch(/REPLAY/);
	});
	it('lanes keep promotion wall and never name the candidate as released', () => {
		render(ArchitectureLanes, { releasedModel: 'MODEL_V2_FINAL' });
		const t = screen.getByTestId('architecture-lanes').textContent ?? '';
		expect(t).toContain('NO AUTOMATIC PROMOTION');
		expect(t).toContain('MODEL_V2_FINAL');
		expect(t).not.toContain('CAPSTONE_FL_CANDIDATE');
	});
});
