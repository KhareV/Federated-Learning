import { array, fields, integer, literal, object, string } from '../evidence-validation';
import { parseSignalStage, type SignalStage } from './types';

export interface ResearchRecord {
	dataset_id: 'MITDB'; record_id: string; participant_group_id: string; partition: 'TRAIN';
	eligible_window_count: number; source_kind: 'FROZEN_PROCESSED_RESEARCH_CACHE';
}
export interface ResearchWindow {
	record: ResearchRecord; window_index: number; example_id: string;
	left_timestamp_us: number; right_timestamp_us: number;
	signal_interval: 'LEFT_CLOSED_RIGHT_OPEN'; annotation_interval: 'BOTH_CLOSED';
	stage: SignalStage; label_contract: 'AAMI_SVF_WINDOW_V1'; label: number; label_status: string;
	mapped_n_count: number; mapped_s_count: number; mapped_v_count: number; mapped_f_count: number;
	q_count: number; unmappable_count: number;
	annotation_positions_status: 'UNAVAILABLE_RAW_WFDB_NOT_PRESENT';
	cache_file_sha256: string; example_ids_file_sha256: string;
	window_manifest_sha256: string; split_manifest_sha256: string;
	claim_boundary: 'PROCESSED_TRAIN_WINDOW_NOT_HELD_OUT_INFERENCE';
}
function record(value: unknown, label: string): ResearchRecord {
	const x = object(value, label);
	fields(x, ['dataset_id','record_id','participant_group_id','partition','eligible_window_count','source_kind'], label);
	return { dataset_id: literal(x.dataset_id, 'MITDB', `${label}.dataset_id`),
		record_id: string(x.record_id, `${label}.record_id`),
		participant_group_id: string(x.participant_group_id, `${label}.participant_group_id`),
		partition: literal(x.partition, 'TRAIN', `${label}.partition`),
		eligible_window_count: integer(x.eligible_window_count, `${label}.eligible_window_count`),
		source_kind: literal(x.source_kind, 'FROZEN_PROCESSED_RESEARCH_CACHE', `${label}.source_kind`) };
}
export function parseResearchRecords(value: unknown): ResearchRecord[] {
	return array(value, record, 'research_records');
}
export function parseResearchWindow(value: unknown): ResearchWindow {
	const x = object(value, 'research_window');
	fields(x, ['record','window_index','example_id','left_timestamp_us','right_timestamp_us',
		'signal_interval','annotation_interval','stage','label_contract','label','label_status',
		'mapped_n_count','mapped_s_count','mapped_v_count','mapped_f_count','q_count',
		'unmappable_count','annotation_positions_status','cache_file_sha256',
		'example_ids_file_sha256','window_manifest_sha256','split_manifest_sha256','claim_boundary'],
		'research_window');
	const label = integer(x.label, 'research_window.label');
	if (label !== 0 && label !== 1) throw new Error('MALFORMED_RESEARCH_WINDOW_LABEL');
	return { record: record(x.record, 'research_window.record'),
		window_index: integer(x.window_index, 'research_window.window_index'),
		example_id: string(x.example_id, 'research_window.example_id'),
		left_timestamp_us: integer(x.left_timestamp_us, 'research_window.left_timestamp_us'),
		right_timestamp_us: integer(x.right_timestamp_us, 'research_window.right_timestamp_us'),
		signal_interval: literal(x.signal_interval, 'LEFT_CLOSED_RIGHT_OPEN', 'research_window.signal_interval'),
		annotation_interval: literal(x.annotation_interval, 'BOTH_CLOSED', 'research_window.annotation_interval'),
		stage: parseSignalStage(x.stage, 'research_window.stage'),
		label_contract: literal(x.label_contract, 'AAMI_SVF_WINDOW_V1', 'research_window.label_contract'),
		label, label_status: string(x.label_status, 'research_window.label_status'),
		mapped_n_count: integer(x.mapped_n_count, 'research_window.mapped_n_count'),
		mapped_s_count: integer(x.mapped_s_count, 'research_window.mapped_s_count'),
		mapped_v_count: integer(x.mapped_v_count, 'research_window.mapped_v_count'),
		mapped_f_count: integer(x.mapped_f_count, 'research_window.mapped_f_count'),
		q_count: integer(x.q_count, 'research_window.q_count'),
		unmappable_count: integer(x.unmappable_count, 'research_window.unmappable_count'),
		annotation_positions_status: literal(x.annotation_positions_status,
			'UNAVAILABLE_RAW_WFDB_NOT_PRESENT', 'research_window.annotation_positions_status'),
		cache_file_sha256: string(x.cache_file_sha256, 'research_window.cache_file_sha256'),
		example_ids_file_sha256: string(x.example_ids_file_sha256, 'research_window.example_ids_file_sha256'),
		window_manifest_sha256: string(x.window_manifest_sha256, 'research_window.window_manifest_sha256'),
		split_manifest_sha256: string(x.split_manifest_sha256, 'research_window.split_manifest_sha256'),
		claim_boundary: literal(x.claim_boundary, 'PROCESSED_TRAIN_WINDOW_NOT_HELD_OUT_INFERENCE',
			'research_window.claim_boundary') };
}
