// Metric card definitions and honest value display (no rounding of source data, no silent zero-fill).
import type { EvalRecord, RoundEvalStatus } from './types';

export type Tone = 'value' | 'pending' | 'undefined' | 'failed';
export interface MetricDisplay { text: string; tone: Tone; full: string; reason: string | null }
export interface MetricDef { key: string; label: string; hint: string; format?: 'rate' | 'loss' | 'count' | 'ratio' }
export interface MetricGroup { id: string; title: string; items: MetricDef[] }

export const HEADLINE: MetricDef[] = [
	{ key: 'AUPRC', label: 'AUPRC', hint: 'average precision (non-interpolated)' }, { key: 'AUROC', label: 'AUROC', hint: 'area under the ROC curve' },
	{ key: 'F1', label: 'F1', hint: 'at the fixed 0.5 rule' }, { key: 'specificity', label: 'Specificity', hint: 'true-negative rate at 0.5' },
	{ key: 'recall', label: 'Recall', hint: 'sensitivity at 0.5' }, { key: 'accuracy', label: 'Accuracy', hint: 'at 0.5' },
	{ key: 'BCE', label: 'BCE', hint: 'unweighted binary cross-entropy (lower is better)', format: 'loss' }, { key: 'Brier', label: 'Brier', hint: 'mean squared probability error (lower is better)', format: 'loss' }
];

export const METRIC_GROUPS: MetricGroup[] = [
	{ id: 'ranking', title: 'Ranking', items: [{ key: 'AUPRC', label: 'AUPRC / average precision', hint: '' }, { key: 'AUROC', label: 'AUROC', hint: '' }] },
	{ id: 'threshold', title: 'Threshold classification (fixed 0.5, no calibration)', items: [
		{ key: 'F1', label: 'F1', hint: '' }, { key: 'accuracy', label: 'Accuracy', hint: '' }, { key: 'precision', label: 'Precision / PPV', hint: '' }, { key: 'recall', label: 'Recall / sensitivity', hint: '' },
		{ key: 'specificity', label: 'Specificity', hint: '' }, { key: 'balanced_accuracy', label: 'Balanced accuracy', hint: '' }, { key: 'negative_predictive_value', label: 'Negative predictive value', hint: '' },
		{ key: 'false_positive_rate', label: 'False-positive rate', hint: '' }, { key: 'false_negative_rate', label: 'False-negative rate', hint: '' }, { key: 'false_discovery_rate', label: 'False-discovery rate', hint: '' },
		{ key: 'false_omission_rate', label: 'False-omission rate', hint: '' }, { key: 'MCC', label: 'Matthews correlation', hint: '' }] },
	{ id: 'probability', title: 'Probability and loss', items: [
		{ key: 'BCE', label: 'Unweighted BCE', hint: '', format: 'loss' }, { key: 'Brier', label: 'Brier score', hint: '', format: 'loss' }, { key: 'mean_predicted_probability', label: 'Mean predicted probability', hint: '' },
		{ key: 'mean_score_positive_class', label: 'Mean score, positive class', hint: '' }, { key: 'mean_score_negative_class', label: 'Mean score, negative class', hint: '' }] },
	{ id: 'confusion', title: 'Confusion counts', items: [
		{ key: 'TP', label: 'TP', hint: '', format: 'count' }, { key: 'FP', label: 'FP', hint: '', format: 'count' }, { key: 'TN', label: 'TN', hint: '', format: 'count' }, { key: 'FN', label: 'FN', hint: '', format: 'count' },
		{ key: 'predicted_positives', label: 'Predicted positives', hint: '', format: 'count' }, { key: 'predicted_negatives', label: 'Predicted negatives', hint: '', format: 'count' }] },
	{ id: 'population', title: 'Population', items: [
		{ key: 'windows', label: 'Evaluation windows', hint: '', format: 'count' }, { key: 'positives', label: 'Positive examples', hint: '', format: 'count' }, { key: 'negatives', label: 'Negative examples', hint: '', format: 'count' },
		{ key: 'prevalence', label: 'Positive prevalence', hint: '' }] }
];

const PENDING_TEXT: Record<string, string> = { QUEUED: 'QUEUED', EVALUATING: 'EVALUATING', NOT_SUBMITTED: 'NOT YET AVAILABLE' };

export function statusFor(records: EvalRecord[], round: number): RoundEvalStatus {
	return records.find((r) => r.round_id === round)?.evaluation_status ?? 'NOT_SUBMITTED';
}

/** A displayed number is the source number printed at 6 decimals; the exact value is always available in `full`. */
export function display(record: EvalRecord | undefined, key: string, format: MetricDef['format'] = 'rate'): MetricDisplay {
	const status: RoundEvalStatus = record?.evaluation_status ?? 'NOT_SUBMITTED';
	if (status === 'FAILED') return { text: `FAILED — ${record?.failure?.code ?? 'unknown'}`, tone: 'failed', full: record?.failure?.message ?? '', reason: record?.failure?.message ?? null };
	if (status !== 'COMPLETED' || !record?.metric_result) return { text: PENDING_TEXT[status] ?? 'NOT YET AVAILABLE', tone: 'pending', full: '', reason: null };
	const value = record.metric_result[key];
	if (value === null || value === undefined) {
		const reasons = (record.metric_result.undefined ?? {}) as Record<string, string>;
		const reason = reasons[key] ?? 'not defined for this state';
		return { text: `UNDEFINED — ${reason}`, tone: 'undefined', full: '', reason };
	}
	if (typeof value !== 'number') return { text: String(value), tone: 'value', full: String(value), reason: null };
	const text = format === 'count' || Number.isInteger(value) ? String(value) : value.toFixed(6);
	return { text, tone: 'value', full: String(value), reason: null };
}
