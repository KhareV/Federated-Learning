// Central state-presentation contract for the NHM dashboard (T033, DASHBOARD_UI_V1).
//
// Every dashboard component consumes this module rather than hardcoding wording. The five
// canonical monitoring states come from the frozen API_RUNTIME_V1 contract
// (fusion/state_machine.py); this module never recomputes or invents a sixth state. HTTP
// 400/422/500 are a SEPARATE transport/request-level category -- never fabricated into a
// monitoring_state value (Section 11/17).

import type { MonitoringState } from '$lib/api/nhm-v1';
import { MONITORING_STATES } from '$lib/api/nhm-v1';

export { MONITORING_STATES };
export type { MonitoringState };

/** Visual severity token only -- never a scientific/monitoring state. */
export type VisualTone = 'neutral' | 'notice' | 'warning' | 'technical-error';

export interface StatePresentation {
	title: string;
	text: string;
	tone: VisualTone;
	/** Whether this canonical state is compatible with showing a probability figure, when the
	 * API response actually supplies one (SYSTEM_ERROR never does, by construction). */
	probabilityDisplayable: boolean;
	/** Whether a PPG/SpO2 context warning banner should render alongside this state. */
	contextWarning: boolean;
}

export const STATE_PRESENTATION: Record<MonitoringState, StatePresentation> = {
	NORMAL_MONITORED_PATTERN: {
		title: 'Normal monitored pattern',
		text: 'Latest source-domain calibrated probability and signal quality are shown below. This is a research monitoring state, not a health assessment.',
		tone: 'neutral',
		probabilityDisplayable: true,
		contextWarning: false
	},
	POTENTIAL_ECTOPY_ASSOCIATED_PATTERN: {
		title: 'Potential SVF-associated ECG pattern',
		text: 'Recording review recommended. Not a diagnosis.',
		tone: 'notice',
		probabilityDisplayable: true,
		contextWarning: false
	},
	RECHECK_SENSOR: {
		title: 'Recheck sensor / signal quality',
		text: 'Signal quality is degraded or unusable for this window. Reposition or check the sensor connection.',
		tone: 'warning',
		probabilityDisplayable: true,
		contextWarning: false
	},
	CONTEXT_UNAVAILABLE: {
		title: 'Context unavailable',
		text: 'PPG / SpO2 context is unavailable for this window. The ECG result, when valid, is still shown below -- it is never hidden for missing context.',
		tone: 'notice',
		probabilityDisplayable: true,
		contextWarning: true
	},
	SYSTEM_ERROR: {
		title: 'Technical system error -- monitoring result unavailable',
		text: 'A technical failure prevented this window from producing a monitoring result. No probability is shown; the previous result is not implied to still be current.',
		tone: 'technical-error',
		probabilityDisplayable: false,
		contextWarning: false
	}
};

/** HTTP-layer presentation (Section 17). 400 is a distinct request/transport category --
 * never mapped onto a canonical monitoring_state, never appended to probability history. */
export type HttpErrorKind = 400 | 422 | 500;

export interface HttpErrorPresentation {
	/** The canonical monitoring_state this HTTP status should render as, or null for 400
	 * (400 is a request/input contract error, not a scientific monitoring state). */
	displayState: MonitoringState | null;
	title: string;
	text: string;
	tone: VisualTone;
	appendProbabilityPoint: false;
	/** Whether this HTTP outcome should still leave a gap/event marker in the probability
	 * history (true for 422/500, which the backend accepts as real window events; false for
	 * 400, which never reaches ALERT_POLICY_V1 at all). */
	appendHistoryGap: boolean;
}

export function httpErrorPresentation(status: HttpErrorKind, message: string): HttpErrorPresentation {
	if (status === 400) {
		return {
			displayState: null,
			title: 'Request error',
			text: `The request did not meet the API contract and was not accepted: ${message}`,
			tone: 'technical-error',
			appendProbabilityPoint: false,
			appendHistoryGap: false
		};
	}
	if (status === 422) {
		return {
			displayState: 'RECHECK_SENSOR',
			title: STATE_PRESENTATION.RECHECK_SENSOR.title,
			text: `Unusable or incomplete signal window -- No model inference was run for this window: ${message}`,
			tone: 'warning',
			appendProbabilityPoint: false,
			appendHistoryGap: true
		};
	}
	return {
		displayState: 'SYSTEM_ERROR',
		title: STATE_PRESENTATION.SYSTEM_ERROR.title,
		text: message,
		tone: 'technical-error',
		appendProbabilityPoint: false,
		appendHistoryGap: true
	};
}

/** Prohibited substrings: if any of these ever appear in rendered dashboard copy, the
 * dashboard has drifted into a diagnosis/disease claim. Used by tests, not production code.
 * Deliberately does NOT include the bare word "diagnosis" -- the required disclaimer text
 * ("Not a diagnosis.") must say exactly that; see PROHIBITED_WORDING_EXCEPTIONS below for how
 * tests should treat it. */
export const PROHIBITED_WORDING = [
	'healthy',
	'normal heart',
	'no arrhythmia',
	'disease-free',
	'arrhythmia detected',
	'ectopy confirmed',
	'abnormal patient',
	'danger',
	'emergency',
	'disease detected',
	'disease risk',
	'medical grade',
	'medical-grade',
	'clinical grade',
	'clinical-grade'
];

/** A rendered diagnosis-claim check must flag "diagnosis"/"diagnose" appearing WITHOUT one of
 * these negating qualifiers immediately before it (case-insensitive). */
export const DIAGNOSIS_WORD_ALLOWED_PREFIXES = ['not a ', 'not for ', 'no '];
