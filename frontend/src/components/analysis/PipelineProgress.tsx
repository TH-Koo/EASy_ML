"use client";

import { StepItem } from "@/components/analysis/StepItem";
import {
  STAGE_LABELS,
  STAGE_ORDER,
  type ProgressEvent,
  type StageName,
  type StageStatus,
} from "@/types/analysis";

/**
 * 분석 진행 화면.
 *
 * 홈(가운데 큰 제목 + 보라 둘째 줄)과 결과 화면(흰 바탕, 연회색 카드)의
 * 말씨와 조형을 그대로 잇는다. 검색창에서 넘어와 결과가 나올 때까지 한
 * 서비스처럼 보이게 하려는 것이다.
 *
 *   제목       무엇을 하고 있는지 한 문장
 *   진행 카드  지금 단계 · n/6 · 진행 막대 · 여섯 단계
 *
 * 경과·남은 시간과 분석 번호는 보여 주지 않는다. 시간은 단계마다 기관 응답에
 * 따라 크게 달라 예상이 자주 빗나갔고, 분석 번호는 사용자에게 쓸모가 없다.
 */

interface PipelineProgressProps {
  progress: ProgressEvent | null;
}

function initialStages(): StageStatus[] {
  return STAGE_ORDER.map((name) => ({
    name,
    label: STAGE_LABELS[name].name,
    sub_label: STAGE_LABELS[name].sub,
    state: "wait",
    started_at: null,
    finished_at: null,
    error_message: null,
  }));
}

/** 카드 머리에 쓰는 '지금 하는 일'. 단계 이름(명사)보다 사람이 읽기 쉬운 문장으로 쓴다. */
const DOING: Record<StageName, string> = {
  crawl: "상품 페이지를 읽는 중",
  ocr: "이미지 속 광고 문구를 읽는 중",
  llm_refine: "AI 기능 주장을 정리하는 중",
  public_verify: "공공 기록을 조회하는 중",
  patent_search: "특허·인증을 찾는 중",
  score: "판정을 계산하는 중",
};

export function PipelineProgress({ progress }: PipelineProgressProps) {
  const stages = progress?.stages ?? initialStages();
  const percent = progress?.overall_percent ?? 0;
  const status = progress?.status ?? "queued";
  const done = stages.filter((s) => s.state === "done").length;
  const current = progress?.current_stage
    ? DOING[progress.current_stage]
    : status === "queued"
      ? "분석을 준비하고 있어요"
      : status === "completed"
        ? "확인 완료"
        : "확인하는 중";

  return (
    // 내용이 화면보다 짧으면 세로 가운데보다 살짝 위에 둔다(아래 여백을 더 준다).
    <section
      className="theme-violet bg-surface flex flex-1 items-center justify-center px-5 pt-12 pb-[14vh]"
      aria-live="polite"
      aria-busy={status === "running" || status === "queued"}
    >
      <div className="w-full max-w-[720px]">
        <div className="text-center">
          <h1 className="text-fg text-[clamp(26px,3.6vw,36px)] leading-[1.3] font-bold tracking-[-0.03em]">
            광고 속 AI 기능을
            <br />
            <span className="text-brand-fg">공공 기록과 맞춰 보는 중이에요</span>
          </h1>
          <p className="text-fg-muted mt-3 text-[15px]">
            공공 기록 조회는 기관 응답을 기다려서, 단계마다 걸리는 시간이 달라요.
          </p>
        </div>

        <div className="bg-surface-strong mt-10 rounded-[20px] px-6 pt-5 pb-3 md:px-7">
          <p className="text-fg text-[17px] font-bold tracking-[var(--tracking-tight)]">
            {current}
            <span className="text-fg-dim ml-2 text-[13px] font-medium tabular-nums">
              {done} / {stages.length}
            </span>
          </p>

          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            aria-label="분석 진행률"
            className="bg-border mt-3 h-1.5 w-full overflow-hidden rounded-full"
          >
            <div
              className="bg-brand h-full rounded-full transition-[width] duration-500 ease-out"
              style={{ width: `${percent}%` }}
            />
          </div>

          {/* 여섯 단계 — 넓은 화면에서는 두 줄로 세워 위에서 아래로 읽는다 */}
          <ol className="mt-2 grid md:grid-flow-col md:grid-cols-2 md:grid-rows-3 md:gap-x-8 [&>li:nth-child(3)]:md:border-b-0 [&>li:last-child]:border-b-0">
            {stages.map((s) => (
              <StepItem key={s.name} stage={s} />
            ))}
          </ol>
        </div>

      </div>
    </section>
  );
}
