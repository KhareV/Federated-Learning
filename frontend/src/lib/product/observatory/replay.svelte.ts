import { FederationLiveModel, type FederationView } from '../federation/live-model';

/** Per-event snapshots of the validated federation view model. Each snapshot is an independent copy: the model mutates in place. */
export function buildSnapshots(runId: string, events: unknown[]): FederationView[] | null {
	const model = new FederationLiveModel(runId);
	const out: FederationView[] = [];
	for (const event of events) {
		if (!model.applyRaw(event)) return null;
		out.push(structuredClone($state.snapshot(model.snapshot)) as FederationView);
	}
	return out;
}
