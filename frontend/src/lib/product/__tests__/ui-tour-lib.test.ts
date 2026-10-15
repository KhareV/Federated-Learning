// @vitest-environment jsdom
// The browser audit's in-page metrics expression is a template string evaluated by Chrome; a syntax slip there silently voids a whole tour (it happened twice).
// The template is evaluated exactly as Node evaluates it, then EXECUTED against a small DOM so a runtime error cannot hide either.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const lib = readFileSync(path.resolve(__dirname, '../../../../../scripts/ui_tour_lib.mjs'), 'utf-8');
const metricsSource = (): string => {
	const m = /const METRICS = `([\s\S]*?)`;\n/.exec(lib);
	expect(m).not.toBeNull();
	return new Function(`return \`${(m as RegExpExecArray)[1]}\``)() as string;
};

describe('ui tour library', () => {
	it('the in-page METRICS expression parses once the template is evaluated', () => {
		expect(() => new Function(`return ${metricsSource()}`)).not.toThrow();
	});
	it('and runs against a DOM, returning every audit field', () => {
		Object.defineProperty(HTMLElement.prototype, 'innerText', { configurable: true, get() { return this.textContent; } });
		HTMLElement.prototype.getBoundingClientRect = () => ({ width: 10, height: 10, top: 0, left: 0, right: 10, bottom: 10, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
		document.body.innerHTML = '<main><h1>Title</h1><h3>Skipped level</h3><p>' + 'word '.repeat(60) + '</p><button></button><a href="#x">link</a></main>';
		const result = (0, eval)(metricsSource()) as Record<string, unknown>;
		for (const field of ['text', 'words', 'headingSkips', 'landmarks', 'horizontalOverflow', 'tinyTextElements', 'tinyBreakdown', 'longParagraphs', 'unnamedControls', 'unnamedSamples', 'h1Count', 'docHeight']) {
			expect(result, field).toHaveProperty(field);
		}
		expect(result.h1Count).toBe(1);
		expect(result.headingSkips).toBe(1);
	});
	it('records HTTP status, external hosts, failed requests and keyboard focus indicators', () => {
		for (const needle of ['httpStatus', 'externalHosts', 'keyboardProbe', 'failedRequests']) expect(lib).toContain(needle);
	});
});
