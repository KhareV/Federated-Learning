// The guided demonstration path: one story from monitoring to measured, bounded evidence. Pure data, so every claim in it can be tested.
// Every step names HOW its evidence is produced (computed now, a prepared recorded run, frozen evidence, a stored session) so a replay is never presented as live.

export type EvidenceMode = 'LIVE_COMPUTED' | 'PREPARED_RUN' | 'FROZEN_EVIDENCE' | 'RECORDED_SESSION' | 'STORED_LIBRARY' | 'STATEMENT';

export const EVIDENCE_MODES: Readonly<Record<EvidenceMode, { label: string; meaning: string }>> = {
	LIVE_COMPUTED: { label: 'LIVE · COMPUTED NOW', meaning: 'Computed on this machine while you watch (a simulated source or a real local training run).' },
	PREPARED_RUN: { label: 'PREPARED RUN · RECORDED', meaning: 'A run completed earlier in this workspace; opened, not recomputed. It carries its own RECORDED / replay labels.' },
	FROZEN_EVIDENCE: { label: 'FROZEN EVIDENCE · HASH-CHECKED', meaning: 'A committed report read after a SHA-256 check. Nothing is trained or re-evaluated.' },
	RECORDED_SESSION: { label: 'RECORDED SESSION · STORED', meaning: 'Stored telemetry or a stored monitoring session; its labels and quality grades are shown as recorded.' },
	STORED_LIBRARY: { label: 'STORED · DURABLE LIBRARY', meaning: 'Engineering candidates kept across restarts, verified against their digest before use.' },
	STATEMENT: { label: 'STATEMENT', meaning: 'Scope and limits, said aloud.' }
};

export interface DemoStep {
	id: string;
	title: string;
	minutes: number;
	href: string;
	open: string;
	mode: EvidenceMode;
	does: string;
	understand: string;
	say: string;
	ifItFails: string;
}

export const DEMO_STEPS: readonly DemoStep[] = [
	{ id: 'scope', title: 'Scope and boundary', minutes: 0.5, href: '/app/about', open: 'About', mode: 'STATEMENT',
		does: 'State what NHM is: a research prototype with a released centrally trained model, a monitoring product, and a separate federated engineering lane.',
		understand: 'Three things are kept apart everywhere: frozen scientific evidence, a monitoring product, and an engineering demonstration.',
		say: 'This is not clinical or diagnostic. Synthetic and assigned labels are never expert ground truth.', ifItFails: 'Nothing to fail; this is a statement.' },
	{ id: 'monitor', title: 'A signal enters the monitor', minutes: 1.25, href: '/app/monitoring', open: 'Monitor', mode: 'LIVE_COMPUTED',
		does: 'Attach the simulated wearable, start a session, and point at the quality state before any model result. Mention that a MongoDB hardware source exists and is shown only as a labelled, recorded session.',
		understand: 'Windows are built causally, quality is graded before inference, and the released model answers per window.',
		say: 'The wearable here is simulated. The hardware path is an experimental, resampled analysis that is explicitly marked not valid.', ifItFails: 'Open the latest completed session from History; it is stored evidence.' },
	{ id: 'federation', title: 'Federated training, live', minutes: 2, href: '/app/federation', open: 'Federation Studio', mode: 'LIVE_COMPUTED',
		does: 'Choose the realistic cohort and 3 rounds from the pretrained start, then start. Narrate the eight logical clients, local training, aggregation and the per-round evaluation. Start it, continue to the next step, and return.',
		understand: 'Local optimisation and aggregation are really executed on one machine, and each committed state is scored afterwards by a separate observer.',
		say: 'Eight logical clients on one laptop with synthetic data: it demonstrates the mechanism, not a deployment.', ifItFails: 'Open the prepared completed run from "Your federation runs" and use its replay.' },
	{ id: 'evaluation', title: 'Independent evaluation of every round', minutes: 1, href: '/app/federation/live', open: 'Live federation', mode: 'PREPARED_RUN',
		does: 'Show the evaluated rounds, the evaluation cohort label, the fixed 0.5 rule and the generalisation tab against the frozen V2 baseline.',
		understand: 'The evaluation cohort is disjoint from training, no round or threshold is selected from it, and a score on a synthetic cohort is a pipeline check, not a performance claim.',
		say: 'These scores come from one synthetic cohort family. Over five repeated training runs round 10 beats the pretrained start there, but adapting to the synthetic cohort lowers performance on real MIT-BIH ECG, so a candidate is not a better ECG model than the released one.', ifItFails: 'Use any completed run; the layout is identical.' },
	{ id: 'science', title: 'The scientific result', minutes: 1.25, href: '/app/observatory/outcomes', open: 'FL research outcomes', mode: 'FROZEN_EVIDENCE',
		does: 'Show that federated training matched centralized training on MIT-BIH and on the external INCART set, with the intervals and the exposed-dataset caveat. Then open the external check: the same frozen models on real PTB-XL ECG that no model had seen (record-level target, outside the locked scope).',
		understand: 'This is the only evidence with real, expert-annotated ECG behind it; the federated and centralized results are not ranked against each other.',
		say: 'Few patient clusters, nominal intervals, and an exposed external set: matching, not superiority.', ifItFails: 'Use the exported figure PNGs listed in the demo runbook.' },
	{ id: 'candidates', title: 'Candidates, kept and reused', minutes: 1.25, href: '/app/models', open: 'Models', mode: 'STORED_LIBRARY',
		does: 'Open the stored candidates, group by evaluation cohort, show a lineage chain, then start a run from a candidate on the other cohort.',
		understand: 'A candidate is an engineering artefact with provenance: digest-verified before use, owner-scoped, never deployed or used for monitoring.',
		say: 'Scores of candidates evaluated on different cohorts are not comparable; the page says so.', ifItFails: 'Show the lineage and digest; skip starting the run.' },
	{ id: 'hardware', title: 'The hardware boundary', minutes: 1, href: '/app/history', open: 'History', mode: 'RECORDED_SESSION',
		does: 'Open a recorded hardware session: stored readings, the quality grades, and how many windows were VALID versus accepted below VALID for experimental training.',
		understand: 'One recorded client with assigned labels is federated with seven synthetic peers to test the pipeline; it says nothing about the device or a person.',
		say: 'The device streams about 17 to 20 samples per second, which is far too low for QRS morphology. Physical-device verification is not claimed.', ifItFails: 'Use the stored showcase session, which is labelled as generated.' },
	{ id: 'limits', title: 'Limits and provenance', minutes: 0.75, href: '/app/observatory/provenance', open: 'Provenance', mode: 'FROZEN_EVIDENCE',
		does: 'Open the provenance page and read the known boundaries: calibration domain, exposed datasets, SecAgg as a round-1 shadow check, synthetic cohorts.',
		understand: 'Negative and limiting findings are part of the result, and every statement points to a committed file.',
		say: 'SecAgg+ here verifies a protected aggregate matches the plain one in a single-host simulation; it is not a privacy guarantee.', ifItFails: 'Nothing to fail; evidence is read-only.' }
];

export const totalMinutes = (steps: readonly DemoStep[] = DEMO_STEPS): number => steps.reduce((n, s) => n + s.minutes, 0);

/** Phrases that must never appear in the demonstration path: each would claim more than the evidence supports. Limits are stated with "not" / "no", which these do not match. */
export const FORBIDDEN_CLAIMS: readonly RegExp[] = [/clinically validated/i, /(?<!not |no )physical(ly)?[- ](esp32 |hardware |device )?(is |was )?verified/i, /federated (beats|outperforms)/i, /diagnostic accuracy/i, /\bbetter model\b/i, /\bproves?\b/i];
