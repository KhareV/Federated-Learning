import { describe, expect, it } from 'vitest';
import {
	DIAGNOSIS_WORD_ALLOWED_PREFIXES,
	MONITORING_STATES,
	PROHIBITED_WORDING,
	STATE_PRESENTATION,
	httpErrorPresentation
} from '../state-presentation';

describe('STATE_PRESENTATION: exactly five canonical states (Section 11)', () => {
	it('covers exactly the five canonical monitoring states, no more, no fewer', () => {
		expect(MONITORING_STATES).toHaveLength(5);
		expect(Object.keys(STATE_PRESENTATION).sort()).toEqual([...MONITORING_STATES].sort());
	});

	it('does not define a sixth state for QUALITY_WARNING', () => {
		expect(Object.keys(STATE_PRESENTATION)).not.toContain('QUALITY_WARNING');
	});

	for (const state of MONITORING_STATES) {
		it(`${state}: required wording present, no prohibited wording`, () => {
			const presentation = STATE_PRESENTATION[state];
			expect(presentation.title.length).toBeGreaterThan(0);
			expect(presentation.text.length).toBeGreaterThan(0);
			const combined = `${presentation.title} ${presentation.text}`.toLowerCase();
			for (const prohibited of PROHIBITED_WORDING) {
				expect(combined).not.toContain(prohibited);
			}
			// "diagnosis"/"diagnose" may only appear right after a negating qualifier.
			const diagnosisIndex = combined.indexOf('diagnos');
			if (diagnosisIndex !== -1) {
				const prefix = combined.slice(Math.max(0, diagnosisIndex - 8), diagnosisIndex);
				const allowed = DIAGNOSIS_WORD_ALLOWED_PREFIXES.some((p) => prefix.endsWith(p));
				expect(allowed, `"${combined}" uses "diagnos..." without a negating qualifier`).toBe(true);
			}
		});
	}

	it('NORMAL_MONITORED_PATTERN: neutral tone, probability displayable', () => {
		const presentation = STATE_PRESENTATION.NORMAL_MONITORED_PATTERN;
		expect(presentation.tone).toBe('neutral');
		expect(presentation.probabilityDisplayable).toBe(true);
	});

	it('POTENTIAL_ECTOPY_ASSOCIATED_PATTERN: says "Not a diagnosis"', () => {
		const presentation = STATE_PRESENTATION.POTENTIAL_ECTOPY_ASSOCIATED_PATTERN;
		expect(presentation.text).toContain('Not a diagnosis');
		expect(presentation.title.toLowerCase()).toContain('potential');
	});

	it('RECHECK_SENSOR: signal/sensor wording, not disease wording', () => {
		const presentation = STATE_PRESENTATION.RECHECK_SENSOR;
		expect(presentation.title.toLowerCase()).toMatch(/sensor|signal quality/);
		expect(presentation.tone).toBe('warning');
	});

	it('CONTEXT_UNAVAILABLE: states missing context, keeps probability displayable', () => {
		const presentation = STATE_PRESENTATION.CONTEXT_UNAVAILABLE;
		expect(presentation.text.toLowerCase()).toContain('unavailable');
		expect(presentation.probabilityDisplayable).toBe(true);
		expect(presentation.contextWarning).toBe(true);
	});

	it('SYSTEM_ERROR: technical wording, probability NOT displayable', () => {
		const presentation = STATE_PRESENTATION.SYSTEM_ERROR;
		expect(presentation.title.toLowerCase()).toContain('technical');
		expect(presentation.probabilityDisplayable).toBe(false);
	});
});

describe('httpErrorPresentation: Section 17 HTTP mapping', () => {
	it('400 maps to no canonical monitoring state and no probability point', () => {
		const presentation = httpErrorPresentation(400, 'bad request');
		expect(presentation.displayState).toBeNull();
		expect(presentation.appendProbabilityPoint).toBe(false);
		expect(presentation.appendHistoryGap).toBe(false);
	});

	it('422 maps to RECHECK_SENSOR with no probability point but a history gap', () => {
		const presentation = httpErrorPresentation(422, 'incomplete window');
		expect(presentation.displayState).toBe('RECHECK_SENSOR');
		expect(presentation.appendProbabilityPoint).toBe(false);
		expect(presentation.appendHistoryGap).toBe(true);
	});

	it('500 maps to SYSTEM_ERROR with no probability point but a history gap', () => {
		const presentation = httpErrorPresentation(500, 'internal error');
		expect(presentation.displayState).toBe('SYSTEM_ERROR');
		expect(presentation.appendProbabilityPoint).toBe(false);
		expect(presentation.appendHistoryGap).toBe(true);
	});
});
