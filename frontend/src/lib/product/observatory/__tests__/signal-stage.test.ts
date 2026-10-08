// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import SignalStageChart from '$lib/components/product/observatory/SignalStageChart.svelte';

afterEach(cleanup);

describe('bounded signal inspection', () => {
	it('preserves a null gap and exposes the selected actual sample value', async () => {
		const stage = {
			stage_id: 'SOURCE_OBSERVED', unit: 'synthetic mV convention', sample_rate_hz: 360,
			actual_point_count: 3, displayed_point_count: 3, display_is_decimated: false,
			points: [
				{ timestamp_us: 0, value: 1.25, source_index: 0 },
				{ timestamp_us: 2778, value: null, source_index: 1 },
				{ timestamp_us: 5556, value: -0.5, source_index: 2 }
			]
		};
		const view = render(SignalStageChart, { props: { stage, startUs: 0, endUs: 10_000 } });
		expect(view.container.querySelectorAll('path.wave')).toHaveLength(2);
		const cursor = screen.getByRole('slider', { name: 'Inspect a rendered point' });
		await fireEvent.input(cursor, { target: { value: '1' } });
		expect(screen.getByText(/MISSING \/ GAP/)).toBeTruthy();
		await fireEvent.input(cursor, { target: { value: '2' } });
		expect(screen.getByText(/-0\.500000 synthetic mV convention/)).toBeTruthy();
		expect(screen.getByText(/source index 2/)).toBeTruthy();
	});
});
