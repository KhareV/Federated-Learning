// Human labels for technical federation states (technical names are never renamed internally).
import type { Algorithm, AggregationMode, ClientState } from './types';

export const ALGORITHM_LABEL: Record<Algorithm, { name: string; text: string }> = {
	FEDAVG: { name: 'FEDAVG', text: 'Federated averaging baseline.' },
	FEDPROX: { name: 'FEDPROX', text: 'Frozen federated proximal configuration.' }
};
export const MODE_LABEL: Record<AggregationMode, { name: string; text: string }> = {
	PLAIN: { name: 'PLAIN', text: 'Authoritative weighted aggregation only.' },
	SECAGG_SHADOW: { name: 'SECAGG_SHADOW', text: 'Authoritative aggregation stays PLAIN. A round-1 protected-aggregation shadow (Flower SecAgg+) is executed and compared with the plain aggregate under the frozen tolerance.' }
};
export const CLIENT_LABEL: Record<ClientState, string> = {
	IDLE: 'WAITING', DATA_READY: 'DATA READY', TRAINING: 'TRAINING', UPDATE_READY: 'UPDATE READY', SUBMITTED: 'SUBMITTED', REJECTED: 'REJECTED', FAILED: 'FAILED'
};
/** 8 chars head + ellipsis + 4 tail; the full value stays in the title / copy action. */
export function shortDigest(d: string | null | undefined): string {
	return d ? (d.length > 14 ? `${d.slice(0, 8)}…${d.slice(-4)}` : d) : '--';
}
