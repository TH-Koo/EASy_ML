import { CalendarDays, Landmark, Lock, Minus, Plus } from "lucide-react";

import { descriptionFor } from "@/lib/verificationDescriptions";
import type { AnalysisResult } from "@/types/analysis";

/**
 * "이 결과, 믿을 수 있나요?" — 아이콘 + 한 문장.
 *
 * 영문 라벨·제목·보조문·아이콘으로 네 번 끊어 읽던 타일을 한 줄짜리 띠로
 * 바꿨다. 기관별 조회 결과는 접어 두고 필요한 사람만 펼친다.
 */
export function TrustBar({ data }: { data: AnalysisResult }) {
  const rows = data.verification.rows;
  const items = [
    { Icon: Landmark, title: "공공기관 기록만 봐요", note: "리뷰·블로그는 보지 않아요" },
    { Icon: Lock, title: "회사가 고칠 수 없어요", note: "기관이 심사한 기록이에요" },
    {
      Icon: CalendarDays,
      title: `${data.product.analysis_date.replaceAll("-", ".")} 기준`,
      note: "이후 등록된 기록은 빠져 있어요",
    },
  ];

  return (
    <section aria-labelledby="trust-h">
      <h2 id="trust-h" className="text-fg mb-2 px-0.5 text-[22px] font-extrabold tracking-[var(--tracking-heading)]">
        이 결과, 믿을 수 있나요?
      </h2>
      <div className="bg-surface rounded-[var(--radius-panel)] px-2 py-1.5 shadow-[var(--shadow-panel)]">
        <div className="grid md:grid-cols-3">
          {items.map(({ Icon, title, note }, i) => (
            <div
              key={title}
              className={`flex items-center gap-3 px-4 py-4 ${i > 0 ? "border-border border-t md:border-t-0 md:border-l" : ""}`}
            >
              <Icon size={28} strokeWidth={1.6} className="text-brand shrink-0" aria-hidden />
              <p className="flex flex-col">
                <b className="text-fg text-[15px] font-bold tracking-[var(--tracking-tight)] tabular-nums">{title}</b>
                <span className="text-fg-dim text-[12.5px]">{note}</span>
              </p>
            </div>
          ))}
        </div>

        {rows.length > 0 ? (
          <details className="group border-border mx-1.5 border-t">
            <summary className="text-fg-muted flex cursor-pointer list-none items-center justify-between px-2 py-3 text-[13.5px] font-semibold [&::-webkit-details-marker]:hidden">
              조회한 공공기관 {rows.length}곳 보기
              <span aria-hidden className="border-border group-open:bg-fg group-open:border-fg grid size-5 place-items-center rounded-full border group-open:text-white">
                <Plus size={11} strokeWidth={3} className="group-open:hidden" />
                <Minus size={11} strokeWidth={3} className="hidden group-open:block" />
              </span>
            </summary>
            <ul className="flex flex-col gap-2 px-2 pb-3.5">
              {rows.map((row) => (
                <li key={row.source ?? row.key} className="text-[13px]">
                  <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <b className="text-fg font-semibold">{row.key}</b>
                    <span className="text-fg-muted tabular-nums">{row.value}</span>
                  </span>
                  {descriptionFor(row) ? (
                    <span className="text-fg-dim block text-[12.5px]">{descriptionFor(row)}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </section>
  );
}
