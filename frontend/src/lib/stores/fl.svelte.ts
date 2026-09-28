export const flState = $state({ isTraining: false, currentRound: 0, activeClients: 0, globalAccuracy: 0, globalF1: 0, lastUpdated: null as Date | null });

export function updateFL(data: Record<string, unknown>) {
	flState.currentRound = Number(data.current_round ?? flState.currentRound);
	flState.activeClients = Number(data.active_clients ?? flState.activeClients);
	flState.globalAccuracy = Number(data.global_accuracy ?? flState.globalAccuracy);
	flState.globalF1 = Number(data.global_f1 ?? flState.globalF1);
	flState.isTraining = Boolean(data.is_training ?? flState.isTraining);
	flState.lastUpdated = new Date();
}