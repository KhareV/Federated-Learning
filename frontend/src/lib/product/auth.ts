// CAPSTONE_FRONTEND_AUTH_V1 -- client-side auth bootstrap. The backend is the authority:
//   GET /product/v1/system -> auth_provider / demo_mode decide the mode; there is no frontend toggle.
//   DEMO  : Clerk is never imported or initialised; /me supplies the explicit offline identity.
//   CLERK : the official ClerkJS is loaded lazily; REST calls carry `Authorization: Bearer <token>`
//           obtained from the active Clerk session per request (never stored). There is NO fallback
//           to Demo when Clerk is unavailable. Route guards are UX only; FastAPI authorizes.

import {
	ProductApiError,
	createProductClient,
	type ProductClient,
	type TokenProvider
} from './api';
import type { AuthIdentity, SystemInfoV2 } from './types';

export type AuthPhase =
	| 'LOADING'
	| 'SIGN_IN_REQUIRED' // mode known, no verified identity yet
	| 'AUTHENTICATED'
	| 'AUTHENTICATION_UNAVAILABLE' // CLERK mode but Clerk cannot initialise (never falls back)
	| 'BACKEND_UNREACHABLE';

export interface AuthState {
	phase: AuthPhase;
	mode: 'DEMO' | 'CLERK' | null;
	system: SystemInfoV2 | null;
	identity: AuthIdentity | null;
	error: string | null;
}

/** The small slice of the official ClerkJS surface this app uses. */
export interface ClerkLike {
	load(options?: Record<string, unknown>): Promise<void>;
	readonly session?: { getToken(): Promise<string | null> } | null;
	mountSignIn(node: HTMLDivElement, props?: Record<string, unknown>): void;
	unmountSignIn(node: HTMLDivElement): void;
	signOut(): Promise<void>;
	addListener?(callback: () => void): () => void;
}

export type ClerkLoader = (publishableKey: string) => Promise<ClerkLike>;

export interface FrontendAuthOptions {
	createClient?: (getToken?: TokenProvider) => ProductClient;
	loadClerk?: ClerkLoader;
	publishableKey?: string | null;
}

/**
 * Clerk Frontend API domain derived from the publishable key, as in the official ClerkJS quickstart
 * (https://clerk.com/docs/js-frontend/getting-started/quickstart): pk_test_<base64(domain + '$')>.
 * Returns null for anything that does not decode to a plain hostname.
 */
export function clerkFrontendApiDomain(publishableKey: string): string | null {
	const part = publishableKey.split('_')[2];
	if (!part) return null;
	try {
		const decoded = atob(part);
		const domain = decoded.endsWith('$') ? decoded.slice(0, -1) : '';
		return /^[A-Za-z0-9.-]+$/.test(domain) && domain.includes('.') ? domain : null;
	} catch {
		return null;
	}
}

type ClerkUiWindow = Window & { __internal_ClerkUICtor?: unknown };

/**
 * ClerkJS 6.x ships WITHOUT its prebuilt UI components; the official quickstart loads the separate `@clerk/ui`
 * browser bundle from the instance's own Frontend API domain and hands its constructor to `clerk.load`. Without it
 * `mountSignIn` throws "Clerk was not loaded with Ui components". Only ever invoked in CLERK mode.
 */
export async function loadClerkUiBundle(publishableKey: string): Promise<unknown> {
	const win = window as ClerkUiWindow;
	if (win.__internal_ClerkUICtor) return win.__internal_ClerkUICtor;
	const domain = clerkFrontendApiDomain(publishableKey);
	if (!domain) throw new Error('Clerk publishable key does not encode a Frontend API domain');
	await new Promise<void>((resolve, reject) => {
		const script = document.createElement('script');
		script.src = `https://${domain}/npm/@clerk/ui@1/dist/ui.browser.js`;
		script.async = true;
		script.crossOrigin = 'anonymous';
		script.onload = () => resolve();
		script.onerror = () => reject(new Error('Failed to load the Clerk UI bundle'));
		document.head.appendChild(script);
	});
	if (!win.__internal_ClerkUICtor) throw new Error('Clerk UI bundle did not register its constructor');
	return win.__internal_ClerkUICtor;
}

/** Lazy official-ClerkJS loader: only ever invoked in CLERK mode. */
export const defaultClerkLoader: ClerkLoader = async (publishableKey) => {
	const module = (await import('@clerk/clerk-js')) as unknown as {
		Clerk?: new (key: string) => ClerkLike;
		default?: new (key: string) => ClerkLike;
	};
	const ClerkCtor = module.Clerk ?? module.default;
	if (!ClerkCtor) throw new Error('ClerkJS export not found');
	const ClerkUI = await loadClerkUiBundle(publishableKey);
	const clerk = new ClerkCtor(publishableKey);
	await clerk.load({ ui: { ClerkUI } });
	return clerk;
};

export function readPublishableKey(): string | null {
	const key = (import.meta.env?.VITE_CLERK_PUBLISHABLE_KEY as string | undefined) ?? '';
	return key.trim() ? key.trim() : null;
}

export class FrontendAuth {
	state: AuthState = { phase: 'LOADING', mode: null, system: null, identity: null, error: null };
	private clerk: ClerkLike | null = null;
	private clerkInitialised = false;
	private readonly client: ProductClient;
	private readonly listeners = new Set<(state: AuthState) => void>();

	constructor(private readonly options: FrontendAuthOptions = {}) {
		const make = options.createClient ?? ((getToken) => createProductClient({ getToken }));
		this.client = make(() => this.token());
	}

	get api(): ProductClient {
		return this.client;
	}
	get clerkWasInitialised(): boolean {
		return this.clerkInitialised;
	}

	subscribe(listener: (state: AuthState) => void): () => void {
		this.listeners.add(listener);
		return () => this.listeners.delete(listener);
	}

	private set(patch: Partial<AuthState>): AuthState {
		this.state = { ...this.state, ...patch };
		for (const listener of this.listeners) listener(this.state);
		return this.state;
	}

	/** Bearer token for the CURRENT Clerk session; null in DEMO mode. Never persisted. */
	private async token(): Promise<string | null> {
		if (this.state.mode !== 'CLERK' || !this.clerk?.session) return null;
		return (await this.clerk.session.getToken()) ?? null;
	}

	/** Read /system, decide the mode, initialise Clerk only in CLERK mode. */
	async bootstrap(): Promise<AuthState> {
		let system: SystemInfoV2;
		try {
			system = await this.client.system();
		} catch (cause) {
			return this.set({
				phase: 'BACKEND_UNREACHABLE',
				error: cause instanceof Error ? cause.message : 'Product backend unavailable'
			});
		}
		const mode = system.auth_provider;
		this.set({ mode, system }); // the backend decides; recorded before any branch so token() sees it
		if (mode === 'DEMO') {
			// DEMO: no Clerk import, no Clerk network request.
			return this.set({ phase: 'SIGN_IN_REQUIRED', mode, system, identity: null, error: null });
		}
		const key = this.options.publishableKey === undefined ? readPublishableKey() : this.options.publishableKey;
		if (!key) {
			return this.set({
				phase: 'AUTHENTICATION_UNAVAILABLE',
				mode,
				system,
				error: 'Clerk publishable key (VITE_CLERK_PUBLISHABLE_KEY) is not configured'
			});
		}
		try {
			this.clerk = await (this.options.loadClerk ?? defaultClerkLoader)(key);
			this.clerkInitialised = true;
		} catch (cause) {
			return this.set({
				phase: 'AUTHENTICATION_UNAVAILABLE',
				mode,
				system,
				error: cause instanceof Error ? cause.message : 'Clerk failed to initialise'
			});
		}
		if (!this.clerk.session) {
			return this.set({ phase: 'SIGN_IN_REQUIRED', mode, system, identity: null, error: null });
		}
		return this.verifyIdentity();
	}

	/** DEMO: "Enter demo workspace". CLERK: call after the Clerk sign-in completes. */
	async verifyIdentity(): Promise<AuthState> {
		try {
			const identity = await this.client.me();
			return this.set({ phase: 'AUTHENTICATED', identity, error: null });
		} catch (cause) {
			if (cause instanceof ProductApiError && cause.kind === 'AUTHENTICATION_REQUIRED') {
				return this.set({ phase: 'SIGN_IN_REQUIRED', identity: null, error: cause.message });
			}
			return this.set({
				phase: 'BACKEND_UNREACHABLE',
				error: cause instanceof Error ? cause.message : 'Product backend unavailable'
			});
		}
	}

	async enterDemo(): Promise<AuthState> {
		if (this.state.mode !== 'DEMO') return this.state; // the backend decides; never switch modes here
		return this.verifyIdentity();
	}

	/** Used by app routes (refresh): runs the bootstrap again and verifies identity. */
	async restore(): Promise<AuthState> {
		await this.bootstrap();
		if (this.state.phase === 'SIGN_IN_REQUIRED' && this.state.mode === 'DEMO') {
			return this.verifyIdentity();
		}
		return this.state;
	}

	mountClerkSignIn(node: HTMLDivElement): () => void {
		if (!this.clerk) return () => {};
		const clerk = this.clerk;
		clerk.mountSignIn(node, {});
		const stop = clerk.addListener?.(() => {
			if (clerk.session && this.state.phase !== 'AUTHENTICATED') void this.verifyIdentity();
		});
		return () => {
			stop?.();
			clerk.unmountSignIn(node);
		};
	}

	async signOut(): Promise<void> {
		if (this.state.mode === 'CLERK' && this.clerk) await this.clerk.signOut();
		this.set({ phase: 'SIGN_IN_REQUIRED', identity: null });
	}
}
