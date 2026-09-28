import { browser } from '$app/environment';

export type LiveConnection = {
	close: () => void;
};

export function connectLive(clientId: string, handlers: Partial<Pick<WebSocket, 'onopen' | 'onclose' | 'onerror' | 'onmessage'>> = {}): LiveConnection {
	if (!browser) return { close: () => undefined };

	const configured = import.meta.env.VITE_WS_BASE_URL;
	const base = configured || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;
	const socket = new WebSocket(`${base}/ws/live/${encodeURIComponent(clientId)}`);
	socket.onopen = handlers.onopen ?? null;
	socket.onclose = handlers.onclose ?? null;
	socket.onerror = handlers.onerror ?? null;
	socket.onmessage = handlers.onmessage ?? null;

	return { close: () => socket.close() };
}