<script lang="ts">
	import type { EvidenceFact, SourceProvenance } from '$lib/product/research/types';
	let { facts, provenance }: { facts: EvidenceFact[]; provenance: SourceProvenance[] } = $props();
	const display = (value: EvidenceFact['value']) => Array.isArray(value) ? value.join(' • ') : String(value);
</script>
<div class="scroll"><table><caption>Frozen facts copied from source summaries, with their research role</caption>
	<thead><tr><th scope="col">Fact</th><th scope="col">Exact frozen value</th><th scope="col">Role</th><th scope="col">Source phase</th></tr></thead>
	<tbody>{#each facts as fact}<tr><th scope="row">{fact.fact_id}</th><td>{display(fact.value)}{fact.unit ? ` ${fact.unit}` : ''}</td><td>{fact.role}</td><td>{fact.phase}</td></tr>{/each}</tbody>
</table></div>
<details><summary>EVIDENCE PROVENANCE</summary><p>Repository-relative frozen source files and SHA256 hashes. The API verifies these before serving the catalog.</p>
	<ul>{#each provenance as source}<li><strong>{source.phase}</strong> · <code>{source.source_relative_path}</code><br /><code>{source.source_sha256}</code></li>{/each}</ul>
</details>
<style>
	.scroll{max-width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12px}caption{text-align:left;color:#94a3b8;padding:8px}th,td{padding:9px;border-bottom:1px solid var(--nhm-border);text-align:left;vertical-align:top;overflow-wrap:anywhere;min-width:100px}th{color:#9fe7e1;font-weight:500}td{color:#a7b8c9}details{margin-top:20px;border:1px solid var(--nhm-border);padding:12px}summary{cursor:pointer;color:#2bb8b0;font:11px 'JetBrains Mono',monospace}summary:focus-visible{outline:2px solid #fbbf24}li{margin:12px 0;color:#a7b8c9;overflow-wrap:anywhere}code{font-size:11px;overflow-wrap:anywhere}@media(max-width:600px){table,thead,tbody,tr,th,td{display:block}thead{position:absolute;left:-9999px}tr{border-bottom:1px solid var(--nhm-border);padding:8px 0}th,td{border:0;min-width:0;padding:4px}}
</style>
