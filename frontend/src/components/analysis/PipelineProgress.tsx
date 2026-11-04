"use client";

import { Link2 } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { StepItem } from "@/components/analysis/StepItem";
import { computeEta } from "@/lib/timing";
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
 *   진행 카드  지금 단계 · n/6 · 진행 막대 · 경과/남은 시간 · 여섯 단계
 *
 * 남은 예상 시간은 서버에서 소식을 들은 뒤에만 보인다. computeEta 는 소식이
 * 없을 때 총합을 그대로 돌려주므로, 스트림이 끊기면 같은 숫자가 계속 붙어
 * 있게 된다.
 */

interface PipelineProgressProps {
  analysisId: string;
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

/**
 * 홈 검색창에서 넣은 주소. 진행 이벤트에는 주소가 없어서, 검증을 시작할 때
 * VerifyForm 이 sessionStorage 에 남긴 값을 읽는다. 다른 경로로 들어왔으면 없다.
 */
export const analyzedUrlKey = (id: string) => `fides_url_${id}`;

function useAnalyzedUrl(id: string): string | null {
  return useSyncExternalStore(
    () => () => {},
    () => {
      try {
        return sessionStorage.getItem(analyzedUrlKey(id));
      } catch {
        return null;
      }
    },
    () => null,
  );
}

/** 홈 검색창과 같은 모양 — 넣은 주소가 그대로 확인되고 있다는 걸 이어서 보여 준다. */
function AddressPill({ url }: { url: string }) {
  return (
    <div className="bg-surface border-border mx-auto mt-8 flex max-w-[700px] items-center gap-3 rounded-[14px] border-[1.5px] py-1.5 pr-1.5 pl-2 shadow-[0_1px_2px_rgba(16,24,40,.04)]">
      <span aria-hidden className="bg-brand-soft text-brand-fg grid size-[38px] shrink-0 place-items-center rounded-[10px]">
        <Link2 size={18} />
      </span>
      <span className="text-fg min-w-0 flex-1 truncate py-2.5 text-[15px]" title={url}>
        {url}
      </span>
      <span className="text-brand-fg inline-flex h-[42px] shrink-0 items-center gap-2 rounded-[10px] bg-[var(--claim-ok-soft)] px-4 text-sm font-bold">
        <span aria-hidden className="size-2 animate-pulse rounded-full bg-[var(--claim-part)] motion-reduce:animate-none" />
        확인 중
      </span>
    </div>
  );
}

/** 75 → "1분 15초", 9 → "9초" */
function duration(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  return s >= 60 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${s}초`;
}

export function PipelineProgress({ analysisId, progress }: PipelineProgressProps) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef<number>(0);

  useEffect(() => {
    startRef.current = Date.now();
    const id = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

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
  const eta = computeEta(progress);
  const url = useAnalyzedUrl(analysisId);

  return (
    <section
      className="theme-violet bg-surface flex flex-1 justify-center px-5 pt-16 pb-20 md:pt-20"
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

        {url ? <AddressPill url={url} /> : null}

        <div className="bg-surface-strong mt-6 rounded-[20px] px-6 pt-5 pb-3 md:px-7">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <p className="text-fg text-[17px] font-bold tracking-[var(--tracking-tight)]">
              {current}
              <span className="text-fg-dim ml-2 text-[13px] font-medium tabular-nums">
                {done} / {stages.length}
              </span>
            </p>
            <p className="text-fg-dim text-[13px] tabular-nums">
              경과 <b className="text-fg font-semibold">{duration(elapsed)}</b>
              {progress && eta > 0 ? <> · 남은 예상 {duration(eta)}</> : null}
            </p>
          </div>

          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            aria-label="분석 진행률"
            className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[var(--claim-ok-soft)]"
          >
            {/* 연보라에서 보라로 — 끝으로 갈수록 진해진다 */}
            <div
              className="h-full rounded-full transition-[width] duration-500 ease-out"
              style={{
                width: `${percent}%`,
                background: "linear-gradient(90deg, var(--claim-part), var(--color-brand))",
              }}
            />
          </div>

          {/* 여섯 단계 — 넓은 화면에서는 두 줄로 세워 위에서 아래로 읽는다 */}
          <ol className="mt-2 grid md:grid-flow-col md:grid-cols-2 md:grid-rows-3 md:gap-x-8 [&>li:nth-child(3)]:md:border-b-0 [&>li:last-child]:border-b-0">
            {stages.map((s) => (
              <StepItem key={s.name} stage={s} />
            ))}
          </ol>
        </div>

        {/* 결과에서 쓸 색을 미리 보여 준다 — 보라 · 연보라 · 로즈 */}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2 text-[13px]">
          <span className="text-fg-dim mr-1">결과는 이렇게 알려 드려요</span>
          <span className="rounded-full bg-[var(--claim-ok-soft)] px-3 py-1 font-semibold text-[var(--claim-ok)]">
            근거 충분
          </span>
          <span className="rounded-full bg-[rgba(160,139,234,.16)] px-3 py-1 font-semibold text-[#8a72e0]">
            근거 일부 확인
          </span>
          <span className="rounded-full bg-[var(--claim-no-soft)] px-3 py-1 font-semibold text-[var(--claim-no)]">
            근거 미확인
          </span>
        </div>

        <p className="text-fg-dim mt-5 text-center text-xs tabular-nums">분석 번호 {analysisId}</p>
      </div>
    </section>
  );
}
