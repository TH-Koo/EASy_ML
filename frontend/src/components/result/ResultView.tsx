import { Badge } from "@/components/primitives/Badge";
import { ClaimChecklist, RecordChecklist } from "@/components/result/ClaimChecklist";
import { QuickActions } from "@/components/result/QuickActions";
import { SummaryStrip } from "@/components/result/SummaryStrip";
import { TrustBar } from "@/components/result/TrustBar";
import { VerdictPanel } from "@/components/result/VerdictPanel";
import type { AnalysisResult } from "@/types/analysis";

/**
 * 결과 화면 — 한 단, 위에서 아래로 "결론 → 근거 → 믿을 수 있는 이유".
 *
 *   VerdictPanel    판정 + 기능별 결과 + 점수 위치
 *   SummaryStrip    찾은 기록 · 확인한 곳 · 기준일 · 미확인 이유로 가기
 *   ClaimChecklist  광고 문구 팩트체크(근거·쉬운 설명은 펼쳐서)
 *   TrustBar        공공 기록만 쓴다는 근거 · 기관별 조회 결과
 *   QuickActions    다른 제품 검색 · 공유 · 인쇄 · 북마크
 *
 * 점수·가중치 표는 보여 주지 않는다. 점수는 결론 타일 안에서 분포 속 위치와
 * 함께 작게만 쓴다. `claims` 가 없는 예전 기록은 기관별 조회 결과를 대신
 * 보여 준다.
 */
export function ResultView({
  data,
  historyId,
}: {
  data: AnalysisResult;
  historyId?: number;
  /** 예전 화면이 분석 소요 시간을 보여 주던 값. 지금은 쓰지 않는다. */
  elapsedSeconds?: number;
}) {
  const claims = data.claims ?? [];
  return (
    <div className="theme-violet mx-auto flex w-full max-w-[960px] flex-col gap-3.5 px-4 pt-4 pb-16 md:px-0">
      {data.meta.backend === "mock" ? (
        <Badge intent="warn" className="self-start" title="이 결과는 mock 어댑터가 생성한 합성 데이터입니다.">
          mock data
        </Badge>
      ) : null}

      <VerdictPanel data={data} />
      <SummaryStrip data={data} />

      <div className="mt-8 flex flex-col gap-11">
        {claims.length > 0 ? (
          <ClaimChecklist claims={claims} />
        ) : data.verification.rows.length > 0 ? (
          <RecordChecklist rows={data.verification.rows} />
        ) : null}
        <TrustBar data={data} />
        <QuickActions data={data} historyId={historyId} />
      </div>
    </div>
  );
}
