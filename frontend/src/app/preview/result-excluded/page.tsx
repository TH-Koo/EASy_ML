import { SummaryStrip } from "@/components/result/SummaryStrip";
import { VerdictPanel } from "@/components/result/VerdictPanel";
import type { AnalysisResult } from "@/types/analysis";

/** 판정 제외 결과의 윗부분 — 검토용. 백엔드 없이 예시 데이터로 그린다. */

const SAMPLE = {
  product: {
    name: "Seagate SkyHawk AI 7200/512M (12TB, ST12000VE003)",
    url: "https://prod.danawa.com/info/?pcode=94811081",
    analysis_date: "2026-11-06",
    ai_claims_count: 5,
  },
  scores: { overall: 0, overall_label: "판정 제외" },
  claims: [],
  verification: { rows: [{}, {}, {}, {}, {}, {}, {}] },
} as unknown as AnalysisResult;

export default function ResultExcludedPreviewPage() {
  return (
    <div className="theme-violet mx-auto flex w-full max-w-[960px] flex-col gap-3.5 px-4 pt-4 pb-16 md:px-0">
      <VerdictPanel data={SAMPLE} />
      <SummaryStrip data={SAMPLE} />
    </div>
  );
}
