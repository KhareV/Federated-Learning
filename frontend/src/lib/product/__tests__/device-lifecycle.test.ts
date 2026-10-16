import { describe, expect, it } from 'vitest';
import { DEVICE_TRANSITIONS, deviceActions } from '../device-lifecycle';

describe('device lifecycle buttons', () => {
	it('never offers Scan from STOPPED or DISCONNECTED (ILLEGAL_DEVICE_TRANSITION:STOPPED->SCANNING)', () => {
		expect(deviceActions('STOPPED').scan).toBe(false);
		expect(deviceActions('DISCONNECTED').scan).toBe(false);
	});
	it('offers Reconnect after a stopped session, and Scan only where the contract allows it', () => {
		expect(deviceActions('STOPPED')).toMatchObject({ reconnect: true, connect: false, disconnect: true });
		expect(deviceActions('DETACHED').scan).toBe(true);
		expect(deviceActions('ERROR').scan).toBe(true);
		expect(deviceActions('FOUND').connect).toBe(true);
		expect(deviceActions('CONNECTED').disconnect).toBe(true);
	});
	it('scan is enabled exactly where the frozen table has a ->SCANNING edge', () => {
		for (const [state, next] of Object.entries(DEVICE_TRANSITIONS)) expect(deviceActions(state as never).scan).toBe(next.includes('SCANNING'));
		expect(deviceActions(null)).toEqual({ scan: false, connect: false, reconnect: false, disconnect: false });
	});
});
