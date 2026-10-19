// Data source of a federation run (presentation only). The Live page is ONE design for every run; only where the eight logical clients'
// training windows come from differs. Kept apart from participation.ts, which stays byte-identical to the original owner-binding rule.
export type RunDataSource = 'SYNTHETIC' | 'HARDWARE';
export const SYNTHETIC_CLIENT_IDS = Array.from({ length: 8 }, (_, i) => `SIM_FL_SITE_0${i}`);
export const HARDWARE_CLIENT_IDS = Array.from({ length: 8 }, (_, i) => `RECORDED_DEMO_CLIENT_0${i}`);

export function runDataSource(runId: string | null | undefined, engine?: string | null): RunDataSource {
	return engine === 'HARDWARE_DEMO' || (runId ?? '').startsWith('HDFLRUN-') ? 'HARDWARE' : 'SYNTHETIC';
}
export const clientIdsFor = (source: RunDataSource): string[] => (source === 'HARDWARE' ? HARDWARE_CLIENT_IDS : SYNTHETIC_CLIENT_IDS);
/** The eight logical clients of THIS run: its descriptor's own list when it has one (a pretrained-V2 hardware run is one recorded client plus seven research peers), else the namespace default. */
export const clientIdsOfRun = (source: RunDataSource, runClientIds?: readonly string[] | null): string[] => (runClientIds && runClientIds.length === 8 ? [...runClientIds] : clientIdsFor(source));
/** A client that holds YOUR recorded windows (as opposed to a research peer). */
export const isRecordedClient = (clientId: string): boolean => clientId.startsWith('RECORDED_DEMO_CLIENT_');

/** Short, human name for a logical client: SIM_FL_SITE_03 -> "Site 03", RECORDED_DEMO_CLIENT_03 -> "Client 03". */
export function clientShortName(clientId: string): string {
	const m = /(\d{2})$/.exec(clientId);
	if (!m) return clientId;
	return clientId.startsWith('RECORDED_DEMO_CLIENT_') ? `Client ${m[1]}` : `Site ${m[1]}`;
}

/** Pretrained-V2 recorded-hardware runs: one recorded client and seven research peers, exactly the shape of a synthetic V2 run. */
export const HARDWARE_V2_COPY: (typeof SOURCE_COPY)['HARDWARE'] = {
	chip: '1 recorded client · 7 research peers', claimChips: ['RECORDED HARDWARE DATA', 'ASSIGNED RESEARCH LABELS'], network: 'Federated participants', networkNote: 'RECORDED HARDWARE · ASSIGNED RESEARCH LABELS',
	dataLabel: 'YOUR RECORDED WINDOWS · LABELS ARE ALGORITHMICALLY ASSIGNED', bufferLabel: 'Local recorded-window buffer', modelLabel: 'MODEL_V2 architecture (pretrained V2 weights)', peerTag: 'RESEARCH COHORT PEER'
};

export const SOURCE_COPY: Record<RunDataSource, { chip: string; claimChips: string[]; network: string; networkNote: string; dataLabel: string; bufferLabel: string; modelLabel: string; peerTag: string | null }> = {
	SYNTHETIC: {
		chip: '8 logical clients', claimChips: ['LOGICAL CLIENTS'], network: 'Eight logical clients', networkNote: 'SOFTWARE-GENERATED ECG',
		dataLabel: 'SOFTWARE-GENERATED ECG · NOT YOUR PHYSIOLOGY', bufferLabel: 'Local research-window buffer', modelLabel: 'MODEL_V2 architecture', peerTag: 'RESEARCH PEER'
	},
	HARDWARE: {
		chip: '8 logical clients · your recorded windows', claimChips: ['RECORDED HARDWARE DATA', 'ASSIGNED RESEARCH LABELS'], network: 'Eight logical clients holding your recorded windows', networkNote: 'RECORDED HARDWARE · ASSIGNED RESEARCH LABELS',
		dataLabel: 'YOUR RECORDED WINDOWS · LABELS ARE ALGORITHMICALLY ASSIGNED', bufferLabel: 'Local recorded-window buffer', modelLabel: 'HARDWARE_DEMO_MODEL_V1 (tabular)', peerTag: null
	}
};
