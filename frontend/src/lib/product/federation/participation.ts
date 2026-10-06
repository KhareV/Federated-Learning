// USER_BOUND_FL_PARTICIPATION_V1 (UFL-LITE-002): a PURE presentation rule. One existing synthetic FL client is presented as the
// authenticated owner's edge client. It needs only the backend-decided auth provider, the run type and a client id: no user identity,
// token, storage, network or Svelte state. The backend already guarantees that the viewed run belongs to the authenticated caller.
import type { AuthProviderName } from '../types';
import type { RunType } from './types';

export const OWNER_BOUND_CLIENT_ID = 'SIM_FL_SITE_00';
export type ParticipationRole = 'AUTHENTICATED_OWNER' | 'SYNTHETIC_PEER';

/** SIM_FL_SITE_00 only for CLERK + LIVE_RUN; DEMO, REPLAY and "no run" have no owner-bound client. */
export function ownerBoundClientId(authProvider: AuthProviderName | null | undefined, runType: RunType | null | undefined): string | null {
	return authProvider === 'CLERK' && runType === 'LIVE_RUN' ? OWNER_BOUND_CLIENT_ID : null;
}

export function participationRole(clientId: string, ownerBound: string | null | undefined): ParticipationRole | null {
	if (!ownerBound) return null;
	return clientId === ownerBound ? 'AUTHENTICATED_OWNER' : 'SYNTHETIC_PEER';
}
