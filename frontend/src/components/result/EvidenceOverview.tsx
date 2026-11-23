import { sourceDetails, sourceName } from "@/lib/resultSummary";
import type { AnalysisResult } from "@/types/analysis";

/** 기능별 팩트체크 다음에 보여 주는 제조사 연구개발 기록. */
export function ManufacturerResearch({ data }: { data: AnalysisResult }) {
  return (
    <section aria-labelledby="manufacturer-research-h">
      <h2
        id="manufacturer-research-h"
        className="text-fg mb-2 px-0.5 text-[22px] font-extrabold tracking-[var(--tracking-heading)]"
      >
        제조사가 관련 AI 기술을 개발해 온 기록이 있나요?
      </h2>
      <div className="bg-surface rounded-[var(--radius-panel)] p-5 shadow-[var(--shadow-panel)] md:p-6">
        <p className="text-fg-muted text-sm leading-relaxed">
          공시와 연구과제를 각각 최대 3건 보여줘요. 제조사의 투자·연구 이력을
          살펴보는 자료예요. 해당 기능을 이 제품에 적용했는지는 제품과 직접
          연결된 기록으로 확인해요.
        </p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {["dart", "ntis"].map((source) => {
            const row = data.verification.rows.find(
              (item) =>
                item.source?.toLowerCase() === source ||
                item.key.toLowerCase().includes(source),
            );
            const records = row?.record_titles?.slice(0, 3) ?? [];
            const count = Number(row?.count ?? row?.value.match(/(\d+)건/)?.[1] ?? 0);
            const confirmed = count > 0 || records.length > 0;
            const result = confirmed
              ? (count || records.length) + "건"
              : row?.value === "없음" || row?.value === "AI 과제 없음"
                ? "0건"
                : row?.value ?? "조회 결과가 제공되지 않았어요";
            const details = sourceDetails(source);
            return (
              <div key={source} className="bg-surface-strong rounded-lg p-3.5">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-fg text-sm font-bold">
                    {sourceName({ source, label: source })}
                  </h3>
                  <span
                    className="text-fg-dim inline-flex shrink-0 items-center gap-1.5 text-xs whitespace-nowrap"
                    style={{ transform: "translateY(-2px)" }}
                  >
                    <i
                      aria-hidden
                      className="size-2 rounded-full"
                      style={{ backgroundColor: confirmed ? "var(--claim-ok)" : "var(--claim-no)" }}
                    />
                    {confirmed ? "확인" : "미확인"}
                  </span>
                </div>
                <p className="text-fg-muted mt-1 text-xs leading-relaxed">
                  {details.role}
                </p>
                <p className="text-fg mt-2 text-sm font-semibold">
                  조회 결과: {result}
                </p>
                {records.length > 0 ? (
                  <ul className="text-fg-dim mt-1 flex flex-col gap-1 text-xs leading-relaxed">
                    {records.map((record) => <li key={record}>{record}</li>)}
                  </ul>
                ) : confirmed ? null : (
                  <p className="text-fg-dim mt-1 text-xs leading-relaxed">
                    조회 결과가 없습니다.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
