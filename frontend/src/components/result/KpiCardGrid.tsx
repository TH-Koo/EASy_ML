import { Minus, Plus } from "lucide-react";

import type { Scores } from "@/types/analysis";

const INDICATORS = [
  {
    field: "verification_credibility",
    label: "제품 확인 (HES)",
    description: "판매 정보와 인증 기록 등을 바탕으로 자료가 해당 제품을 얼마나 분명히 가리키는지 봐요.",
  },
  {
    field: "text_credibility",
    label: "기술 근거 (TES)",
    description: "특허, 공시, 연구개발 자료가 광고한 기술과 얼마나 관련 있는지 봐요. 제품에 직접 연결되는 근거를 더 중요하게 봐요.",
  },
  {
    field: "relational_credibility",
    label: "인증·공공 기록 (CES)",
    description: "조회한 인증과 공공 기록 중 제품과 관련 있어 평가에 반영할 수 있는 근거를 살펴봐요.",
  },
  {
    field: "ecs",
    label: "근거 출처의 다양성 (ECS)",
    description: "판매자 설명 외에 여러 종류의 독립된 출처에서 근거를 찾았는지 봐요.",
  },
  {
    field: "conf",
    label: "분석 신뢰도 (CONF)",
    description: "자료가 이 제품을 직접 가리키는지, 여러 출처의 자료가 광고 내용과 일치하는지 등을 바탕으로 판단해요.",
  },
] as const satisfies ReadonlyArray<{
  field: keyof Scores;
  label: string;
  description: string;
}>;

export function KpiCardGrid({ scores }: { scores: Scores }) {
  return (
    <details
      id="indicator-scores"
      className="group bg-surface print:border-border rounded-[var(--radius-panel)] px-3.5 py-1.5 shadow-[var(--shadow-panel)] print:border"
    >
      <summary className="text-fg-muted flex cursor-pointer list-none items-center justify-between px-2 py-3 text-[13.5px] font-semibold [&::-webkit-details-marker]:hidden">
        <span>
          지표별 점수와 산정 기준<span className="print:hidden"> 보기</span>
        </span>
        <span
          aria-hidden
          className="print:hidden border-border group-open:bg-fg group-open:border-fg grid size-5 place-items-center rounded-full border group-open:text-white"
        >
          <Plus size={11} strokeWidth={3} className="group-open:hidden" />
          <Minus size={11} strokeWidth={3} className="hidden group-open:block" />
        </span>
      </summary>
      <p className="text-fg-muted px-2 pb-3 text-[13px]">
        각 지표는 종합 점수와 같은 표시 눈금으로 변환했어요.
        종합 점수는 지표마다 반영 비중이 달라 단순 평균과 차이가 있어요.
      </p>
      <ul className="flex flex-col gap-2 px-2 pb-3.5">
        {INDICATORS.map(({ field, label, description }) => {
          const score = scores.indicator_display?.[field] ?? scores[field];
          return (
            <li key={field} className="text-[13px]">
              <span className="flex items-baseline justify-between gap-3">
                <b className="text-fg font-semibold">{label}</b>
                <span className="text-fg-muted shrink-0 text-right whitespace-nowrap tabular-nums">
                  {typeof score === "number" && Number.isFinite(score)
                    ? score.toFixed(2) + "점"
                    : "—"}
                </span>
              </span>
              <span className="text-fg-dim block text-[12.5px]">{description}</span>
            </li>
          );
        })}
      </ul>
    </details>
  );
}
