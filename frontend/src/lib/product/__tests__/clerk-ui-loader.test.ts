// @vitest-environment jsdom
// CLERK-LIVE-001: ClerkJS 6.x needs the separate @clerk/ui bundle (official JavaScript quickstart). Only CLERK mode ever loads it.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FrontendAuth, clerkFrontendApiDomain, loadClerkUiBundle, type ClerkLike } from '../auth';
import { fakeBackend, systemInfo } from './support';

const PK = 'pk_test_' + btoa('example-app-1234.clerk.accounts.dev$');

afterEach(() => {
	delete (window as unknown as Record<string, unknown>).__internal_ClerkUICtor;
	document.head.querySelectorAll('script').forEach((node) => node.remove());
});

describe('Clerk UI bundle loader', () => {
	it('derives the Frontend API domain from the publishable key and rejects anything else', () => {
		expect(clerkFrontendApiDomain(PK)).toBe('example-app-1234.clerk.accounts.dev');
		expect(clerkFrontendApiDomain('pk_test_not-base64!!')).toBeNull();
		expect(clerkFrontendApiDomain('pk_test_' + btoa('evil.example.com/path$'))).toBeNull();
		expect(clerkFrontendApiDomain('pk_test_' + btoa('nodollar.example.com'))).toBeNull();
		expect(clerkFrontendApiDomain('garbage')).toBeNull();
	});

	it('loads the UI bundle from the instance Frontend API domain with crossorigin=anonymous and returns its constructor', async () => {
		const promise = loadClerkUiBundle(PK);
		const script = document.head.querySelector('script') as HTMLScriptElement;
		expect(script.src).toBe('https://example-app-1234.clerk.accounts.dev/npm/@clerk/ui@1/dist/ui.browser.js');
		expect(script.crossOrigin).toBe('anonymous');
		const Ctor = function ClerkUI() {};
		(window as unknown as Record<string, unknown>).__internal_ClerkUICtor = Ctor;
		script.onload?.(new Event('load'));
		await expect(promise).resolves.toBe(Ctor);
	});

	it('fails closed when the bundle cannot be loaded or registers nothing, and never appends a second script when already loaded', async () => {
		const failing = loadClerkUiBundle(PK);
		(document.head.querySelector('script') as HTMLScriptElement).onerror?.(new Event('error'));
		await expect(failing).rejects.toThrow('Failed to load the Clerk UI bundle');
		document.head.querySelectorAll('script').forEach((node) => node.remove());
		const silent = loadClerkUiBundle(PK);
		(document.head.querySelector('script') as HTMLScriptElement).onload?.(new Event('load'));
		await expect(silent).rejects.toThrow('did not register');
		const Ctor = function ClerkUI() {};
		(window as unknown as Record<string, unknown>).__internal_ClerkUICtor = Ctor;
		document.head.querySelectorAll('script').forEach((node) => node.remove());
		await expect(loadClerkUiBundle(PK)).resolves.toBe(Ctor);
		expect(document.head.querySelectorAll('script').length).toBe(0);
		await expect(loadClerkUiBundle('garbage')).resolves.toBe(Ctor);   // already loaded: no key needed
		delete (window as unknown as Record<string, unknown>).__internal_ClerkUICtor;
		await expect(loadClerkUiBundle('garbage')).rejects.toThrow('Frontend API domain');
	});

	it('DEMO mode never loads the Clerk UI bundle or ClerkJS', async () => {
		const loadClerk = vi.fn(async () => ({}) as ClerkLike);
		const auth = new FrontendAuth({ createClient: () => fakeBackend(systemInfo({ auth_provider: 'DEMO', demo_mode: true })), loadClerk, publishableKey: PK });
		await auth.bootstrap();
		expect(loadClerk).not.toHaveBeenCalled();
		expect(auth.clerkWasInitialised).toBe(false);
		expect(document.head.querySelectorAll('script').length).toBe(0);
	});
});
