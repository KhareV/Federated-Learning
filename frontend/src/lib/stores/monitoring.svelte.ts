import type { SensorReading } from '$lib/types';

export const monitoringState = $state({
	isMonitoring: false,
	liveHR: 0,
	liveSPO2: 0,
	 ecgSQI: 0,
	ppgSQI: 0,
	overallSQI: 0,
	qualityLabel: 'UNKNOWN',
	anomalyScore: 0,
	anomalyClass: 'NORMAL',
	confidence: 0,
	lastUpdated: null as Date | null,
	liveECGBuffer: [] as number[],
	livePPGBuffer: [] as number[]
});

export function updateMonitoring(data: Partial<SensorReading>) {
	monitoringState.liveHR = data.hr ?? monitoringState.liveHR;
	monitoringState.liveSPO2 = data.spo2 ?? monitoringState.liveSPO2;
	monitoringState.ecgSQI = data.ecg_sqi ?? monitoringState.ecgSQI;
	monitoringState.ppgSQI = data.ppg_sqi ?? monitoringState.ppgSQI;
	monitoringState.overallSQI = data.overall_sqi ?? monitoringState.overallSQI;
	monitoringState.qualityLabel = data.anomaly_class ?? monitoringState.qualityLabel;
	monitoringState.anomalyScore = data.anomaly_score ?? monitoringState.anomalyScore;
	monitoringState.anomalyClass = data.anomaly_class ?? monitoringState.anomalyClass;
	monitoringState.confidence = data.confidence ?? monitoringState.confidence;
	monitoringState.lastUpdated = new Date();
}

export function appendECG(samples: number[]) { monitoringState.liveECGBuffer = [...monitoringState.liveECGBuffer, ...samples].slice(-1250); }
export function appendPPG(samples: number[]) { monitoringState.livePPGBuffer = [...monitoringState.livePPGBuffer, ...samples].slice(-250); }