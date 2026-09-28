import type { Notification } from '$lib/types';

export const notificationState = $state<{ items: Notification[] }>({ items: [] });
export const unreadCount = $derived(notificationState.items.filter((item) => !item.is_read).length);
export function setNotifications(items: Notification[]) { notificationState.items = items; }