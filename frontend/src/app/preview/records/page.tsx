"use client";

import { useState } from "react";

import { RecordsView, bookmarkFor } from "@/components/records/RecordsView";
import type { HistoryItem, WatchlistItem } from "@/types/auth";

/** 내 기록 — 검토용. 백엔드와 로그인 없이 예시 데이터로 그린다. ★ 도 화면에서만 바뀐다. */

const NOW = new Date("2026-11-06T12:00:00");

function sample(id: number, product_name: string, verdict: string, created_at: string): HistoryItem {
  return {
    id,
    url: `https://prod.danawa.com/info/?pcode=${10000000 + id}`,
    product_name,
    company_name: "",
    verdict,
    accs_score: 0,
    risk_level: "",
    created_at,
    category: "",
    folder_id: null,
  };
}

const ITEMS = [
  sample(1, "예시 AI 세탁기 21kg", "높은 신뢰 상품 / Credible", "2026-11-06 10:12:00"),
  sample(2, "예시 AI 공기청정기 X1", "워싱 의심 상품 / Suspected", "2026-11-06 09:40:00"),
  sample(3, "예시 AI 로봇청소기", "신뢰 상품 / Normal", "2026-11-05 21:15:00"),
  sample(4, "예시 AI 무선청소기", "AI 워싱 상품 / Washing", "2026-11-03 18:03:00"),
  sample(5, "예시 AI 냉장고 800L", "워싱 의심 상품 / Suspected", "2026-10-22 13:00:00"),
  sample(6, "예시 일반 선풍기", "AI 기능 주장 미확인 / Not Evaluated", "2026-10-14 13:00:00"),
];

export default function RecordsPreviewPage() {
  const [bookmarks, setBookmarks] = useState<WatchlistItem[]>([
    { id: 1, url: "http://localhost:3001/history/2", product_name: "예시 AI 공기청정기 X1", added_at: "" },
  ]);
  return (
    <RecordsView
      items={ITEMS}
      bookmarks={bookmarks}
      now={NOW}
      onRemoveBookmark={(b) => setBookmarks((prev) => prev.filter((x) => x.id !== b.id))}
      onToggleBookmark={(it) => {
        const on = bookmarkFor(it, bookmarks);
        setBookmarks((prev) =>
          on
            ? prev.filter((x) => x.id !== on.id)
            : [{ id: 100 + it.id, url: `/history/${it.id}`, product_name: it.product_name, added_at: "" }, ...prev],
        );
      }}
    />
  );
}
