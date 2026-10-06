// FINAL-EVAL-REPAIR-001 / LEGACY_ROUTE_POLICY_V1: pre-product dashboard pages are retired by exact-path redirect to the truthful current route.
// Mirrors configs/final_eval_repair/legacy_route_policy_v1.json (a Python test asserts equality). Pure; no I/O.
export const LEGACY_REDIRECTS: Readonly<Record<string, string>> = {
	'/overview': '/app',
	'/fl/overview': '/app/federation',
	'/fl/clients': '/app/federation/clients',
	'/fl/rounds': '/app/federation/rounds',
	'/fl/privacy': '/app/federation/privacy',
	'/fl/global-model': '/app/models',
	'/fl/aggregation': '/app/federation/rounds',
	'/fl/personal-models': '/app/federation',
	'/ai/anomaly': '/app/research/ml',
	'/ai/baseline': '/app/research/ml',
	'/ai/confidence': '/app/research/ml',
	'/ai/explainability': '/app/research/ml',
	'/ai/insights': '/app/research/ml',
	'/alerts': '/app/monitoring',
	'/patients': '/app',
	'/reports': '/app/history',
	'/trends': '/app/history',
	'/research/ablation': '/app/research/ml',
	'/research/analytics': '/app/research/ml',
	'/research/comparison': '/app/research/ml',
	'/research/experiments': '/app/research/ml',
	'/research/results': '/app/research/ml',
	'/research/robustness': '/app/research/ml',
	'/signals/dashboard': '/app/monitoring',
	'/signals/ecg': '/app/monitoring',
	'/signals/ppg': '/app/monitoring',
	'/signals/quality': '/app/monitoring',
	'/signals/spo2': '/app/monitoring',
	'/system/data': '/app/system',
	'/system/devices': '/app/device',
	'/system/health': '/app/system',
	'/system/notifications': '/app/system',
	'/system/settings': '/app/system',
};

/** The canonical current route for a retired legacy path, or null. Trailing slash is normalised; matching is exact (no prefix/substring). */
export function legacyRedirect(pathname: string): string | null {
	const path = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
	return Object.prototype.hasOwnProperty.call(LEGACY_REDIRECTS, path) ? LEGACY_REDIRECTS[path] : null;
}
