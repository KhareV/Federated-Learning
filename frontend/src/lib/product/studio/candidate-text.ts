import { COHORT_PHRASE } from './cohort-text';
import type { CandidateCohort, CohortId } from './types';

/** The training cohort of a stored candidate as it reads in a sentence. An imported research checkpoint was trained on real MIT-BIH patients in simulated sites: there is no synthetic cohort behind it. */
export function trainedOn(cohort: CandidateCohort | null): string {
	if (cohort === 'REAL_ECG') return 'real MIT-BIH training patients in eight simulated sites (no synthetic cohort)';
	return COHORT_PHRASE[cohort ?? 'ORIGINAL'];
}

/** The cohort a run uses, in a sentence. */
export const runCohortName = (cohort: CohortId): string => COHORT_PHRASE[cohort];

/** Whether a candidate's training cohort differs from the cohort of the run it starts. A real-ECG checkpoint always does: it has no synthetic cohort. */
export const crossesCohorts = (candidate: CandidateCohort | null, run: CohortId): boolean => candidate !== null && candidate !== run;
