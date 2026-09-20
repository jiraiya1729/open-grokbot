"use client";

import { useEffect, useRef, useState } from "react";

interface Notification {
  id: string;
  type: string;
  title: string;
  body?: string;
  entity_type?: string;
  entity_id?: string;
  read_at?: string;
  created_at: string;
}

const TYPE_ICONS: Record<string, string> = {
  routine_completed: "✓",
  routine_failed: "✕",
  approval_required: "⚠",
  needs_input: "●",
  default: "○",
};

function NotificationItem({
  notification,
  onRead,
}: {
  notification: Notification;
  onRead: (id: string) => void;
}) {
  const icon = TYPE_ICONS[notification.type] || TYPE_ICONS.default;
  const isUnread = !notification.read_at;
  const timeAgo = new Date(notification.created_at).toLocaleString();

  return (
    <div
      onClick={() => isUnread && onRead(notification.id)}
      style={{
        padding: "10px 12px",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        cursor: isUnread ? "pointer" : "default",
        background: isUnread ? "rgba(113,88,217,0.06)" : "transparent",
        display: "flex",
        gap: "10px",
        alignItems: "flex-start",
      }}
    >
      <span
        style={{
          fontSize: "14px",
          color: isUnread ? "#7158D9" : "var(--text-3, #6b7280)",
          flexShrink: 0,
          marginTop: "2px",
        }}
      >
        {icon}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "13px",
            fontWeight: isUnread ? 500 : 400,
            color: "var(--text-1, #e5e7eb)",
          }}
        >
          {notification.title}
        </div>
        {notification.body && (
          <div
            style={{
              fontSize: "11px",
              color: "var(--text-2, #9ca3af)",
              marginTop: "2px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {notification.body}
          </div>
        )}
        <div style={{ fontSize: "10px", color: "var(--text-3, #6b7280)", marginTop: "4px" }}>
          {timeAgo}
        </div>
      </div>
      {isUnread && (
        <div
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: "#7158D9",
            flexShrink: 0,
            marginTop: "6px",
          }}
        />
      )}
    </div>
  );
}

interface NotificationBellProps {
  apiBase?: string;
}

export function NotificationBell({ apiBase = "/api/v1" }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const fetchNotifications = async () => {
    try {
      const res = await fetch(`${apiBase}/notifications?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.items ?? []);
        setUnreadCount(data.unread_count ?? 0);
      }
    } catch {
      // silently ignore
    }
  };

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (!cancelled) await fetchNotifications();
    };
    poll();
    const interval = setInterval(poll, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const handleRead = async (id: string) => {
    try {
      await fetch(`${apiBase}/notifications/${id}/read`, { method: "POST" });
      setNotifications((prev) =>
        prev.map((n) =>
          n.id === id ? { ...n, read_at: new Date().toISOString() } : n
        )
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // silently ignore
    }
  };

  return (
    <div style={{ position: "relative" }} ref={panelRef}>
      <button
        onClick={() => {
          setOpen((s) => !s);
          if (!open) fetchNotifications();
        }}
        aria-label="Notifications"
        style={{
          position: "relative",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          padding: "6px",
          borderRadius: "6px",
          color: "var(--text-2, #9ca3af)",
          fontSize: "18px",
          lineHeight: 1,
        }}
      >
        🔔
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: "2px",
              right: "2px",
              minWidth: "14px",
              height: "14px",
              borderRadius: "7px",
              background: "#7158D9",
              color: "#fff",
              fontSize: "9px",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 2px",
            }}
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            width: "320px",
            maxHeight: "420px",
            overflowY: "auto",
            background: "var(--surface-0, #141414)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "10px",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              padding: "12px 14px",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: "14px" }}>Notifications</span>
            {unreadCount > 0 && (
              <span
                style={{
                  fontSize: "11px",
                  padding: "2px 6px",
                  borderRadius: "10px",
                  background: "rgba(113,88,217,0.2)",
                  color: "#7158D9",
                }}
              >
                {unreadCount} unread
              </span>
            )}
          </div>

          {loading ? (
            <div
              style={{ padding: "24px", textAlign: "center", color: "var(--text-3, #6b7280)", fontSize: "13px" }}
            >
              Loading…
            </div>
          ) : notifications.length === 0 ? (
            <div
              style={{ padding: "32px", textAlign: "center", color: "var(--text-3, #6b7280)", fontSize: "13px" }}
            >
              No notifications
            </div>
          ) : (
            notifications.map((n) => (
              <NotificationItem key={n.id} notification={n} onRead={handleRead} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
