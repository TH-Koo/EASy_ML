import { PipelineProgress } from "@/components/analysis/PipelineProgress";
import { STAGE_LABELS, STAGE_ORDER, type ProgressEvent } from "@/types/analysis";

/**
 * 분석 진행 화면 — 검토용.
 *
 * 백엔드 없이 진행 화면을 보려고 세 번째 단계(주장 정리)가 도는 중인 상태를
 * 고정해서 그린다. 실제 화면은 AnalysisRunner 가 서버 진행 스트림으로 채운다.
 */

export const metadata = { title: "Fides — 진행 화면 미리보기" };

const RUNNING_AT = 2;

const SAMPLE: ProgressEvent = {
  analysis_id: "preview-0000",
  status: "running",
  overall_percent: 42,
  current_stage: STAGE_ORDER[RUNNING_AT],
  updated_at: "2026-11-04T12:00:00Z",
  stages: STAGE_ORDER.map((name, i) => ({
    name,
    label: STAGE_LABELS[name].name,
    sub_label: STAGE_LABELS[name].sub,
    state: i < RUNNING_AT ? "done" : i === RUNNING_AT ? "running" : "wait",
    started_at: null,
    finished_at: null,
    error_message: null,
  })),
};

export default function ProgressPreviewPage() {
  return <PipelineProgress analysisId={SAMPLE.analysis_id} progress={SAMPLE} />;
}
