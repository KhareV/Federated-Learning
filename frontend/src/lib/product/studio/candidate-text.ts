import { COHORT_PHRASE } from './cohort-text';
import type { CandidateCohort, CohortId } from './types';

/** The training cohort of a stored candidate as it reads in a sentence. An imported research checkpoint was trained on real MIT-BIH patients in simulated sites: there is no research cohort behind it. */
export function trainedOn(cohort: CandidateCohort | null): string {
	if (cohort === 'REAL_ECG') return 'real MIT-BIH training patients in eight logical sites (no research cohort)';
	return COHORT_PHRASE[cohort ?? 'ORIGINAL'];
}

/** The cohort a run uses, in a sentence. */
export const runCohortName = (cohort: CohortId): string => COHORT_PHRASE[cohort];

/** Whether a candidate's training cohort differs from the cohort of the run it starts. A real-ECG checkpoint always does: it has no research cohort. */
export const crossesCohorts = (candidate: CandidateCohort | null, run: CohortId): boolean => candidate !== null && candidate !== run;

/** Candidates are listed by the cohort they were TRAINED on, in this order (the research checkpoint has no research cohort, so it comes last). */
export const TRAINING_GROUP_ORDER: CandidateCohort[] = ['ORIGINAL', 'REALISTIC', 'REALISTIC_NSTDB', 'REAL_ECG'];
export const TRAINING_GROUP_LABEL: Record<CandidateCohort, string> = {
	ORIGINAL: 'Trained on the original cohort',
	REALISTIC: 'Trained on the realistic cohort (invented noise)',
	REALISTIC_NSTDB: 'Trained on the realistic cohort with recorded noise',
	REAL_ECG: 'Imported research checkpoints (real MIT-BIH ECG, no research cohort)'
};

/** Group items by the cohort they were trained on, in a fixed order, newest first within a group. Empty groups are left out. */
export function groupByTrainingCohort<T extends { cohort: CandidateCohort; created_at?: string }>(items: T[]): { cohort: CandidateCohort; label: string; items: T[] }[] {
	return TRAINING_GROUP_ORDER
		.map((cohort) => ({ cohort, label: TRAINING_GROUP_LABEL[cohort], items: items.filter((c) => c.cohort === cohort).sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? ''))) }))
		.filter((g) => g.items.length > 0);
}
