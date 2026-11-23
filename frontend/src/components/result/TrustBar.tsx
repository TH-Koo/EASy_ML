import { CalendarDays, Landmark, Lock, Minus, Plus } from "lucide-react";

import { descriptionFor } from "@/lib/verificationDescriptions";
import type { AnalysisResult } from "@/types/analysis";

/**
 * "이 결과, 믿을 수 있나요?" — 아이콘 + 한 문장.
 *
 * 영문 라벨·제목·보조문·아이콘으로 네 번 끊어 읽던 타일을 한 줄짜리 띠로
 * 바꿨다. 기관별 조회 결과는 처음부터 펼쳐 두며 필요하면 접을 수 있다.
 */
export function TrustBar({ data }: { data: AnalysisResult }) {
  const rows = data.verification.rows;
  const items = [
    {
      Icon: Landmark,
      title: "출처와 확인 범위를 함께 봐요",
      note: "공공 기록과 판매자 설명을 구분해요",
    },
    {
      Icon: Lock,
      title: "자료의 종류에 따라 해석해요",
      note: "기업 공시·특허·인증의 의미는 달라요",
    },
    {
      Icon: CalendarDays,
      title: `${data.product.analysis_date.replaceAll("-", ".")} 기준`,
      note: "이후 등록된 기록은 빠져 있어요",
    },
  ];

  return (
    <section aria-labelledby="trust-h">
      <h2
        id="trust-h"
        className="text-fg mb-2 px-0.5 text-[22px] font-extrabold tracking-[var(--tracking-heading)]"
      >
        이 결과, 믿을 수 있나요?
      </h2>
      <div className="bg-surface print:border-border rounded-[var(--radius-panel)] px-2 py-1.5 shadow-[var(--shadow-panel)] print:border">
        <div className="grid md:grid-cols-3 print:grid-cols-3">
          {items.map(({ Icon, title, note }, i) => (
            <div
              key={title}
              className={`flex items-center gap-3 px-4 py-4 ${i > 0 ? "border-border border-t md:border-t-0 md:border-l print:border-t-0 print:border-l" : ""}`}
            >
              <Icon
                size={28}
                strokeWidth={1.6}
                className="text-brand shrink-0"
                aria-hidden
              />
              <p className="flex flex-col">
                <b className="text-fg text-[15px] font-bold tracking-[var(--tracking-tight)] tabular-nums">
                  {title}
                </b>
                <span className="text-fg-dim text-[12.5px]">{note}</span>
              </p>
            </div>
          ))}
        </div>

        {rows.length > 0 ? (
          <details open className="group border-border mx-1.5 border-t">
            <summary className="text-fg-muted flex cursor-pointer list-none items-center justify-between px-2 py-3 text-[13.5px] font-semibold [&::-webkit-details-marker]:hidden">
              <span>
                출처별 조회 결과 {rows.length}개
                <span className="print:hidden"> 보기</span>
              </span>
              <span
                aria-hidden
                className="print:hidden border-border group-open:bg-fg group-open:border-fg grid size-5 place-items-center rounded-full border group-open:text-white"
              >
                <Plus size={11} strokeWidth={3} className="group-open:hidden" />
                <Minus
                  size={11}
                  strokeWidth={3}
                  className="hidden group-open:block"
                />
              </span>
            </summary>
            <ul className="flex flex-col gap-4 px-3 pb-4">
              {rows.map((row) => (
                <li key={row.source ?? row.key} className="text-[13.5px] leading-relaxed">
                  <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <b className="text-fg font-semibold">{row.key}</b>
                    <span className="text-fg-muted tabular-nums">
                      {row.value}
                    </span>
                  </span>
                  {descriptionFor(row) ? (
                    <span className="text-fg-dim mt-1 block text-[13px] leading-relaxed">
                      {descriptionFor(row)}
                    </span>
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
