import type { CandidateCohort, CohortId } from './types';

/** Every cohort a run can use, in display order. */
export const COHORT_IDS: readonly CohortId[] = ['ORIGINAL', 'REALISTIC', 'REALISTIC_NSTDB'];
export const isCohortId = (v: unknown): v is CohortId => typeof v === 'string' && (COHORT_IDS as readonly string[]).includes(v);
/** The realistic family: the invented-noise cohort and the recorded-noise cohort (same structure, own holdout). */
export const isRealisticFamily = (c: CohortId): boolean => c !== 'ORIGINAL';

export const COHORT_BUTTON: Record<CohortId, { title: string; sub: string }> = {
	ORIGINAL: { title: 'ORIGINAL', sub: 'FROZEN · REPRODUCES RECORDED RESULTS' },
	REALISTIC: { title: 'REALISTIC', sub: 'HARDER RHYTHM · SOFTWARE-GENERATED ECG' },
	REALISTIC_NSTDB: { title: 'REALISTIC + RECORDED NOISE', sub: 'NSTDB NOISE · STILL SOFTWARE-GENERATED ECG' }
};

/** The cohort as it reads in a sentence ("the realistic cohort"). */
export const COHORT_PHRASE: Record<CohortId, string> = { ORIGINAL: 'the original cohort', REALISTIC: 'the realistic cohort', REALISTIC_NSTDB: 'the realistic cohort with recorded noise' };
/** What the cohort's evaluation holdout is called in a sentence. */
export const COHORT_HOLDOUT_PHRASE: Record<CohortId, string> = { ORIGINAL: 'same frozen reused holdout', REALISTIC: 'realistic research evaluation cohort', REALISTIC_NSTDB: 'realistic research evaluation cohort with recorded noise' };
/** Short tag for badges and the fixed-configuration table. */
export const COHORT_TAG: Record<CohortId, string> = { ORIGINAL: 'ORIGINAL', REALISTIC: 'REALISTIC', REALISTIC_NSTDB: 'REALISTIC · RECORDED NOISE' };
export const cohortTestId = (c: CohortId): string => `cohort-${c.toLowerCase().replace(/_/g, '-')}`;

export const candidateChipText = (c: CandidateCohort): string => (c === 'REAL_ECG' ? 'REAL ECG · NO RESEARCH COHORT' : c === 'REALISTIC_NSTDB' ? 'REALISTIC · RECORDED NOISE' : c === 'REALISTIC' ? 'REALISTIC COHORT' : 'ORIGINAL COHORT');

/** The candidate's training cohort as it reads in the starter's candidate list ("original cohort", "realistic cohort", ...). */
export const candidateOptionText = (c: CandidateCohort): string => (c === 'REAL_ECG' ? 'real ECG, no research cohort' : c === 'REALISTIC_NSTDB' ? 'realistic cohort (recorded noise)' : c === 'REALISTIC' ? 'realistic cohort' : 'original cohort');
