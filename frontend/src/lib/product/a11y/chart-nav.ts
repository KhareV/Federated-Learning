// Keyboard model for data charts: ONE tab stop per chart, arrow keys move between its data points (roving tabindex).
// Without this every plotted point/bar is its own tab stop, so passing a chart costs dozens of Tab presses (a keyboard trap in practice).
// The action only manages `tabindex` and key handling; the points keep their own labels, focus announcements and Enter behaviour.
const KEYS = new Set(['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp', 'Home', 'End']);

export function chartNav(node: SVGSVGElement): { destroy: () => void } {
	let current: Element | null = null;
	const points = (): SVGElement[] => [...node.querySelectorAll<SVGElement>('[tabindex]')];
	const sync = () => {
		const all = points();
		if (all.length === 0) return;
		if (!current || !all.includes(current as SVGElement)) current = all[0];
		for (const p of all) {
			const want = p === current ? '0' : '-1';
			if (p.getAttribute('tabindex') !== want) p.setAttribute('tabindex', want);
		}
	};
	const observer = new MutationObserver(sync);
	observer.observe(node, { childList: true, subtree: true });
	sync();
	const onFocusIn = (event: FocusEvent) => {
		const target = event.target as Element | null;
		if (target && target !== node && target.hasAttribute('tabindex') && target !== current) { current = target; sync(); }
	};
	const onKeyDown = (event: KeyboardEvent) => {
		if (!KEYS.has(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
		const all = points();
		const index = current ? all.indexOf(current as SVGElement) : -1;
		if (index < 0 || all.length === 0) return;
		let next = index;
		if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = Math.min(all.length - 1, index + 1);
		else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = Math.max(0, index - 1);
		else if (event.key === 'Home') next = 0;
		else if (event.key === 'End') next = all.length - 1;
		event.preventDefault();
		current = all[next];
		sync();
		(all[next] as SVGElement & { focus: () => void }).focus();
	};
	node.addEventListener('focusin', onFocusIn);
	node.addEventListener('keydown', onKeyDown);
	return { destroy: () => { observer.disconnect(); node.removeEventListener('focusin', onFocusIn); node.removeEventListener('keydown', onKeyDown); } };
}
