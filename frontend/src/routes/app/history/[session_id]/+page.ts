// The root layout prerenders everything (prerender = true), which makes SvelteKit DROP un-prerendered dynamic routes from the server manifest:
// a direct load or reload of this URL then matched no route and was answered with the SPA shell but HTTP 404.
// 'auto' keeps the route in the manifest, so the (SPA, ssr = false) shell is served with 200 for any id and the client router renders the page.
export const prerender = 'auto';
