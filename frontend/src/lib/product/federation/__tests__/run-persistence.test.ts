import { describe, expect, it, vi } from 'vitest';
const { goto } = vi.hoisted(() => ({ goto: vi.fn(async () => undefined) }));
vi.mock('$app/navigation', () => ({ goto }));
import { bootRun } from '$lib/components/product/federation/useRunParam';

const fake = (runId: string | null) => ({ loadRuns: vi.fn(async () => undefined), selectRun: vi.fn(async () => undefined), run: runId ? { run_id: runId } : null });

describe('selected-run persistence across run-scoped pages', () => {
	it('an explicit ?run= wins and does not rewrite the URL', async () => {
		const fed = fake('FL10RUN-OLD');
		await bootRun(fed as never, 'HDFLRUN-NEW', '/app/federation/rounds');
		expect(fed.selectRun).toHaveBeenCalledWith('HDFLRUN-NEW');
		expect(goto).not.toHaveBeenCalled();
	});
	it('without ?run= the run selected earlier in the session is re-attached and put in the URL', async () => {
		goto.mockClear();
		const fed = fake('HDFLRUN-ABC');
		await bootRun(fed as never, null, '/app/federation/privacy');
		expect(fed.selectRun).toHaveBeenCalledWith('HDFLRUN-ABC');
		expect(goto).toHaveBeenCalledWith('/app/federation/privacy?run=HDFLRUN-ABC', { replaceState: true, noScroll: true, keepFocus: true });
	});
	it('with nothing selected it stays on the empty "pick a run" state', async () => {
		goto.mockClear();
		const fed = fake(null);
		await bootRun(fed as never, null, '/app/federation/live');
		expect(fed.selectRun).not.toHaveBeenCalled();
		expect(goto).not.toHaveBeenCalled();
	});
});
