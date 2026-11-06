"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MaybeAppShell } from "@/components/app/MaybeAppShell";
import { RecordsView, bookmarkFor } from "@/components/records/RecordsView";
import {
  apiAddWatchlist,
  apiDeleteWatchlist,
  apiFetchHistory,
  apiFetchWatchlist,
  isSessionExpired,
} from "@/lib/api/auth";
import { useAuth } from "@/lib/auth";
import { loginHref } from "@/lib/loginLink";
import type { HistoryItem, WatchlistItem } from "@/types/auth";

/**
 * 내 기록. 기록은 계정에 쌓이므로 비로그인이면 로그인으로 보내고, 끝나면
 * 이 화면으로 돌아온다.
 */
export default function HistoryPage() {
  const router = useRouter();
  const { user, mounted } = useAuth();
  const [data, setData] = useState<{ items: HistoryItem[]; bookmarks: WatchlistItem[]; now: Date } | null>(null);
  const [failed, setFailed] = useState(false);
  const token = user?.token;

  useEffect(() => {
    if (!mounted) return;
    if (!token) {
      router.replace(loginHref("/history"));
      return;
    }
    let alive = true;
    Promise.all([apiFetchHistory(token), apiFetchWatchlist(token)])
      .then(([items, bookmarks]) => {
        if (alive) setData({ items, bookmarks, now: new Date() });
      })
      .catch((e) => {
        if (!alive) return;
        if (isSessionExpired(e)) router.replace(loginHref("/history"));
        else setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [mounted, token, router]);

  const setBookmarks = (fn: (prev: WatchlistItem[]) => WatchlistItem[]) =>
    setData((d) => (d ? { ...d, bookmarks: fn(d.bookmarks) } : d));

  /* 누르면 먼저 화면을 바꾸고, 서버가 거절하면 되돌린다. */
  async function remove(bookmark: WatchlistItem) {
    if (!token) return;
    setBookmarks((prev) => prev.filter((b) => b.id !== bookmark.id));
    try {
      await apiDeleteWatchlist(token, bookmark.id);
    } catch {
      setBookmarks((prev) => [bookmark, ...prev]);
    }
  }

  async function toggle(item: HistoryItem) {
    if (!token || !data) return;
    const existing = bookmarkFor(item, data.bookmarks);
    if (existing) return remove(existing);

    const url = `${window.location.origin}/history/${item.id}`;
    const temp: WatchlistItem = { id: -item.id, url, product_name: item.product_name, added_at: "" };
    setBookmarks((prev) => [temp, ...prev]);
    try {
      const saved = await apiAddWatchlist(token, url, item.product_name);
      setBookmarks((prev) => prev.map((b) => (b.id === temp.id ? saved : b)));
    } catch {
      setBookmarks((prev) => prev.filter((b) => b.id !== temp.id));
    }
  }

  return (
    <MaybeAppShell signedOutChrome="site">
      {data ? (
        <RecordsView
          items={data.items}
          bookmarks={data.bookmarks}
          now={data.now}
          onToggleBookmark={toggle}
          onRemoveBookmark={remove}
        />
      ) : (
        <p role="status" className="text-fg-muted flex-1 px-5 py-20 text-center text-[15px]">
          {failed ? "기록을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요." : "기록을 불러오는 중…"}
        </p>
      )}
    </MaybeAppShell>
  );
}
