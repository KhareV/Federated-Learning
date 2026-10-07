// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import ComparisonPanel from '$lib/components/product/story/ComparisonPanel.svelte';
import FlowDiagram from '$lib/components/product/story/FlowDiagram.svelte';
import QuestionCard from '$lib/components/product/story/QuestionCard.svelte';

afterEach(cleanup);

const route = (name: string) => readFileSync(
	path.join(process.cwd(), 'src', 'routes', 'app', name, '+page.svelte'),
	'utf8'
);

describe('UI-ENH-002 presentation boundary', () => {
	it('comparison keeps both roles explicit and does not invent a winner', () => {
		render(ComparisonPanel, {
			leftTitle: 'MODEL_V2_FINAL', rightTitle: 'ENGINEERING CANDIDATE',
			leftStatus: 'RELEASED', rightStatus: 'NOT DEPLOYED',
			rows: [{ label: 'Monitoring use', left: 'YES', right: 'NO' }],
			testid: 'comparison'
		});
		const panel = screen.getByTestId('comparison');
		expect(panel.textContent).toContain('MODEL_V2_FINAL');
		expect(panel.textContent).toContain('NOT DEPLOYED');
		expect(panel.textContent).toContain('Monitoring use');
		expect(panel.textContent).not.toMatch(/winner|candidate accuracy|candidate AUPRC/i);
	});

	it('flow diagram is an ordered, text-labelled explanation', () => {
		render(FlowDiagram, { label: 'Two-stage path', steps: [
			{ label: 'SIMULATED SOURCE', status: 'done' },
			{ label: 'SERVER-SIDE MODEL', status: 'pending' }
		] });
		const flow = screen.getByRole('list', { name: 'Two-stage path' });
		expect(flow.tagName).toBe('OL');
		expect(flow.textContent).toContain('SIMULATED SOURCE');
		expect(flow.textContent).toContain('SERVER-SIDE MODEL');
	});

	it('research decision card keeps the negative answer visible', () => {
		render(QuestionCard, {
			n: '1', question: 'Was the original model criterion met?',
			answer: 'NO · NOT PROMOTED', tone: 'no', reason: 'The frozen paired interval crossed zero.'
		});
		expect(screen.getByText('NO · NOT PROMOTED')).toBeTruthy();
		expect(screen.getByText('The frozen paired interval crossed zero.')).toBeTruthy();
	});

	it('route copy separates scientific evidence from the product engineering demo', () => {
		const fl = route('research/fl');
		expect(fl).toContain('SCIENTIFIC FL EXPERIMENTS');
		expect(fl).toContain('CURRENT PRODUCT ENGINEERING DEMO');
		expect(fl).toContain('No synthetic demo accuracy');
		expect(fl).toContain('NOT promoted as a generally superior method');
		expect(fl).not.toMatch(/candidate (?:AUPRC|AUROC|accuracy|F1)/i);
	});

	it('model and monitoring copy do not promote the sandbox candidate', () => {
		const models = route('models');
		const monitoring = route('monitoring');
		expect(models).toContain('No candidate performance');
		expect(models).toContain('No inference runtime');
		expect(models).toContain('NOT DEPLOYED');
		expect(monitoring).toContain('SIGNAL QUALITY (is the signal usable?) is not the same thing as MONITORING STATE');
		expect(monitoring).toContain('The browser only displays what the backend sends.');
	});
});
