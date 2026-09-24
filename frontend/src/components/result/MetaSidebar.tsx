import { Card } from "@/components/primitives/Card";
import { SectionHeader } from "@/components/primitives/SectionHeader";
import type { AnalysisResult } from "@/types/analysis";

interface MetaSidebarProps {
  data: AnalysisResult;
}

function Row({
  k,
  v,
  mono = false,
}: {
  k: string;
  v: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2.5">
      <dt className="text-fg-subtle text-[13px] uppercase font-medium tracking-[0.06em] whitespace-nowrap">
        {k}
      </dt>
      <dd
        className={`text-fg min-w-0 truncate text-right text-[13px] ${mono ? "font-mono tabular-nums" : ""}`}
      >
        {v}
      </dd>
    </div>
  );
}

export function MetaSidebar({ data }: MetaSidebarProps) {
  const created = new Date(data.created_at);
  const createdStr = created.toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <Card>
      <SectionHeader eyebrow="meta" title="분석 메타데이터" />
      <dl className="divide-soft px-5 pb-3">
        {/* 소요 시간과 분석일은 히어로 하단 3칸에 이미 있다. 여기 또 적으면
            같은 값이 한 화면에 두 번 나오고, 예전에는 히어로가 브라우저
            타이머를, 여기가 백엔드 값을 써서 18s / 18.2s 로 어긋났다. */}
        <Row k="분석 ID" v={data.analysis_id} mono />
        <Row k="파이프라인" v={data.meta.pipeline_version} mono />
        <Row
          k="가중치 모델"
          v={data.meta.model_version ?? "규칙 기반"}
          mono={Boolean(data.meta.model_version)}
        />
        <Row k="생성 시각" v={createdStr} />
      </dl>
    </Card>
  );
}
