// Bounded evidence export for ONE selected object. Contains only data already displayed, plus ids, hashes and the claim boundary.
// No secrets, tokens, identities or unauthorized research recordings are ever included.
export interface EvidenceExport { schema_version: 'NHM_OBSERVATORY_EXPORT_V1'; exported_from: string; kind: string; selected: string; claim_boundary: string; methodology: string; payload: unknown }

async function sha256(text: string): Promise<string> {
	const bytes = new TextEncoder().encode(text);
	const digest = await crypto.subtle.digest('SHA-256', bytes);
	return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function buildExport(kind: string, selected: string, claimBoundary: string, methodology: string, payload: unknown): Promise<{ filename: string; text: string; sha256: string }> {
	const doc: EvidenceExport = { schema_version: 'NHM_OBSERVATORY_EXPORT_V1', exported_from: 'NHM_RESEARCH_OBSERVATORY_V1_CANDIDATE', kind, selected, claim_boundary: claimBoundary, methodology, payload };
	const text = JSON.stringify(doc, null, 2) + '\n';
	return { filename: `nhm-${kind}-${selected.replace(/[^A-Za-z0-9_.-]+/g, '_')}.json`, text, sha256: await sha256(text) };
}

export async function downloadExport(kind: string, selected: string, claimBoundary: string, methodology: string, payload: unknown): Promise<string> {
	const built = await buildExport(kind, selected, claimBoundary, methodology, payload);
	const url = URL.createObjectURL(new Blob([built.text], { type: 'application/json' }));
	const a = document.createElement('a');
	a.href = url; a.download = built.filename; a.click();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
	return built.sha256;
}
