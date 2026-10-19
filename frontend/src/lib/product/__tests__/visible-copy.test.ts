// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { installVisibleCopy } from '../visible-copy';

afterEach(() => { document.body.replaceChildren(); });

describe('sitewide visible copy boundary', () => {
	it('updates initial and later API text without changing field values or identifiers', async () => {
		const root = document.createElement('main');
		const label = document.createElement('p');
		label.textContent = 'Synthetic cohort · virtual wearable · engineering sandbox';
		const button = document.createElement('button');
		button.setAttribute('aria-label', 'Open simulated source');
		button.dataset.testid = 'synthetic-control';
		const option = document.createElement('option');
		option.value = 'CANONICAL_SYNTHETIC';
		option.textContent = 'CANONICAL_SYNTHETIC';
		root.append(label, button, option);
		document.body.append(root);
		const stop = installVisibleCopy(root);
		expect(label.textContent).toBe('research cohort · software ECG source · research workspace');
		expect(button.getAttribute('aria-label')).toBe('Open software source');
		expect(button.dataset.testid).toBe('synthetic-control');
		expect(option.value).toBe('CANONICAL_SYNTHETIC');
		expect(option.textContent).toBe('Canonical research cohort');
		label.textContent = 'SIM_FL_SITE_03 uses simulated ECG';
		await new Promise((resolve) => setTimeout(resolve, 0));
		expect(label.textContent).toBe('Logical site 03 uses software-generated ECG');
		stop();
	});
});
