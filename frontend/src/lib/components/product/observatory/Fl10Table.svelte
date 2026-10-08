<script lang="ts">
	import { cell, sha256Hex, tableToCsv, tableToMarkdown, type Fl10Table } from '$lib/product/observatory/fl10';
	let { table, open = false }: { table: Fl10Table; open?: boolean } = $props();
	let digest = $state<string | null>(null);
	function save(name: string, text: string, mime: string) {
		const url = URL.createObjectURL(new Blob([text], { type: mime }));
		const a = document.createElement('a'); a.href = url; a.download = name; a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
	async function exportCsv() { const text = tableToCsv(table); digest = await sha256Hex(text); save(`${table.id}.csv`, text, 'text/csv'); }
	async function exportJson() {
		const text = JSON.stringify({ table_id: table.id, title: table.title, caption: table.caption, synthetic_label: table.synthetic_label, columns: table.columns, rows: table.rows, sources: table.sources, undefined_policy: 'null = UNDEFINED / NOT CAPTURED (never zero)' }, null, 1) + '\n';
		digest = await sha256Hex(text); save(`${table.id}.json`, text, 'application/json');
	}
	async function exportMarkdown() {
		const text = tableToMarkdown(table);
		digest = await sha256Hex(text);
		save(`${table.id}.md`, text, 'text/markdown');
	}
</script>
<section class="tbl" data-testid={`table-${table.id}`}>
	<details {open}><summary><b>{table.id.replace('FL10_', '')}</b> · {table.title} <small>({table.rows.length} rows × {table.columns.length} columns)</small></summary>
		<p class="cap">{table.caption}</p><p class="syn">{table.synthetic_label}</p>
		<div class="bar"><button onclick={() => void exportCsv()}>Export CSV (full precision)</button><button onclick={() => void exportJson()}>Export JSON</button><button onclick={() => void exportMarkdown()}>Export Markdown</button>{#if digest}<small>SHA256 <code>{digest.slice(0, 16)}…</code></small>{/if}</div>
		<div class="scroll" tabindex="0" role="region" aria-label={`${table.title} data`}><table><thead><tr>{#each table.columns as c}<th scope="col">{c}</th>{/each}</tr></thead>
			<tbody>{#each table.rows as r}<tr>{#each r as v, i}{#if i === 0}<th scope="row">{cell(v, 4)}</th>{:else}<td class:undef={v === null}>{cell(v, 4)}</td>{/if}{/each}</tr>{/each}</tbody></table></div>
		<p class="dim">Displayed rounded to 4 decimals for reading; exports keep full precision. Sources: {table.sources.join(', ')}.</p></details>
</section>
<style>
	.tbl{border:1px solid rgba(148,163,184,.22);padding:8px 12px;background:rgba(10,15,31,.4);min-width:0}summary{cursor:pointer;color:#e2e8f0;font-size:13px}small,.dim{color:#94a3b8;font-size:11px}.cap{color:#a7b8c9;font-size:12px;margin:6px 0}.syn{display:inline-block;border:1px solid rgba(167,139,250,.55);padding:3px 8px;color:#d8ccff;font:10px 'JetBrains Mono',monospace;margin:0 0 6px}
	.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0}button{background:#0a0f1f;color:#e2e8f0;border:1px solid rgba(148,163,184,.35);padding:5px 10px;min-height:30px;font:11px 'JetBrains Mono',monospace;cursor:pointer}.scroll{overflow:auto;max-height:420px;max-width:100%}
	table{border-collapse:collapse;font-size:11px}th,td{border-bottom:1px solid rgba(148,163,184,.15);padding:4px 9px;text-align:left;white-space:nowrap;color:#cbd5e1}thead th{position:sticky;top:0;background:#0a0f1f;color:#71829a;font:10px 'JetBrains Mono',monospace}tbody th{position:sticky;left:0;background:#0a0f1f;color:#e2e8f0}td.undef{color:#f87171}code{color:#9fe7e1}
</style>
