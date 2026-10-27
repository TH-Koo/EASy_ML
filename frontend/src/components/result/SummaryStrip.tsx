import { ArrowRight } from "lucide-react";
import Link from "next/link";

import type { AnalysisResult } from "@/types/analysis";

/**
 * 결론 타일 바로 아래 요약 띠.
 *
 * 정보 칸은 흰 바탕에 선으로만 나누고, 누를 수 있는 것은 색을 채운 비교
 * 버튼 하나다. 예전에는 정보와 버튼이 같은 타일 모양이라 무엇을 읽고
 * 무엇을 누르는지 구분이 안 됐다.
 */
export function SummaryStrip({ data }: { data: AnalysisResult }) {
  const sources = data.verification.rows.length;
  return (
    <section
      aria-label="분석 요약"
      className="grid overflow-hidden rounded-[var(--radius-panel)] bg-surface shadow-[var(--shadow-panel)] md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
    >
      <Cell
        label="확인한 곳"
        value={sources > 0 ? `공공기관 ${sources}곳` : "공공기관"}
        note="특허청 · 금융감독원 · 인증 기관 등"
      />
      <Cell
        label="기준일"
        value={data.product.analysis_date.replaceAll("-", ".")}
        note="이후 등록된 기록은 빠져 있어요"
        className="border-border border-t md:border-t-0 md:border-l"
      />
      <Link
        href="/compare"
        className="flex items-center justify-between gap-4 px-6 py-4 text-[15px] font-bold text-white hover:brightness-110 md:justify-start"
        style={{ background: "var(--color-brand)" }}
      >
        비슷한 제품과 비교하기
        <ArrowRight size={18} aria-hidden />
      </Link>
    </section>
  );
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
