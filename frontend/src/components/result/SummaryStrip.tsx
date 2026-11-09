"use client";

import { ArrowDown, ArrowRight } from "lucide-react";
import Link from "next/link";

import { recordTally, sortClaims } from "@/lib/resultSummary";
import type { AnalysisResult } from "@/types/analysis";

/**
 * 결론 타일 바로 아래 요약 띠.
 *
 * 정보 칸은 흰 바탕에 선으로만 나누고, 누를 수 있는 것은 색을 채운 칸
 * 하나다. 그 칸은 지금 결과에서 바로 이어지는 행동이다 — 미확인 기능이
 * 있으면 "왜 미확인인지" 아래 팩트체크로 데려가고, 없으면 다른 제품을
 * 검색하러 간다. 같은 카테고리 비교는 보류해 두었다.
 */
export function SummaryStrip({ data }: { data: AnalysisResult }) {
  const sources = data.verification.rows.length;
  const claims = data.claims ?? [];
  const tally = recordTally(claims);
  const firstMissing = sortClaims(claims, true).find((c) => c.status === "unsupported");
  const missing = claims.filter((c) => c.status === "unsupported").length;
  const peak = Math.max(1, ...tally.kinds.map(([, n]) => n));

  return (
    <section
      aria-label="분석 요약"
      className="bg-surface grid overflow-hidden rounded-[var(--radius-panel)] shadow-[var(--shadow-panel)] md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
    >
      {claims.length > 0 ? (
        <div className="flex min-w-0 flex-col gap-0.5 px-6 py-4">
          <span className="text-fg-dim text-[12.5px] font-medium">찾은 공공 기록</span>
          <span className="text-fg text-lg font-bold tracking-[var(--tracking-tight)] tabular-nums">
            {tally.total}건
          </span>
          {tally.kinds.length > 0 ? (
            <ul aria-hidden className="mt-1.5 flex flex-col gap-1">
              {tally.kinds.slice(0, 3).map(([kind, n]) => (
                <li key={kind} className="grid grid-cols-[34px_minmax(0,1fr)_24px] items-center gap-2 text-xs">
                  <span className="text-fg-muted">{kind}</span>
                  <i className="bg-fg-muted block h-1.5 rounded-full" style={{ width: `${(n / peak) * 100}%` }} />
                  <span className="text-fg-muted text-right font-semibold tabular-nums">{n}</span>
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-fg-dim text-[12.5px]">광고와 맞는 기록을 찾지 못했어요</span>
          )}
        </div>
      ) : null}
      <Cell
        label="확인한 곳"
        value={sources > 0 ? `공공기관 ${sources}곳` : "공공기관"}
        note="특허청 · 금융감독원 · 인증 기관 등"
        className={claims.length > 0 ? "border-border border-t md:border-t-0 md:border-l" : undefined}
      />
      <Cell
        label="기준일"
        value={data.product.analysis_date.replaceAll("-", ".")}
        note="이후 등록된 기록은 빠져 있어요"
        className="border-border border-t md:border-t-0 md:border-l"
      />
      {firstMissing ? (
        <button
          type="button"
          onClick={() => openClaim(firstMissing.id)}
          className="flex items-center justify-between gap-4 px-6 py-4 text-left text-[15px] leading-snug font-bold text-white hover:brightness-110 md:justify-start"
          style={{ background: "var(--color-brand)" }}
        >
          <span>
            미확인 근거 {missing}개,
            <br className="hidden md:inline" /> 이유 보기
          </span>
          <ArrowDown size={18} aria-hidden />
        </button>
      ) : (
        <Link
          href="/"
          className="flex items-center justify-between gap-4 px-6 py-4 text-[15px] font-bold text-white hover:brightness-110 md:justify-start"
          style={{ background: "var(--color-brand)" }}
        >
          다른 제품 검색하기
          <ArrowRight size={18} aria-hidden />
        </Link>
      )}
    </section>
  );
}

/** 팩트체크의 그 기능 칸을 펼치고 그리로 내려간다. 접힌 '나머지' 묶음 안에 있어도 연다. */
function openClaim(id: string) {
  const el = document.getElementById(`claim-${id}`);
  if (!el) return;
  for (let p: HTMLElement | null = el; p; p = p.parentElement) {
    if (p instanceof HTMLDetailsElement) p.open = true;
  }
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function Cell({
  label,
  value,
  note,
  className,
}: {
  label: string;
  value: string;
  note: string;
  className?: string;
}) {
  return (
    <div className={`flex min-w-0 flex-col gap-0.5 px-6 py-4 ${className ?? ""}`}>
      <span className="text-fg-dim text-[12.5px] font-medium">{label}</span>
      <span className="text-fg text-lg font-bold tracking-[var(--tracking-tight)] tabular-nums">
        {value}
      </span>
      <span className="text-fg-dim text-[12.5px]">{note}</span>
    </div>
  );
}
