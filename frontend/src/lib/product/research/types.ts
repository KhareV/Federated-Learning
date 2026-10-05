import { array, bool, fields, integer, literal, number, object, string } from '../evidence-validation';

export type FactValue = string | boolean | number | string[];
export interface EvidenceFact {
	fact_id: string; value: FactValue; unit: string | null; role: string; phase: string;
	source_relative_path: string; source_sha256: string; source_locator: (string | number)[];
	interpretation: string; limitations: string;
}
export interface SourceProvenance { phase: string; source_relative_path: string; source_sha256: string }
interface ResearchBase {
	catalog_id: 'CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1';
	evidence_version: 'FROZEN_SUMMARY_PROJECTION_V1';
	generated_from_frozen_sources: true;
	facts: EvidenceFact[]; source_provenance: SourceProvenance[];
	claim_boundary: 'READ_ONLY_NON_DIAGNOSTIC_RESEARCH_EVIDENCE';
}
export interface MlResearchEvidence extends ResearchBase { evidence_domain: 'ML' }
export interface FlResearchEvidence extends ResearchBase {
	evidence_domain: 'FL'; scientific_fl_phases: string[];
	v2_fl_005_role: 'FL_ENGINEERING_DEMO_NOT_SCIENTIFIC_EFFICACY';
}

function factValue(value: unknown, label: string): FactValue {
	if (typeof value === 'string') return value;
	if (typeof value === 'boolean') return bool(value, label);
	if (typeof value === 'number') return number(value, label);
	return array(value, string, label);
}

function fact(value: unknown, label: string): EvidenceFact {
	const o = object(value, label);
	fields(o, ['fact_id','value','unit','role','phase','source_relative_path','source_sha256','source_locator',
		'interpretation','limitations'], label);
	const path = string(o.source_relative_path, 'source_relative_path');
	if (path.startsWith('/') || path.includes('..') || !/^(reports\/model_v2|artifacts)\//.test(path))
		throw new Error('MALFORMED_EVIDENCE:source_path');
	const digest = string(o.source_sha256, 'source_sha256');
	if (!/^[a-f0-9]{64}$/.test(digest)) throw new Error('MALFORMED_EVIDENCE:source_sha256');
	return { fact_id: string(o.fact_id, 'fact_id'), value: factValue(o.value, 'value'),
		unit: o.unit === null ? null : string(o.unit, 'unit'), role: string(o.role, 'role'),
		phase: string(o.phase, 'phase'), source_relative_path: path, source_sha256: digest,
		source_locator: array(o.source_locator, (v, l) => typeof v === 'string' ? string(v, l) : integer(v, l), 'source_locator'),
		interpretation: string(o.interpretation, 'interpretation'),
		limitations: string(o.limitations, 'limitations') };
}

function provenance(value: unknown, label: string): SourceProvenance {
	const o = object(value, label);
	fields(o, ['phase','source_relative_path','source_sha256'], label);
	return { phase: string(o.phase, 'phase'), source_relative_path: string(o.source_relative_path, 'source_relative_path'),
		source_sha256: string(o.source_sha256, 'source_sha256') };
}

function base(value: unknown, domain: 'ML' | 'FL') {
	const o = object(value, `research.${domain}`);
	fields(o, ['catalog_id','evidence_version','generated_from_frozen_sources','facts',
		'source_provenance','claim_boundary','evidence_domain',
		...(domain === 'FL' ? ['scientific_fl_phases','v2_fl_005_role'] : [])], `research.${domain}`);
	const common: ResearchBase = {
		catalog_id: literal(o.catalog_id, 'CAPSTONE_RESEARCH_EVIDENCE_CATALOG_V1', 'catalog_id'),
		evidence_version: literal(o.evidence_version, 'FROZEN_SUMMARY_PROJECTION_V1', 'evidence_version'),
		generated_from_frozen_sources: o.generated_from_frozen_sources === true ? true
			: (() => { throw new Error('MALFORMED_EVIDENCE:generated_from_frozen_sources'); })(),
		facts: array(o.facts, fact, 'facts'), source_provenance: array(o.source_provenance, provenance, 'source_provenance'),
		claim_boundary: literal(o.claim_boundary, 'READ_ONLY_NON_DIAGNOSTIC_RESEARCH_EVIDENCE', 'claim_boundary')
	};
	literal(o.evidence_domain, domain, 'evidence_domain');
	return { o, common };
}

export function parseMlResearchEvidence(value: unknown): MlResearchEvidence {
	return { ...base(value, 'ML').common, evidence_domain: 'ML' };
}
export function parseFlResearchEvidence(value: unknown): FlResearchEvidence {
	const { o, common } = base(value, 'FL');
	const phases = array(o.scientific_fl_phases, string, 'scientific_fl_phases');
	if (phases.join('|') !== 'V2-FL-001|V2-FL-002|V2-FL-003|V2-FL-EVAL-001|V2-FL-004')
		throw new Error('MALFORMED_EVIDENCE:scientific_fl_phases');
	return { ...common, evidence_domain: 'FL', scientific_fl_phases: phases,
		v2_fl_005_role: literal(o.v2_fl_005_role, 'FL_ENGINEERING_DEMO_NOT_SCIENTIFIC_EFFICACY', 'v2_fl_005_role') };
}

export function factMap(facts: EvidenceFact[]): Map<string, EvidenceFact> {
	return new Map(facts.map((fact) => [fact.fact_id, fact]));
}
