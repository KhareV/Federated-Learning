<script lang="ts">
  import '../app.css';
  import { SmoothCursor } from '$lib/components/magic/smooth-cursor';
  import { afterNavigate } from '$app/navigation';
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();

  afterNavigate(({ to }) => {
    // Preserve native anchor navigation while making page-to-page transitions
    // settle into the same calm, editorial scroll used by the landing page.
    if (!to?.url.hash) window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
  });
</script>

<SmoothCursor />
{@render children()}
