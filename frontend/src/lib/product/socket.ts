// CAPSTONE_MONITORING_STORE_V1 (part): monitoring WebSocket with a bounded reconnect policy.
// The backend replays its journal from sequence 0 on every connection, so each (re)connect is a
// fresh deterministic rebuild: the consumer is told to reset before the first replayed event.

export const MAX_RECONNECTS = 3;
export const RECONNECT_DELAYS_MS = [500, 1000, 2000] as const;

export interface SocketLike {
	onopen: ((ev: unknown) => void) | null;
	onmessage: ((ev: { data: unknown }) => void) | null;
	onclose: ((ev: { code?: number }) => void) | null;
	onerror: ((ev: unknown) => void) | null;
	close(): void;
}

export interface LiveSocketHandlers {
	onReset(): void; // a new connection begins: clear event-derived state
	onMessage(data: unknown): void;
	onStatus(status: LiveSocketStatus): void;
}

export type LiveSocketStatus = 'CONNECTING' | 'OPEN' | 'RECONNECTING' | 'CLOSED_NORMAL' | 'DISCONNECTED';

export interface LiveSocketOptions {
	url: string;
	handlers: LiveSocketHandlers;
	factory?: (url: string) => SocketLike;
	setTimer?: (fn: () => void, ms: number) => unknown;
	clearTimer?: (handle: unknown) => void;
}

/** Normal close codes: 1000 = journal complete (session finished); 4401/4403/4404 are
 * authentication / ownership / unknown-session refusals and are never retried. */
export class LiveSocket {
	private socket: SocketLike | null = null;
	private retries = 0;
	private timer: unknown = null;
	private stopped = false;
	private everOpened = false;
	status: LiveSocketStatus = 'CONNECTING';

	constructor(private readonly options: LiveSocketOptions) {}

	connect(): void {
		this.stopped = false;
		this.retries = 0;
		this.open();
	}

	/** Explicit user reconnect after the bounded automatic policy gave up. */
	reconnect(): void {
		this.clearPending();
		this.socket?.close();
		this.stopped = false;
		this.retries = 0;
		this.open();
	}

	close(): void {
		this.stopped = true;
		this.clearPending();
		const socket = this.socket;
		this.socket = null;
		if (socket) {
			socket.onclose = null;
			socket.close();
		}
	}

	private set(status: LiveSocketStatus): void {
		this.status = status;
		this.options.handlers.onStatus(status);
	}

	private clearPending(): void {
		if (this.timer !== null) (this.options.clearTimer ?? clearTimeout)(this.timer as never);
		this.timer = null;
	}

	private open(): void {
		const factory = this.options.factory ?? ((url: string) => new WebSocket(url) as unknown as SocketLike);
		this.set(this.retries === 0 && !this.everOpened ? 'CONNECTING' : 'RECONNECTING');
		this.options.handlers.onReset();
		const socket = factory(this.options.url);
		this.socket = socket;
		socket.onopen = () => {
			this.everOpened = true;
			this.set('OPEN');
		};
		socket.onmessage = (event) => this.options.handlers.onMessage(event.data);
		socket.onerror = () => {};
		socket.onclose = (event) => {
			if (this.stopped || this.socket !== socket) return;
			const code = event?.code;
			if (code === 1000) return this.set('CLOSED_NORMAL');
			if (code === 4401 || code === 4403 || code === 4404) return this.set('DISCONNECTED');
			if (this.retries >= MAX_RECONNECTS) return this.set('DISCONNECTED');
			const delay = RECONNECT_DELAYS_MS[Math.min(this.retries, RECONNECT_DELAYS_MS.length - 1)];
			this.retries += 1;
			this.set('RECONNECTING');
			this.timer = (this.options.setTimer ?? setTimeout)(() => this.open(), delay);
		};
	}
}
