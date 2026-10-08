/** Moves keyboard/screen-reader focus to the page heading after a client-side route change (WCAG 2.4.3 focus order guidance). */
export function focusHeading(node: HTMLElement): void {
	queueMicrotask(() => node.focus({ preventScroll: true }));
}
