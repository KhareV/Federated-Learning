import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

// Section 30/49: active, rendered frontend source must not contain unsupported legacy claims.
// Scans every .svelte/.ts file under src/ (excluding tests themselves, which legitimately name
// these strings as UI_TEST_FIXTURE / prohibited-wording constants).

const SRC_ROOT = path.resolve(__dirname, '../../../');

const NEGATION_WINDOW = 24;
const NEGATION_MARKERS = ['no ', 'not ', 'never ', "isn't ", 'is not '];

const PROHIBITED_PATTERNS: { label: string; pattern: RegExp; allowNegated?: boolean }[] = [
	{ label: '24-bit ADC claim', pattern: /24-bit/i },
	{ label: '360 Hz sampling claim', pattern: /360\s?hz/i },
	{ label: 'PTB-XL as current project data', pattern: /ptb-?xl/i },
	{ label: 'medical-grade claim', pattern: /medical[- ]grade/i, allowNegated: true },
	{ label: 'clinical-grade claim', pattern: /clinical[- ]grade/i, allowNegated: true },
	{ label: '"arrhythmia detected" claim', pattern: /arrhythmia detected/i },
	{ label: '"disease risk" claim', pattern: /disease risk/i },
	{ label: '"patient is abnormal" claim', pattern: /patient is abnormal/i }
];

// The canonical prohibited-phrase registry necessarily names the phrases it bans -- it is not
// rendered UI copy, so it is the scan's input vocabulary, not a scan target.
const EXCLUDED_RELATIVE_PATHS = new Set(['lib/dashboard/state-presentation.ts']);

// CAP-005: the product monitor renders the SIMULATED device-source ECG transport (360 Hz,
// ADC_COUNTS). The "360 Hz" pattern above guards against an unsupported HARDWARE sampling claim; these
// three product files legitimately name the simulated source rate. Each occurrence there must be
// qualified as simulated -- enforced by lib/product/__tests__/claims-and-copy.test.ts.
const SIMULATED_SOURCE_RATE_FILES = new Set([
	'lib/components/product/WaveformPlot.svelte',
	'lib/product/waveform.ts',
	'routes/app/monitoring/+page.svelte'
]);

function listFiles(dir: string, out: string[] = []): string[] {
	for (const entry of readdirSync(dir)) {
		if (entry === '__tests__' || entry === 'node_modules' || entry.startsWith('.')) continue;
		const full = path.join(dir, entry);
		const stat = statSync(full);
		if (stat.isDirectory()) listFiles(full, out);
		else if (
			(entry.endsWith('.svelte') || entry.endsWith('.ts')) &&
			!EXCLUDED_RELATIVE_PATHS.has(path.relative(SRC_ROOT, full))
		)
			out.push(full);
	}
	return out;
}

/** A disclaimer ("no medical-grade claim is made") is the correct, required wording -- only an
 * unqualified/affirmative occurrence is a violation. */
function isNegated(text: string, matchIndex: number): boolean {
	const windowStart = Math.max(0, matchIndex - NEGATION_WINDOW);
	const preceding = text.slice(windowStart, matchIndex).toLowerCase();
	return NEGATION_MARKERS.some((marker) => preceding.includes(marker));
}

describe('legacy claim audit: no unsupported hardware/diagnosis claims in active source', () => {
	const files = listFiles(SRC_ROOT);
	expect(files.length).toBeGreaterThan(50); // sanity: the scan actually walked the tree

	for (const { label, pattern, allowNegated } of PROHIBITED_PATTERNS) {
		it(`no active file contains an unqualified: ${label}`, () => {
			const offenders: string[] = [];
			const globalPattern = new RegExp(pattern.source, pattern.flags.includes('g') ? pattern.flags : `${pattern.flags}g`);
			for (const file of files) {
				const text = readFileSync(file, 'utf-8');
				for (const match of text.matchAll(globalPattern)) {
					if (match.index === undefined) continue;
					if (allowNegated && isNegated(text, match.index)) continue;
					if (label === '360 Hz sampling claim' && SIMULATED_SOURCE_RATE_FILES.has(path.relative(SRC_ROOT, file))) continue;
					offenders.push(path.relative(SRC_ROOT, file));
					break;
				}
			}
			expect(offenders, `files matching ${pattern}: ${offenders.join(', ')}`).toEqual([]);
		});
	}
});
