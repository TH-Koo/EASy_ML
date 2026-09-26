import { ClaimLedger } from "@/components/claim/ClaimLedger";
import { AlertBanner } from "@/components/result/AlertBanner";
import { DashboardShell } from "@/components/result/DashboardShell";
import { KpiCardGrid } from "@/components/result/KpiCardGrid";
import { MetaSidebar } from "@/components/result/MetaSidebar";
import { QuickActions } from "@/components/result/QuickActions";
import { ResultFooterCta } from "@/components/result/ResultFooterCta";
import { ResultHero } from "@/components/result/ResultHero";
import { ScoreBreakdown } from "@/components/result/ScoreBreakdown";
import { VerificationTable } from "@/components/result/VerificationTable";
import { XaiFindings } from "@/components/result/XaiFindings";
import type { AnalysisResult } from "@/types/analysis";

/**
 * Result dashboard. Uses `DashboardShell` to lay out:
 *   - row 1 (col 12) ResultHero — product + overall ScoreGauge + meta
 *   - row 2 (col 12) AlertBanner — tier-aware messaging
 *   - row 3 (col 8 main + col 4 sticky sidebar):
 *       main:    KpiCardGrid → XaiFindings → VerificationTable
 *       sidebar: MetaSidebar → QuickActions
 *   - row 4 (col 12) ResultFooterCta
 *
 * 사이드바에서 `DataSourceList` 를 뺐다. 9개 소스 목록은 어떤 제품을
 * 분석해도 같은 내용이라 결과가 아니라 서비스 설명이다. 컴포넌트는 그대로
 * 두었으므로 소개 화면에서 다시 쓸 수 있다.
 */
export function ResultView({ data, historyId, elapsedSeconds }: { data: AnalysisResult; historyId?: number; elapsedSeconds?: number }) {
  return (
    <DashboardShell
      hero={<ResultHero data={data} elapsedSeconds={elapsedSeconds} />}
      alert={<AlertBanner overallLabel={data.scores.overall_label} />}
      main={
        <>
          {/* 대조 뷰를 맨 앞에 둔다. 이 서비스의 결론은 점수가 아니라
              "붙지 않고 남은 주장"이고, /about 이 그렇게 가르친다.
              서버가 capability_scores 를 저장하기 전 기록에는 claims 가
              비어 있으므로 그때는 접는다. */}
          {data.claims && data.claims.length > 0 ? (
            <ClaimLedger claims={data.claims} />
          ) : null}
          <KpiCardGrid scores={data.scores} />
          {/* 가중치 연결 이전 기록에는 weighting 이 없으므로 접는다. */}
          {data.weighting ? (
            <ScoreBreakdown scores={data.scores} weighting={data.weighting} />
          ) : null}
          <XaiFindings findings={data.xai_findings} />
          <VerificationTable verification={data.verification} />
        </>
      }
      sidebar={
        <>
          <QuickActions data={data} historyId={historyId} />
          <MetaSidebar data={data} />
        </>
      }
      footer={<ResultFooterCta />}
    />
  );
}
