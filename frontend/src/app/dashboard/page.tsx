"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";

import { Button } from "@/components/primitives/Button";
import { Eyebrow } from "@/components/primitives/Eyebrow";
import {
  apiAddWatchlist,
  apiDeleteWatchlist,
  apiFetchDashboard,
  apiFetchHistory,
  apiFetchHistoryResult,
  apiFetchWatchlist,
  isSessionExpired,
} from "@/lib/api/auth";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import type { AnalysisResult } from "@/types/analysis";
import type {
  ClaimRollup,
  DashboardData,
  HistoryItem,
  WatchlistItem,
} from "@/types/auth";

/**
 * 대시보드.
 *
 * 구성(탭 · 검색 · 정렬 · 표 · 비교 모드 · 북마크)은 그대로 두고 조판만
 * 사이트의 나머지와 같은 언어로 옮겼다. 이전에는 이 파일 안에 500줄짜리
 * `<style>` 블록이 있었고 자체 팔레트(`#f4f6fb`·`#0e1120`·`#2563eb`)와
 * `'Inter'` · `'JetBrains Mono'` 를 직접 참조했다. 그래서 이 화면만 다른
 * 활자로 그려졌고, 우리가 JetBrains Mono 를 걷어낸 뒤로는 숫자 칸이 OS
 * 기본 모노로 떨어져 있었다.
 *
 * 표에서 고친 것:
 *   · `위험도` 칸에 위험도가 아니라 행 번호(01·02·03)가 찍히고 있었다
 *   · `성능` 칸이 `신뢰도 {accs}%` 였는데 같은 숫자가 이미 앞 칸에 있었다
 *   · `상태` 칸은 `HistoryItem` 에 status 필드가 없어 언제나 COMPLETE 였다
 *   · 등급을 accs_score 로 다시 계산하고 있었다 — 백엔드가 이미 판정한
 *     `risk_level` 과 `verdict` 를 그대로 쓴다. 판정 기준이 두 벌일 이유가 없다
 *
 * 등급은 백엔드의 한글 5단계를 판정 3색에 얹는다. 서비스 전체가
 * `확인 / 부분 / 없음` 셋으로만 말하기로 한 이상 여기만 다섯 색을 쓸 수 없다.
 */

/* ── 판정 ─────────────────────────────────────────────────────────── */

/** server.py 가 넣는 값 그대로. 앞뒤 공백과 표기 흔들림만 흡수한다. */
function riskTone(level: string): { color: string; label: string } {
  const v = (level || "").trim();
  if (v.includes("매우 낮") || v === "낮음")
    return { color: "var(--color-verified)", label: v || "—" };
  if (v.includes("보통")) return { color: "var(--color-partial)", label: v };
  if (v.includes("높")) return { color: "var(--color-missing)", label: v };
  return { color: "var(--color-fg-faint)", label: v || "—" };
}

/**
 * 주장 하나를 칸 하나로. /about 의 조회 매트릭스와 같은 언어다 —
 * 파랑 확인 · 노랑 부분 · 주황 근거 없음.
 *
 * 숫자 하나(ACCS)로 뭉개지 않고 "여섯 중 넷이 비었다"를 눈에 보이게 한다.
 * 그게 이 서비스의 결론이다.
 */
function ClaimBar({ claims }: { claims: ClaimRollup }) {
  const seg = [
    { n: claims.verified, c: "var(--color-verified)", label: "확인" },
    { n: claims.partial, c: "var(--color-partial)", label: "부분" },
    { n: claims.missing, c: "var(--color-missing)", label: "없음" },
  ];
  return (
    <span
      className="flex gap-[3px]"
      title={`주장 ${claims.total} · ${seg.map((s) => `${s.label} ${s.n}`).join(" · ")}`}
    >
      {seg.flatMap((s, si) =>
        Array.from({ length: s.n }).map((_, i) => (
          <span
            key={`${si}-${i}`}
            className="h-[6px] w-[9px] rounded-[1px]"
            style={{ background: s.c, opacity: si === 2 ? 1 : 0.55 }}
          />
        )),
      )}
    </span>
  );
}

function formatDate(s: string) {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

const LABEL =
  "font-mono text-xs tracking-[var(--tracking-label)] text-fg-faint";

/**
 * ⚠️ 배포 전 `true` 로 되돌릴 것.
 *
 * `false` 면 세션 없이도 대시보드가 열린다. 화면을 다듬는 동안 매번
 * 로그인할 수 없어 열어 뒀다.
 *
 * 데이터가 새지는 않는다 — 조회는 전부 토큰을 요구하는 API 로만
 * 이루어지고, 토큰이 없으면 아예 호출하지 않는다. 로그아웃 상태에서는
 * 빈 껍데기만 보인다. 그래도 `/dashboard` 주소가 누구에게나 열려 있으므로
 * 배포본에 이대로 나가면 안 된다.
 *
 * 이 파일에서 이 상수만 찾으면 되도록 한 곳에 모아 뒀다.
 */
const REQUIRE_LOGIN = false;

/* ── 페이지 ───────────────────────────────────────────────────────── */

export default function DashboardPage() {
  const router = useRouter();
  const { user, mounted } = useAuth();

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [bookmarks, setBookmarks] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"records" | "bookmarks">("records");
  const [compareMode, setCompareMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [summary, setSummary] = useState<DashboardData | null>(null);
  /** 펼친 행. 열 때 그 한 건만 상세를 부른다 */
  const [openRow, setOpenRow] = useState<number | null>(null);

  useEffect(() => {
    if (!mounted) return;
    if (!user) {
      /* 게이트는 파일 상단 `REQUIRE_LOGIN` 하나로 켜고 끈다 */
      if (REQUIRE_LOGIN) router.replace("/login");
      return;
    }
    /* 요약은 별도 엔드포인트가 이미 계산해 준다. 실패해도 표는 보여야
       하므로 목록과 따로 처리한다. */
    apiFetchDashboard(user.token)
      .then(setSummary)
      .catch(() => setSummary(null));

    Promise.all([apiFetchHistory(user.token), apiFetchWatchlist(user.token)])
      .then(([h, b]) => {
        setHistory(h);
        setBookmarks(b);
      })
      .catch((e) => {
        /* 토큰이 만료됐으면 여기 남아 있어도 할 수 있는 게 없다.
           헬퍼가 이미 세션을 지웠으므로 로그인으로 보낸다. */
        if (isSessionExpired(e)) {
          router.replace("/login");
          return;
        }
        setError(e instanceof Error ? e.message : "불러오지 못했습니다.");
      })
      .finally(() => setLoading(false));
  }, [mounted, user, router]);

  /* 로그아웃 상태에서는 부를 API 가 없으므로 로딩도 없다 */
  if (!mounted || (user && loading)) return <DashboardSkeleton />;

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 3) next.add(id);
      return next;
    });
  }

  function toggleCompareMode() {
    setCompareMode((m) => !m);
    setSelected(new Set());
  }

  const filtered = history
    .filter((item) => {
      const q = searchQuery.trim().toLowerCase();
      if (!q) return true;
      return (
        item.product_name.toLowerCase().includes(q) ||
        (item.company_name || "").toLowerCase().includes(q) ||
        (item.category || "").toLowerCase().includes(q)
      );
    })
    .sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      return sortOrder === "newest" ? tb - ta : ta - tb;
    });

  return (
    <div className="bg-bg flex flex-1 flex-col">
      <div className="mx-auto w-full max-w-[1200px] px-5 py-14 md:px-10">
        {/* 머리 */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Eyebrow>Dashboard</Eyebrow>
            <h1 className="text-fg mt-3 text-2xl font-medium tracking-[var(--tracking-heading)] md:text-[27px]">
              분석 현황
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="primary" size="sm">
              <Link href="/">새 분석</Link>
            </Button>
            <Button
              variant={compareMode ? "brand" : "secondary"}
              size="sm"
              onClick={toggleCompareMode}
            >
              {compareMode ? "선택 취소" : "비교보기"}
            </Button>
          </div>
        </div>

        {/* 실패는 빈 상태와 다른 상태다. 예전에는 둘이 함께 떠서 네트워크가
            끊긴 사용자가 자기 기록이 사라진 줄 알았다. */}
        {error ? (
          <p
            className="mt-8 border-t pt-4 text-xs leading-loose"
            style={{
              borderColor: "var(--color-missing)",
              color: "var(--color-missing)",
            }}
          >
            {error}
          </p>
        ) : null}

        {/* 탭 */}
        <div className="border-border mt-8 flex items-center gap-7 border-b">
          {(
            [
              ["records", "분석 기록", history.length],
              ["bookmarks", "북마크", bookmarks.length],
            ] as const
          ).map(([key, label, count]) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              aria-current={activeTab === key ? "true" : undefined}
              className={cn(
                "-mb-px border-b-2 pb-3 text-sm tracking-[var(--tracking-tight)] transition-colors",
                activeTab === key
                  ? "border-fg text-fg font-medium"
                  : "text-fg-dim hover:text-fg border-transparent",
              )}
            >
              {label}
              <span className="tnum text-fg-faint ml-1.5">{count}</span>
            </button>
          ))}
        </div>

        {activeTab === "records" ? (
          <>
            {/* 요약 — /about 이 가르친 결론 어법으로 연다.
                "몇 건을 봤나"가 아니라 "몇 건에 근거가 부족한가"가 먼저다. */}
            {summary && summary.summary.total > 0 ? (
              <div className="border-border mt-6 grid grid-cols-2 gap-x-8 gap-y-5 border-b pb-6 md:grid-cols-4">
                {[
                  {
                    k: "분석한 제품",
                    v: String(summary.summary.total),
                    sub: "전체 기록",
                  },
                  {
                    k: "근거 부족",
                    v: String(summary.summary.danger_count),
                    sub: "ACCS 35 미만",
                    color: "var(--color-missing)",
                  },
                  {
                    k: "검토 필요",
                    v: String(summary.summary.warn_count),
                    sub: "35 – 60",
                    color: "var(--color-partial)",
                  },
                  {
                    k: "근거 확인",
                    v: String(summary.summary.ok_count),
                    sub: "60 이상",
                    color: "var(--color-verified)",
                  },
                ].map((s) => (
                  <div key={s.k}>
                    <p className={LABEL}>{s.k}</p>
                    <p
                      className="tnum mt-2 text-[30px] leading-none font-medium tracking-[var(--tracking-display)]"
                      style={{ color: s.color ?? "var(--color-fg)" }}
                    >
                      {s.v}
                    </p>
                    <p className="text-fg-dim mt-2 text-xs">{s.sub}</p>
                  </div>
                ))}
              </div>
            ) : null}

            {/* 회사별 — AI 워싱을 제품이 아니라 회사 단위로 보게 한다 */}
            {summary && summary.by_company.length > 1 ? (
              <div className="border-border mt-6 border-b pb-6">
                <p className={LABEL}>회사별</p>
                <ul className="mt-3.5 flex flex-col gap-2.5">
                  {summary.by_company.slice(0, 5).map((c) => (
                    <li
                      key={c.company_name}
                      className="grid grid-cols-[minmax(0,1fr)_auto_110px_44px] items-center gap-4"
                    >
                      <span className="text-fg truncate text-sm tracking-[var(--tracking-tight)]">
                        {c.company_name}
                      </span>
                      <span className="text-fg-dim tnum text-xs">
                        {c.count}건
                      </span>
                      <span className="bg-border h-[3px] overflow-hidden rounded-full">
                        <span
                          className="block h-full rounded-full"
                          style={{
                            width: `${c.avg_score}%`,
                            background: riskTone(
                              c.avg_score >= 85
                                ? "낮음"
                                : c.avg_score >= 40
                                  ? "보통"
                                  : "높음",
                            ).color,
                          }}
                        />
                      </span>
                      <span
                        className="tnum text-right text-sm font-medium"
                        style={{
                          color: riskTone(
                            c.avg_score >= 85
                              ? "낮음"
                              : c.avg_score >= 40
                                ? "보통"
                                : "높음",
                          ).color,
                        }}
                      >
                        {c.avg_score.toFixed(1)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* 검색 · 정렬 */}
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="제품명, 브랜드, 카테고리 검색"
                aria-label="분석 기록 검색"
                className="border-border text-fg placeholder:text-fg-faint focus:border-border-strong h-9 min-w-[200px] flex-1 rounded-[var(--radius-input)] border bg-transparent px-3 text-sm outline-none"
              />
              <div className="border-border flex overflow-hidden rounded-[var(--radius-input)] border">
                {(
                  [
                    ["newest", "최신순"],
                    ["oldest", "오래된순"],
                  ] as const
                ).map(([key, label], i) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSortOrder(key)}
                    className={cn(
                      "h-9 px-3.5 text-xs transition-colors",
                      i > 0 && "border-border border-l",
                      sortOrder === key
                        ? "bg-surface text-fg font-medium"
                        : "text-fg-dim hover:text-fg",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {filtered.length === 0 ? (
              <div className="border-border mt-6 border-y py-16 text-center">
                <p className="text-fg-dim text-sm">
                  {searchQuery
                    ? "검색 결과가 없습니다"
                    : error
                      ? "기록을 불러오지 못했습니다"
                      : "아직 분석 기록이 없습니다"}
                </p>
                {!searchQuery && !error ? (
                  <Button asChild variant="secondary" size="sm" className="mt-5">
                    <Link href="/">첫 분석 시작하기</Link>
                  </Button>
                ) : null}
              </div>
            ) : (
              <table className="mt-6 w-full table-fixed border-collapse">
                <thead>
                  <tr className="border-border border-b">
                    {compareMode ? <th className="w-[36px]" /> : null}
                    <th className={cn(LABEL, "w-[30%] pb-3 text-left font-normal")}>
                      제품
                    </th>
                    <th className={cn(LABEL, "w-[13%] pb-3 text-left font-normal")}>
                      카테고리
                    </th>
                    <th className={cn(LABEL, "w-[13%] pb-3 text-left font-normal")}>
                      주장 · 근거
                    </th>
                    <th className={cn(LABEL, "w-[17%] pb-3 text-left font-normal")}>
                      판정
                    </th>
                    <th className={cn(LABEL, "w-[13%] pb-3 text-left font-normal")}>
                      위험도
                    </th>
                    <th className={cn(LABEL, "w-[10%] pb-3 text-right font-normal")}>
                      ACCS
                    </th>
                    <th className={cn(LABEL, "w-[11%] pb-3 text-right font-normal")}>
                      분석일
                    </th>
                    <th className="w-[28px]" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => {
                    const risk = riskTone(item.risk_level);
                    const sel = selected.has(item.id);
                    const open = openRow === item.id;
                    return (
                      <Fragment key={item.id}>
                      <tr
                        className={cn(
                          "border-border align-top",
                          open ? "" : "border-b",
                          (sel || open) && "bg-surface",
                        )}
                      >
                        {compareMode ? (
                          <td className="py-4">
                            <button
                              type="button"
                              role="checkbox"
                              aria-checked={sel}
                              aria-label={`${item.product_name} 비교 선택`}
                              onClick={() => toggleSelect(item.id)}
                              className={cn(
                                "grid size-[18px] place-items-center rounded-[4px] border text-[11px] transition-colors",
                                sel
                                  ? "border-brand bg-brand text-fg-on-brand"
                                  : "border-border-strong text-transparent",
                              )}
                            >
                              ✓
                            </button>
                          </td>
                        ) : null}

                        <td className="py-4 pr-6">
                          <Link
                            href={`/history/${item.id}`}
                            className="text-fg hover:text-brand-fg block text-sm tracking-[var(--tracking-tight)] transition-colors"
                          >
                            {item.product_name}
                          </Link>
                          <span className="text-fg-dim mt-0.5 block text-xs">
                            {item.company_name || "브랜드 미상"}
                          </span>
                        </td>

                        <td className="text-fg-dim py-4 pr-4 text-xs">
                          {item.category?.trim() || "미분류"}
                        </td>

                        <td className="py-4 pr-4">
                          {item.claims && item.claims.total > 0 ? (
                            <ClaimBar claims={item.claims} />
                          ) : (
                            <span className="text-fg-faint text-xs">—</span>
                          )}
                        </td>

                        <td className="text-fg-muted py-4 pr-4 text-xs leading-relaxed">
                          {item.verdict || "—"}
                        </td>

                        <td className="py-4 pr-4">
                          <span
                            className="inline-flex items-center gap-1.5 font-mono text-xs tracking-[var(--tracking-label)]"
                            style={{ color: risk.color }}
                          >
                            <span
                              className="size-[5px] shrink-0 rounded-full"
                              style={{ background: risk.color }}
                            />
                            {risk.label}
                          </span>
                        </td>

                        <td className="py-4 text-right">
                          <span
                            className="tnum text-sm font-medium"
                            style={{ color: risk.color }}
                          >
                            {item.accs_score.toFixed(1)}
                          </span>
                        </td>

                        <td className="text-fg-dim tnum py-4 text-right text-xs">
                          {formatDate(item.created_at)}
                        </td>

                        {/* 펼치기 — 여는 순간 그 한 건만 상세를 부른다.
                            목록 전체를 미리 부르면 요청이 행 수만큼 나간다. */}
                        <td className="py-4 pl-2 text-right">
                          <button
                            type="button"
                            onClick={() =>
                              setOpenRow((v) => (v === item.id ? null : item.id))
                            }
                            aria-expanded={open}
                            aria-label={`${item.product_name} 상세`}
                            className="text-fg-faint hover:text-fg text-xs transition-colors"
                          >
                            {open ? "▲" : "▼"}
                          </button>
                        </td>
                      </tr>

                      {open && user ? (
                        <tr className="border-border bg-surface border-b">
                          <td
                            colSpan={compareMode ? 9 : 8}
                            className="px-1 pt-1 pb-6"
                          >
                            <RowDetail id={item.id} token={user.token} />
                          </td>
                        </tr>
                      ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        ) : (
          /* ── 북마크 ── */
          <div className="mt-6">
            {user ? (
              <AddBookmarkForm
                token={user.token}
                onAdd={(item) => setBookmarks((prev) => [item, ...prev])}
              />
            ) : (
              <p className="border-border text-fg-dim border-y py-16 text-center text-sm">
                북마크는 로그인한 뒤에 쓸 수 있습니다
              </p>
            )}

            {user ? (
              bookmarks.length === 0 ? (
                <p className="border-border text-fg-dim border-y py-16 text-center text-sm">
                  저장된 북마크가 없습니다
                </p>
              ) : (
                <ul className="border-border divide-border divide-y border-y">
                  {bookmarks.map((bm) => (
                    <BookmarkRow
                      key={bm.id}
                      item={bm}
                      token={user.token}
                      onDelete={(id) =>
                        setBookmarks((prev) => prev.filter((b) => b.id !== id))
                      }
                    />
                  ))}
                </ul>
              )
            ) : null}
          </div>
        )}
      </div>

      {/* 비교 바 */}
      {compareMode && selected.size >= 2 ? (
        <div className="bg-ink fixed bottom-7 left-1/2 z-30 flex -translate-x-1/2 items-center gap-5 rounded-[var(--radius-card)] px-5 py-3.5 text-white shadow-[var(--shadow-panel)]">
          <span className="text-xs text-white/70">
            <span className="tnum font-medium text-white">{selected.size}개</span>{" "}
            선택됨
          </span>
          <button
            type="button"
            onClick={() => router.push(`/compare?ids=${[...selected].join(",")}`)}
            className="text-fg rounded-[var(--radius-input)] bg-white px-3.5 py-1.5 text-xs font-medium"
          >
            비교하기
          </button>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            aria-label="선택 해제"
            className="text-white/50 transition-colors hover:text-white"
          >
            ✕
          </button>
        </div>
      ) : null}
    </div>
  );
}

/* ── 행 상세 ──────────────────────────────────────────────────────── */

/**
 * 펼친 행 안에 그 한 건의 3채널 점수와 소스별 조회 결과를 편다.
 *
 * 목록 응답(`/api/history`)에는 ACCS 하나뿐이라, /about 이 가르친
 * "무엇이 비었나"를 목록만으로는 말할 수 없다. 상세 응답에는 3축 점수와
 * 소스별 결과가 들어 있으므로, 열어 본 행에 한해서만 가져온다.
 *
 * 채널 이름은 analysis_engine 의 소스 묶음을 그대로 따른다 —
 * TES(KIPRIS·DART)=기술 근거, HES(KC·RRA)=공인 인증,
 * CES(TIPA·KORAIA·GS·NEP·조달청)=기관 이력.
 *
 * 주장별 격자는 여기서 못 만든다. 백엔드가 직렬화할 때 claims 를 버려서
 * 상세 응답에도 들어 있지 않다.
 */
function RowDetail({ id, token }: { id: number; token: string }) {
  const [data, setData] = useState<AnalysisResult | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    apiFetchHistoryResult(token, id)
      .then((r) => alive && setData(r))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [id, token]);

  if (failed)
    return (
      <p className="text-fg-dim px-2 py-4 text-xs">
        상세를 불러오지 못했습니다.
      </p>
    );
  if (!data)
    return (
      <p className="text-fg-faint px-2 py-4 text-xs">불러오는 중…</p>
    );

  const channels = [
    { k: "기술 근거", sub: "KIPRIS 특허 · DART 공시", v: data.scores.text_credibility },
    { k: "공인 인증", sub: "KC 인증 · 전파인증 RRA", v: data.scores.verification_credibility },
    { k: "기관 이력", sub: "TIPA · KORAIA · GS · NEP · 조달청", v: data.scores.relational_credibility },
  ];
  const tone = (v: number) =>
    v < 35
      ? "var(--color-missing)"
      : v < 60
        ? "var(--color-partial)"
        : "var(--color-verified)";

  return (
    <div className="grid grid-cols-1 gap-x-12 gap-y-6 px-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div>
        <p className={LABEL}>채널별 신뢰도</p>
        <ul className="mt-3 flex flex-col gap-3">
          {channels.map((c) => (
            <li key={c.k} className="grid grid-cols-[minmax(0,1fr)_90px_42px] items-center gap-3">
              <span>
                <span className="text-fg block text-xs tracking-[var(--tracking-tight)]">
                  {c.k}
                </span>
                <span className="text-fg-dim mt-0.5 block text-xs">{c.sub}</span>
              </span>
              <span className="bg-border h-[3px] overflow-hidden rounded-full">
                <span
                  className="block h-full rounded-full"
                  style={{ width: `${c.v}%`, background: tone(c.v) }}
                />
              </span>
              <span
                className="tnum text-right text-xs font-medium"
                style={{ color: tone(c.v) }}
              >
                {c.v.toFixed(1)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className={LABEL}>소스별 조회 결과</p>
        <ul className="border-border divide-border mt-3 divide-y border-t">
          {data.verification.rows.map((r) => (
            <li key={r.key} className="flex items-center justify-between py-2">
              <span className="text-fg text-xs">{r.key}</span>
              <span
                className="text-xs"
                style={{
                  color:
                    r.intent === "ok"
                      ? "var(--color-verified)"
                      : r.intent === "warn"
                        ? "var(--color-missing)"
                        : "var(--color-fg-dim)",
                }}
              >
                {r.value}
              </span>
            </li>
          ))}
        </ul>
        <Link
          href={`/history/${id}`}
          className="text-brand-fg mt-3 inline-block text-xs underline-offset-4 hover:underline"
        >
          전체 결과 보기 →
        </Link>
      </div>
    </div>
  );
}

/* ── 북마크 추가 ──────────────────────────────────────────────────── */

function AddBookmarkForm({
  token,
  onAdd,
}: {
  token: string;
  onAdd: (i: WatchlistItem) => void;
}) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const urlRef = useRef<HTMLInputElement>(null);

  async function handleAdd() {
    if (!url.trim()) {
      setErr("URL을 입력해 주세요.");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const item = await apiAddWatchlist(token, url.trim(), name.trim());
      onAdd(item);
      setUrl("");
      setName("");
      urlRef.current?.focus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "추가 실패");
    } finally {
      setBusy(false);
    }
  }

  const field =
    "border-border text-fg placeholder:text-fg-faint focus:border-border-strong h-9 rounded-[var(--radius-input)] border bg-transparent px-3 text-sm outline-none";

  return (
    <div className="border-border mb-6 border-b pb-6">
      <div className="flex flex-wrap gap-2.5">
        <input
          ref={urlRef}
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="https://prod.danawa.com/info/?pcode=…"
          aria-label="제품 URL"
          className={cn(field, "min-w-[240px] flex-[2]")}
        />
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="제품 이름 (선택)"
          aria-label="제품 이름"
          className={cn(field, "min-w-[140px] flex-1")}
        />
        <Button variant="primary" size="sm" onClick={handleAdd} disabled={busy}>
          {busy ? "저장 중" : "저장"}
        </Button>
      </div>
      {err ? (
        <p className="mt-2.5 text-xs" style={{ color: "var(--color-missing)" }}>
          {err}
        </p>
      ) : null}
    </div>
  );
}

/* ── 북마크 한 줄 ─────────────────────────────────────────────────── */

function BookmarkRow({
  item,
  token,
  onDelete,
}: {
  item: WatchlistItem;
  token: string;
  onDelete: (id: number) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function handleAnalyze() {
    setBusy(true);
    try {
      const { startAnalysis } = await import("@/lib/api");
      const { analysis_id } = await startAnalysis(item.url, token);
      router.push(`/analysis/${analysis_id}`);
    } catch {
      setBusy(false);
    }
  }

  return (
    <li className="flex items-center gap-4 py-4">
      <div className="min-w-0 flex-1">
        <p className="text-fg truncate text-sm tracking-[var(--tracking-tight)]">
          {item.product_name || "제품명 미설정"}
        </p>
        <p className="text-fg-faint mt-0.5 truncate font-mono text-xs">
          {item.url}
        </p>
      </div>
      <span className="text-fg-dim tnum hidden shrink-0 text-xs sm:block">
        {item.added_at}
      </span>
      <Button
        variant="secondary"
        size="sm"
        onClick={handleAnalyze}
        disabled={busy}
      >
        {busy ? "시작 중" : "분석"}
      </Button>
      <button
        type="button"
        onClick={() => {
          /* 서버가 지운 걸 확인한 뒤에 화면에서 뺀다. 예전에는 응답을
             기다리지도 확인하지도 않아서, 실패해도 사라진 것처럼 보였다가
             새로고침하면 되살아났다. */
          apiDeleteWatchlist(token, item.id)
            .then(() => onDelete(item.id))
            .catch(() => {});
        }}
        aria-label={`${item.product_name || item.url} 삭제`}
        className="text-fg-faint shrink-0 px-1 transition-colors hover:text-[color:var(--color-missing)]"
      >
        ✕
      </button>
    </li>
  );
}

/* ── 스켈레톤 ─────────────────────────────────────────────────────── */

function DashboardSkeleton() {
  return (
    <div className="bg-bg flex flex-1 flex-col">
      <div className="mx-auto w-full max-w-[1200px] px-5 py-14 md:px-10">
        <div className="bg-surface-strong h-3.5 w-24 animate-pulse rounded-full" />
        <div className="bg-surface-strong mt-4 h-7 w-40 animate-pulse rounded-full" />
        <div className="border-border mt-14 border-t">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="border-border border-b py-5">
              <div className="bg-surface-strong h-3.5 w-[38%] animate-pulse rounded-full" />
              <div className="bg-surface-strong mt-2 h-3 w-[22%] animate-pulse rounded-full" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
