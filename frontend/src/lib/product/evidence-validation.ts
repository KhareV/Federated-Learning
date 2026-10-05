// CAP-009 boundary helpers: reject malformed untrusted history/research JSON visibly.
export type JsonRecord = Record<string, unknown>;

export function object(value: unknown, label: string): JsonRecord {
	if (value === null || typeof value !== 'object' || Array.isArray(value)) {
		throw new Error(`MALFORMED_EVIDENCE:${label}:object`);
	}
	return value as JsonRecord;
}

export function fields(value: JsonRecord, allowed: readonly string[], label: string): void {
	for (const key of Object.keys(value)) {
		if (!allowed.includes(key)) throw new Error(`MALFORMED_EVIDENCE:${label}:unexpected:${key}`);
	}
}

export function string(value: unknown, label: string): string {
	if (typeof value !== 'string') throw new Error(`MALFORMED_EVIDENCE:${label}:string`);
	return value;
}

export function number(value: unknown, label: string): number {
	if (typeof value !== 'number' || !Number.isFinite(value))
		throw new Error(`MALFORMED_EVIDENCE:${label}:number`);
	return value;
}

export function integer(value: unknown, label: string): number {
	const n = number(value, label);
	if (!Number.isSafeInteger(n)) throw new Error(`MALFORMED_EVIDENCE:${label}:integer`);
	return n;
}

export function bool(value: unknown, label: string): boolean {
	if (typeof value !== 'boolean') throw new Error(`MALFORMED_EVIDENCE:${label}:boolean`);
	return value;
}

export function nullable<T>(value: unknown, parse: (v: unknown, l: string) => T, label: string): T | null {
	return value === null ? null : parse(value, label);
}

export function array<T>(value: unknown, parse: (v: unknown, l: string) => T, label: string): T[] {
	if (!Array.isArray(value)) throw new Error(`MALFORMED_EVIDENCE:${label}:array`);
	return value.map((item, i) => parse(item, `${label}[${i}]`));
}

export function literal<T extends string>(value: unknown, expected: T, label: string): T {
	if (value !== expected) throw new Error(`MALFORMED_EVIDENCE:${label}:literal`);
	return expected;
}
