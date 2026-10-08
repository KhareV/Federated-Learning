import { describe, expect, it } from 'vitest';
import { buildExport } from '../export';

describe('evidence export', () => {
	it('is deterministic, hashed, labelled and free of secrets', async () => {
		const a = await buildExport('window-trace', 'W 0', 'SYNTHETIC_ENGINEERING_RECONSTRUCTION', 'method', { n: 1 });
		const b = await buildExport('window-trace', 'W 0', 'SYNTHETIC_ENGINEERING_RECONSTRUCTION', 'method', { n: 1 });
		expect(a.sha256).toBe(b.sha256);
		expect(a.filename).toBe('nhm-window-trace-W_0.json');
		const doc = JSON.parse(a.text);
		expect(doc.schema_version).toBe('NHM_OBSERVATORY_EXPORT_V1');
		expect(doc.claim_boundary).toContain('SYNTHETIC');
		expect(a.text).not.toMatch(/sk_test_|Bearer |eyJ[A-Za-z0-9_-]{10,}\./);
	});
});
