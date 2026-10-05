import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseMlResearchEvidence, parseFlResearchEvidence, factMap } from '../types';

const catalog = JSON.parse(readFileSync(path.resolve(process.cwd(), '../artifacts/capstone/CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1.json'), 'utf8'));
const provenance = (facts: typeof catalog.ml_facts) => [...new Map(facts.map((f: { source_relative_path: string; source_sha256: string; phase: string }) =>
	[f.source_relative_path, { source_relative_path: f.source_relative_path, source_sha256: f.source_sha256, phase: f.phase }])).values()];
const common = { catalog_id: catalog.catalog_id, evidence_version: catalog.evidence_version,
	generated_from_frozen_sources: true, claim_boundary: catalog.claim_boundary };
const ml = { ...common, evidence_domain: 'ML', facts: catalog.ml_facts, source_provenance: provenance(catalog.ml_facts) };
const fl = { ...common, evidence_domain: 'FL', facts: catalog.fl_facts, source_provenance: provenance(catalog.fl_facts),
	scientific_fl_phases: catalog.scientific_fl_phases, v2_fl_005_role: catalog.v2_fl_005_role };

describe('CAP-009 frozen research evidence parsing', () => {
	it('preserves distinct historical promotion and later system release decisions', () => {
		const facts = factMap(parseMlResearchEvidence(ml).facts);
		expect(facts.get('promotion_decision')?.value).toBe('MODEL_V2_NOT_PROMOTED_RELEASE_CI');
		expect(facts.get('promotion_eligible')?.value).toBe(false);
		expect(facts.get('system_release_accepted')?.value).toBe(true);
	});
	it('excludes the engineering demo from scientific FL phases', () => {
		const value = parseFlResearchEvidence(fl);
		expect(value.scientific_fl_phases).not.toContain('V2-FL-005');
		expect(factMap(value.facts).get('fedprox_no_general_win')?.value).toBe(true);
	});
	it('rejects malformed provenance and forbidden efficacy-series expansion', () => {
		expect(() => parseMlResearchEvidence({ ...ml, facts: [{ ...ml.facts[0], source_sha256: 'bad' }] })).toThrow();
		expect(() => parseFlResearchEvidence({ ...fl, scientific_fl_phases: [...fl.scientific_fl_phases, 'V2-FL-005'] })).toThrow();
	});
});
