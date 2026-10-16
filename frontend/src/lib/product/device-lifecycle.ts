import type { DeviceState } from './types';

/**
 * Which device-lifecycle buttons are legal in each state. This mirrors the FROZEN transition table
 * (contracts/capstone/device_source_v1.json); the adapter additionally resumes STOPPED -> CONNECTED ("link kept after stop").
 * A button the contract forbids is disabled instead of producing ILLEGAL_DEVICE_TRANSITION.
 */
export const DEVICE_TRANSITIONS: Record<string, readonly string[]> = {
	DETACHED: ['SCANNING'],
	SCANNING: ['FOUND', 'ERROR', 'DETACHED'],
	FOUND: ['PAIRING', 'DETACHED'],
	PAIRING: ['CONNECTED', 'ERROR', 'DETACHED'],
	CONNECTED: ['STREAMING', 'DISCONNECTED', 'DETACHED'],
	STREAMING: ['DISCONNECTED', 'STOPPED', 'ERROR'],
	DISCONNECTED: ['RECONNECTING', 'DETACHED'],
	RECONNECTING: ['CONNECTED', 'ERROR', 'DETACHED'],
	STOPPED: ['CONNECTED', 'DETACHED'],
	ERROR: ['DETACHED', 'SCANNING']
};

export interface DeviceActions { scan: boolean; connect: boolean; reconnect: boolean; disconnect: boolean }

export function deviceActions(state: DeviceState | null | undefined): DeviceActions {
	const next = (state ? DEVICE_TRANSITIONS[state] : undefined) ?? [];
	return {
		scan: next.includes('SCANNING'),
		connect: state === 'FOUND',                       // FOUND -> PAIRING -> CONNECTED
		reconnect: state === 'STOPPED',                   // STOPPED -> CONNECTED
		disconnect: next.includes('DETACHED') || state === 'STREAMING' // STREAMING is ended, then detached, by the adapter
	};
}
