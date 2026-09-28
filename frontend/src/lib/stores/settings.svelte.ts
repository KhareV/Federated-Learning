export const settingsState = $state({ theme: 'dark' as 'dark' | 'light', anomalyThreshold: 0.7, sqiThreshold: 60, flRounds: 100 });

export function toggleTheme() { settingsState.theme = settingsState.theme === 'dark' ? 'light' : 'dark'; }