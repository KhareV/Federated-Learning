import type { HardwareSession, ProductClient } from './api';

/**
 * Recorded-hardware sessions of the signed-in owner, or [] when the backend has no hardware source.
 * The hardware routes exist only when the telemetry source is enabled; asking for them otherwise is a guaranteed 404 (a console error on every visit),
 * so the backend's own capability flag decides and a disabled source is an ordinary empty state.
 */
export async function loadHardwareSessions(api: Pick<ProductClient, 'studioCapabilities' | 'hardwareSessions'>): Promise<HardwareSession[]> {
	try {
		const caps = await api.studioCapabilities();
		return caps.hardware_demo?.available === true ? await api.hardwareSessions() : [];
	} catch {
		return [];
	}
}

/** A recorded session the Observatory can process: it has stored readings and is no longer being recorded. */
export const observatoryReady = (s: HardwareSession): boolean => s.status !== 'ACTIVE' && (s.summary?.stored_readings ?? 0) > 0;
