import { describe, expect, it } from 'vitest';
import { displayCopy } from '../display-copy';

describe('backend wording at the UI boundary', () => {
	it('keeps the source and label limitations understandable', () => {
		expect(displayCopy('Synthetic-only evidence: the score measures agreement with the simulator.'))
			.toBe('Evidence from software-generated ECG only: the score measures agreement with the software ECG generator.');
		expect(displayCopy('YOUR RECORDED WINDOWS · LABELS ARE SYNTHETIC'))
			.toBe('YOUR RECORDED WINDOWS · LABELS ARE ALGORITHMICALLY ASSIGNED');
	});
	it('does not alter raw protocol identifiers unless an explicit display label is defined', () => {
		expect(displayCopy('MODEL_V2_FINAL')).toBe('MODEL_V2_FINAL');
		expect(displayCopy('SYNTHETIC_ENGINEERING_EVENT_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL'))
			.toBe('Research-event evaluation only · not AAMI-SVF or clinical validation');
	});
});
