import { displayCopy } from './display-copy';

/** Final presentation boundary for text supplied by APIs and historical records. */
export function installVisibleCopy(root: Node): () => void {
	const attributes = ['aria-label', 'title', 'alt', 'placeholder'];
	const ignored = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA']);
	const visit = (node: Node) => {
		if (node.nodeType === Node.TEXT_NODE) {
			if (!node.parentElement || ignored.has(node.parentElement.tagName)) return;
			const current = node.nodeValue ?? '';
			const next = displayCopy(current);
			if (next !== current) node.nodeValue = next;
			return;
		}
		if (node.nodeType !== Node.ELEMENT_NODE) return;
		const element = node as Element;
		if (ignored.has(element.tagName)) return;
		for (const attribute of attributes) {
			const current = element.getAttribute(attribute);
			if (current === null) continue;
			const next = displayCopy(current);
			if (next !== current) element.setAttribute(attribute, next);
		}
		for (const child of element.childNodes) visit(child);
	};
	visit(root);
	const observer = new MutationObserver((records) => {
		for (const record of records) {
			if (record.type === 'characterData') visit(record.target);
			else if (record.type === 'attributes') visit(record.target);
			else for (const node of record.addedNodes) visit(node);
		}
	});
	observer.observe(root, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: attributes });
	return () => observer.disconnect();
}
