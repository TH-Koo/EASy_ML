import { Minus, Plus } from "lucide-react";

import { VerdictClaimList } from "@/components/result/VerdictClaimList";
import { cn } from "@/lib/cn";
import {
  SCORE_BINS,
  SCORE_SAMPLE_SIZE,
  VERDICT_STEPS,
  countByStatus,
  headline,
  scoreBin,
  sortClaims,
  topPercent,
  verdictLevel,
  verdictTitle,
} from "@/lib/resultSummary";
import type { AnalysisResult } from "@/types/analysis";

/**
 * 결과 화면 맨 위 결론 타일.
 *
 * 판정과 기능별 결과를 한 타일에 둔다. 결과가 여러 타일로 흩어져 있으면
 * 눈이 지그재그로 움직여야 했다. 왼쪽은 "그래서 어떤가", 오른쪽은
 * "무엇이 되고 무엇이 안 됐나"다.
 */
export function VerdictPanel({ data }: { data: AnalysisResult }) {
  const level = verdictLevel(data.scores.overall_label);
  // 실제 분석은 주장이 수십 개 나온다. 문제가 되는 것부터 몇 개만 보이고
  // 나머지는 그 자리에서 펼친다(VerdictClaimList).
  const claims = sortClaims(data.claims ?? [], true);
  const counts = countByStatus(claims);

  return (
    <section
      aria-label="분석 결론"
      className="relative grid gap-6 overflow-hidden rounded-[var(--radius-panel)] p-6 text-white md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] md:items-start md:gap-8 md:p-8"
      style={{ background: "linear-gradient(135deg, #08195f 0%, #0f35b4 60%, #1e6fe8 100%)" }}
    >
      <div className="min-w-0">
        <p className="text-xs font-semibold text-white/75">
          {data.product.name}
        </p>
        <h1 className="mt-1 text-[34px] leading-tight font-extrabold tracking-[var(--tracking-display)] md:text-[40px]">
          {verdictTitle(data.scores.overall_label)}
        </h1>
        <p className="mt-1 text-[15px] text-white/90">{headline(data)}</p>

        {level !== null ? <VerdictSteps level={level} /> : null}
        {level !== null ? <ScoreContext score={data.scores.overall} /> : null}

        <p className="mt-4 text-[12.5px] text-white/70">
          제품 성능이 아니라 광고 문구가 공공 기록과 맞는지 본 결과예요
        </p>
      </div>

      {claims.length > 0 ? (
        <div className="min-w-0 rounded-[14px] bg-white/10 px-4 py-3.5">
          <p className="flex flex-wrap gap-3.5 border-b border-white/15 px-1 pb-2.5 text-[13px] text-white/85">
            <Count dot="bg-white" label="확인" n={counts.verified} />
            <Count dot="bg-[var(--claim-part-on-dark)]" label="일부" n={counts.partial} />
            <Count dot="bg-[var(--claim-no-on-dark)]" label="미확인" n={counts.unsupported} />
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
    { n: counts.verified, cls: "bg-white" },
    { n: counts.partial, cls: "bg-[var(--claim-part-on-dark)]" },
    { n: counts.unsupported, cls: "bg-[var(--claim-no-on-dark)]" },
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

/* 판정 막대 — 흰색 → 연한 주황 → 주황으로 진해진다. 지금 칸만 진하다. */
const STEP_COLOR = ["#ffffff", "#ffcfa8", "#ff9a52"] as const;
const STEP_TEXT = ["#ffffff", "#ffd9ba", "#ffb07a"] as const;

function VerdictSteps({ level }: { level: number }) {
  return (
    <div className="mt-5 max-w-[240px]" aria-label={`판정 3단계 중 ${VERDICT_STEPS[level]}`}>
      <div className="grid grid-cols-3 items-center gap-1">
        {VERDICT_STEPS.map((step, i) => (
          <i
            key={step}
            aria-hidden
            className={cn("block rounded-[2px]", i === level ? "h-1.5" : "h-1 opacity-40")}
            style={{ background: STEP_COLOR[i] }}
          />
        ))}
      </div>
      <p className="mt-1.5 grid grid-cols-3 gap-1 text-[11.5px] text-white/60">
        {VERDICT_STEPS.map((step, i) => (
          <span
            key={step}
            className={cn(i === 1 && "text-center", i === 2 && "text-right", i === level && "font-bold")}
            style={i === level ? { color: STEP_TEXT[i] } : undefined}
          >
            {step}
          </span>
        ))}
      </p>
    </div>
  );
}

/**
 * 작은 점수 + "점수 보는 법".
 * 점수는 0~100이지만 실제 제품이 한쪽에 몰려 있어 숫자만으로는 늘 낮아
 * 보인다. 분석해 둔 제품 안에서의 위치를 같이 적는다.
 */
function ScoreContext({ score }: { score: number }) {
  const top = topPercent(score);
  const mine = scoreBin(score);
  const peak = Math.max(...SCORE_BINS);
  return (
    <details className="group mt-4 rounded-xl bg-white/10">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2.5 px-3 py-2.5 [&::-webkit-details-marker]:hidden">
        <span className="text-xl leading-none font-extrabold tracking-[var(--tracking-heading)] tabular-nums">
          {Math.round(score)}
          <small className="ml-px text-xs font-semibold text-white/80">점</small>
        </span>
        <span className="text-[13px] text-white/85">
          분석한 제품 {SCORE_SAMPLE_SIZE.toLocaleString()}개 중{" "}
          {/* 아래쪽 절반은 "상위 78%" 보다 "하위 22%" 가 바로 읽힌다 */}
          <b className="text-white">{top <= 50 ? `상위 ${top}%` : `하위 ${100 - top}%`}</b>
        </span>
        <span className="ml-auto text-xs text-white/65">점수 보는 법</span>
        <span
          aria-hidden
          className="grid size-5 place-items-center rounded-full bg-white/20 group-open:bg-white group-open:text-[#0f35b4]"
        >
          <Plus size={12} strokeWidth={3} className="group-open:hidden" />
          <Minus size={12} strokeWidth={3} className="hidden group-open:block" />
        </span>
      </summary>
      <div className="px-3 pb-3">
        <div
          role="img"
          aria-label="분석한 제품의 점수 분포. 대부분 35점에서 55점 사이"
          className="flex h-14 items-end gap-0.5 border-b border-white/30"
        >
          {SCORE_BINS.map((n, i) => (
            <i
              key={i}
              className={cn("block flex-1 rounded-t-[2px]", i === mine ? "bg-[#ff9a52]" : "bg-white/35")}
              style={{ height: `${Math.max(2, Math.round((n / peak) * 100))}%` }}
            />
          ))}
        </div>
        <p className="mt-1 flex justify-between text-[11px] text-white/60 tabular-nums">
          <span>0</span>
          <span>50</span>
          <span>100</span>
        </p>
        <ul className="mt-2.5 flex list-disc flex-col gap-1 pl-4 text-[12.5px] leading-relaxed text-white/85 marker:text-white/60">
          <li>점수는 0~100이지만, 실제 제품은 대부분 <b className="text-white">35~55점</b>에 몰려 있어요.</li>
          <li>공공 기록을 하나도 찾지 못하면 <b className="text-white">5~10점</b>이 나와요.</li>
          <li>60점을 넘는 제품은 <b className="text-white">100개 중 1개</b> 꼴이라, 점수보다 순위로 보는 게 정확해요.</li>
        </ul>
      </div>
    </details>
  );
}
