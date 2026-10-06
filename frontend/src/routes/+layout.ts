import { redirect } from '@sveltejs/kit';
import { legacyRedirect } from '$lib/product/route-policy';

export const ssr = false;
export const prerender = true;

// LEGACY_ROUTE_POLICY_V1: retired pre-product pages never render; they redirect to the truthful current route.
export function load({ url }: { url: URL }) {
	const target = legacyRedirect(url.pathname);
	if (target) redirect(307, target);
}
