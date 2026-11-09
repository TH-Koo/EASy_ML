"use client";

import { ChevronRight, Search, Star } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { VERDICT_STEPS, verdictLevelFromText } from "@/lib/resultSummary";
import type { HistoryItem, WatchlistItem } from "@/types/auth";

/**
 * 내 기록 — 지금까지 확인한 제품과 북마크를 한 목록에서 본다.
 *
 * 북마크 페이지를 따로 두지 않는다. 북마크는 기록의 일부이므로 '★ 북마크'
 * 필터 하나면 된다. 다만 비로그인 때 분석해 저장한 북마크처럼 기록에 없는
 * 것은 그 필터 아래에 따로 보여 준다.
 *
 * 데이터는 부모가 가져온다. 여기서는 그리기와 거르기만 한다.
 */

type Filter = "all" | "bookmark" | 0 | 1 | 2;

const PILL = [
  "bg-[var(--claim-ok-soft)] text-[var(--claim-ok)]",
  "bg-[rgba(160,139,234,.16)] text-[#7f66dc]",
  "bg-[var(--claim-no-soft)] text-[var(--claim-no)]",
] as const;

/** 저장된 북마크가 이 기록을 가리키는가. 결과 링크로 저장한 것과 상품 주소로 저장한 것이 있다. */
export function bookmarkFor(item: HistoryItem, bookmarks: WatchlistItem[]): WatchlistItem | undefined {
  return bookmarks.find((b) => b.url === item.url || b.url.endsWith(`/history/${item.id}`));
}

function parseDate(s: string): Date | null {
  const d = new Date(s.includes("T") ? s : s.replace(" ", "T"));
  return Number.isNaN(d.getTime()) ? null : d;
}

function dayLabel(s: string): string {
  const d = parseDate(s);
  if (!d) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;
}

/** 오늘 · 어제 · 이번 주 · 그 전은 'YYYY년 M월' */
function groupLabel(s: string, now: Date): string {
  const d = parseDate(s);
  if (!d) return "날짜 없음";
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(d)) / 86_400_000);
  if (days <= 0) return "오늘";
  if (days === 1) return "어제";
  if (days < 7) return "이번 주";
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월`;
}

export function RecordsView({
  items,
  bookmarks,
  onToggleBookmark,
  onRemoveBookmark,
  now,
}: {
  items: HistoryItem[];
  bookmarks: WatchlistItem[];
  onToggleBookmark: (item: HistoryItem) => void;
  onRemoveBookmark: (bookmark: WatchlistItem) => void;
  /** 묶음(오늘 · 어제…)의 기준 시각 */
  now: Date;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const counts = useMemo(() => {
    const c = { all: items.length, bookmark: bookmarks.length, 0: 0, 1: 0, 2: 0 };
    for (const it of items) {
      const level = verdictLevelFromText(it.verdict);
      if (level !== null) c[level] += 1;
    }
    return c;
  }, [items, bookmarks]);

  const rows = items.filter((it) => {
    if (q && !it.product_name.toLowerCase().includes(q)) return false;
    if (filter === "all") return true;
    if (filter === "bookmark") return bookmarkFor(it, bookmarks) !== undefined;
    return verdictLevelFromText(it.verdict) === filter;
  });

  // 기록과 이어지지 않는 북마크(비로그인 때의 결과 등)는 북마크 필터에서만 따로 보여 준다.
  const orphans =
    filter === "bookmark"
      ? bookmarks.filter(
          (b) =>
            !items.some((it) => bookmarkFor(it, [b])) &&
            (!q || b.product_name.toLowerCase().includes(q)),
        )
      : [];

  const groups: { label: string; items: HistoryItem[] }[] = [];
  for (const it of rows) {
    const label = groupLabel(it.created_at, now);
    const last = groups[groups.length - 1];
    if (last?.label === label) last.items.push(it);
    else groups.push({ label, items: [it] });
  }

  const chips: { key: Filter; label: string; n: number }[] = [
    { key: "all", label: "전체", n: counts.all },
    { key: "bookmark", label: "★ 북마크", n: counts.bookmark },
    { key: 0, label: VERDICT_STEPS[0], n: counts[0] },
    { key: 1, label: VERDICT_STEPS[1], n: counts[1] },
    { key: 2, label: VERDICT_STEPS[2], n: counts[2] },
  ];

  return (
    <div className="theme-violet bg-surface flex flex-1 justify-center px-5 pt-14 pb-20">
      <div className="w-full max-w-[960px]">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-fg text-[clamp(28px,3.6vw,36px)] leading-tight font-bold tracking-[-0.03em]">
              내 기록
            </h1>
            <p className="text-fg-muted mt-2 text-[15px]">
              지금까지 확인한 제품 <b className="text-fg font-semibold tabular-nums">{counts.all}</b>개 · 북마크{" "}
              <b className="text-fg font-semibold tabular-nums">{counts.bookmark}</b>개
            </p>
          </div>
          <Link
            href="/"
            className="bg-brand rounded-[10px] px-4 py-2.5 text-sm font-bold text-white hover:brightness-110"
          >
            + 새 주소 확인
          </Link>
        </div>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <label className="bg-surface border-border focus-within:border-brand flex min-w-[220px] flex-1 items-center gap-2 rounded-[14px] border-[1.5px] px-3.5 transition-colors">
            <Search size={16} aria-hidden className="text-fg-dim shrink-0" />
            <span className="sr-only">제품 이름으로 찾기</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="제품 이름으로 찾기"
              className="text-fg placeholder:text-fg-dim min-w-0 flex-1 bg-transparent py-2.5 text-sm outline-none"
            />
          </label>
          <div role="group" aria-label="판정으로 거르기" className="flex flex-wrap gap-1.5">
            {chips.map((c) => (
              <button
                key={String(c.key)}
                type="button"
                aria-pressed={filter === c.key}
                onClick={() => setFilter(c.key)}
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-[13px] font-semibold transition-colors",
                  filter === c.key
                    ? "bg-brand border-transparent text-white"
                    : "border-border bg-surface text-fg-muted hover:border-brand hover:text-brand-fg",
                )}
              >
                {c.label} <span className="ml-0.5 font-medium tabular-nums opacity-70">{c.n}</span>
              </button>
            ))}
          </div>
        </div>

        {groups.length === 0 && orphans.length === 0 ? (
          <div className="bg-surface-strong text-fg-muted mt-7 rounded-[20px] px-6 py-14 text-center text-[15px]">
            {q || filter !== "all"
              ? filter === "bookmark" && !q
                ? "아직 북마크가 없어요. 목록에서 ★를 눌러 저장해 보세요."
                : "조건에 맞는 기록이 없어요."
              : "아직 확인한 제품이 없어요. 다나와 상품 주소를 넣어 첫 분석을 해 보세요."}
          </div>
        ) : null}

        {groups.map((g) => (
          <section key={g.label} className="mt-7">
            <h2 className="text-fg-dim mb-2 px-1 text-[13px] font-semibold">{g.label}</h2>
            <ul className="bg-surface-strong divide-border divide-y rounded-[20px] px-5">
              {g.items.map((it) => (
                <Row
                  key={it.id}
                  item={it}
                  on={bookmarkFor(it, bookmarks) !== undefined}
                  query={q}
                  onToggle={() => onToggleBookmark(it)}
                />
              ))}
            </ul>
          </section>
        ))}

        {orphans.length > 0 ? (
          <section className="mt-7">
            <h2 className="text-fg-dim mb-2 px-1 text-[13px] font-semibold">기록에 없는 북마크</h2>
            <ul className="bg-surface-strong divide-border divide-y rounded-[20px] px-5">
              {orphans.map((b) => (
                <li key={b.id} className="flex items-center gap-3 py-3.5">
                  <a href={b.url} className="hover:text-brand-fg text-fg min-w-0 flex-1 truncate text-[15px] font-semibold">
                    {b.product_name || b.url}
                  </a>
                  <StarButton on label={b.product_name} onClick={() => onRemoveBookmark(b)} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </div>
  );
}

function Row({
  item,
  on,
  query,
  onToggle,
}: {
  item: HistoryItem;
  on: boolean;
  query: string;
  onToggle: () => void;
}) {
  const level = verdictLevelFromText(item.verdict);
  return (
    <li className="group relative flex items-center gap-3 py-3.5 md:gap-4">
      <div className="min-w-0 flex-1">
        {/* 줄 전체를 눌러 결과로 간다. ★ 만 위로 올려 따로 눌리게 둔다. */}
        <Link
          href={`/history/${item.id}`}
          className="text-fg group-hover:text-brand-fg block truncate text-[15px] font-semibold after:absolute after:inset-0"
        >
          <Highlight text={item.product_name || "이름 없는 제품"} query={query} />
        </Link>
        <p className="text-fg-dim mt-0.5 truncate text-xs">{item.url}</p>
      </div>
      <span
        className={cn(
          "hidden shrink-0 rounded-full px-2.5 py-1 text-xs font-bold sm:inline",
          level !== null ? PILL[level] : "bg-surface text-fg-dim",
        )}
      >
        {level !== null ? `근거 ${VERDICT_STEPS[level]}` : "판정 제외"}
      </span>
      <time className="text-fg-dim hidden shrink-0 text-[13px] tabular-nums md:inline">{dayLabel(item.created_at)}</time>
      <StarButton on={on} label={item.product_name} onClick={onToggle} />
      <ChevronRight
        size={18}
        aria-hidden
        className="text-fg-dim shrink-0 transition-transform group-hover:translate-x-0.5"
      />
    </li>
  );
}

function StarButton({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      aria-label={`${label} ${on ? "북마크 해제" : "북마크에 저장"}`}
      className={cn(
        "relative z-10 shrink-0 rounded-md p-1 leading-none transition-colors",
        on ? "text-[#f2b01e]" : "text-fg-faint hover:text-[#f2b01e]",
      )}
    >
      <Star size={19} fill={on ? "currentColor" : "none"} aria-hidden />
    </button>
  );
}

function Highlight({ text, query }: { text: string; query: string }) {
  const at = query ? text.toLowerCase().indexOf(query) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="text-brand-fg rounded-[3px] bg-[var(--claim-ok-soft)]">{text.slice(at, at + query.length)}</mark>
      {text.slice(at + query.length)}
    </>
  );
}
