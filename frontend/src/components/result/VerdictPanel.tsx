import { ArrowUpRight } from "lucide-react";

import { VerdictClaimList } from "@/components/result/VerdictClaimList";
import { cn } from "@/lib/cn";
import {
  SCORE_ZONES,
  VERDICT_COLOR,
  VERDICT_STEPS,
  countByStatus,
  headline,
  sortClaims,
  verdictLevel,
  verdictTitle,
} from "@/lib/resultSummary";
import type { AnalysisResult } from "@/types/analysis";

/**
 * 결과 화면 맨 위 결론 타일.
 *
 * 판정과 기능별 결과를 한 타일에 둔다. 왼쪽은 "그래서 어떤가", 오른쪽은
 * "무엇이 되고 무엇이 안 됐나"다. 흰 카드 위에서 색은 판정 하나만 말한다 —
 * 큰 판정 글씨와 점수 막대의 지금 구간이 같은 판정 색이고, 나머지는
 * 검정·회색이다.
 */
export function VerdictPanel({ data }: { data: AnalysisResult }) {
  const level = verdictLevel(data.scores.overall_label);
  // 실제 분석은 주장이 수십 개 나온다. 문제가 되는 것부터 몇 개만 보이고
  // 나머지는 그 자리에서 펼친다(VerdictClaimList).
  const claims = sortClaims(data.claims ?? [], true);
  const counts = countByStatus(claims);
  const url = data.product.url;

  return (
    <section
      aria-label="분석 결론"
      className="bg-surface grid gap-6 rounded-[var(--radius-panel)] p-6 shadow-[var(--shadow-panel)] md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] md:items-start md:gap-8 md:p-8"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <p className="text-fg text-[21px] leading-snug font-bold tracking-[var(--tracking-heading)]">
            {data.product.name}
          </p>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              title={url}
              className="border-border text-fg-muted hover:border-brand hover:text-brand-fg inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors"
            >
              다나와에서 보기
              <ArrowUpRight size={13} aria-hidden />
            </a>
          ) : null}
        </div>
        <h1
          className="mt-2 text-[34px] leading-tight font-extrabold tracking-[var(--tracking-display)] md:text-[40px]"
          style={{ color: level !== null ? VERDICT_COLOR[level] : undefined }}
        >
          {verdictTitle(data.scores.overall_label)}
        </h1>
        <p className="text-fg-muted mt-1 text-[15px]">{headline(data)}</p>

        {level !== null ? <ScoreBar score={data.scores.overall} level={level} /> : null}

        <p className="text-fg-dim mt-4 text-[12.5px]">
          제품 성능이 아니라 광고 문구가 공공 기록과 맞는지 본 결과예요
        </p>
      </div>

      {claims.length > 0 ? (
        <div className="bg-surface-strong min-w-0 rounded-[14px] px-4 py-3.5">
          <p className="border-border text-fg-muted flex flex-wrap gap-3.5 border-b px-1 pb-2.5 text-[13px]">
            <Count dot="bg-[var(--claim-ok)]" label="확인" n={counts.verified} />
            <Count dot="bg-[var(--claim-part)]" label="일부" n={counts.partial} />
            <Count dot="bg-[var(--claim-no)]" label="미확인" n={counts.unsupported} />
          </p>
          <StatusBar counts={counts} total={claims.length} />
          <VerdictClaimList claims={claims} />
        </div>
      ) : null}
    </section>
  );
}

/** 확인 · 일부 · 미확인 비율 막대. 주장이 많을수록 목록보다 이게 먼저 읽힌다. */
function StatusBar({
  counts,
  total,
}: {
  counts: { verified: number; partial: number; unsupported: number };
  total: number;
}) {
  const parts = [
    { n: counts.verified, cls: "bg-[var(--claim-ok)]" },
    { n: counts.partial, cls: "bg-[var(--claim-part)]" },
    { n: counts.unsupported, cls: "bg-[var(--claim-no)]" },
  ];
  return (
    <div aria-hidden className="mt-3 flex h-2 gap-0.5 overflow-hidden rounded-full">
      {parts.map((p, i) =>
        p.n > 0 ? <i key={i} className={cn("block h-full", p.cls)} style={{ flex: p.n / total }} /> : null,
      )}
    </div>
  );
}

function Count({ dot, label, n }: { dot: string; label: string; n: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 tabular-nums">
      <i className={cn("size-2 rounded-full", dot)} aria-hidden />
      {label} {n}
    </span>
  );
}

/**
 * 0~100 점수 막대. 왼쪽부터 미확인 · 일부 확인 · 충분 구간이고, 지금 판정
 * 구간만 판정 색으로 칠한다. 점수는 그 위에 핀으로 꽂는다 — 점수를 따로
 * 떼어 두면 "54점이 좋은 건가"를 다시 묻게 된다.
 */
function ScoreBar({ score, level }: { score: number; level: number }) {
  const s = Math.max(0, Math.min(100, Math.round(score)));
  const { low, high } = SCORE_ZONES;
  // 왼쪽부터 미확인(2) · 일부 확인(1) · 충분(0)
  const zones = [
    { step: 2, from: 0, to: low },
    { step: 1, from: low, to: high },
    { step: 0, from: high, to: 100 },
  ];
  return (
    <div
      role="img"
      aria-label={`광고 근거 점수 100점 중 ${s}점, ${VERDICT_STEPS[level]} 구간`}
      className="relative mt-10 max-w-[380px]"
    >
      <div className="relative flex h-2.5 gap-[3px]">
        {zones.map((z) => (
          <i
            key={z.step}
            aria-hidden
            className="bg-surface-strong block h-full rounded-[3px]"
            style={{
              width: `${z.to - z.from}%`,
              background: z.step === level ? VERDICT_COLOR[level] : undefined,
            }}
          />
        ))}
        <span
          aria-hidden
          className="absolute -top-1.5 -bottom-1.5 w-1 -translate-x-1/2 rounded-sm shadow-[0_0_0_3px_var(--color-surface)]"
          // 핀은 지금 판정 색. 같은 색 구간 위에서도 흰 테두리로 떠 보인다.
          style={{ left: `${s}%`, background: VERDICT_COLOR[level] }}
        >
          <b className="text-fg absolute bottom-[calc(100%+6px)] left-1/2 -translate-x-1/2 text-sm font-extrabold whitespace-nowrap tabular-nums">
            {s}점
          </b>
        </span>
      </div>
      <div aria-hidden className="text-fg-dim relative mt-1.5 h-4 text-[11px] tabular-nums">
        <span className="absolute left-0">0</span>
        <span className="absolute right-0">100</span>
      </div>
      <div aria-hidden className="relative h-4 text-xs">
        {zones.map((z) => (
          <span
            key={z.step}
            className={cn(
              "absolute -translate-x-1/2 whitespace-nowrap",
              z.step === level ? "font-bold" : "text-fg-dim",
            )}
            style={{
              left: `${(z.from + z.to) / 2}%`,
              color: z.step === level ? VERDICT_COLOR[level] : undefined,
            }}
          >
            {VERDICT_STEPS[z.step]}
          </span>
        ))}
      </div>
    </div>
  );
}
