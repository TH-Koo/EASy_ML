import { Card } from "@/components/primitives/Card";
import { SectionHeader } from "@/components/primitives/SectionHeader";
import { cn } from "@/lib/cn";
import { CREDIBILITY_AXES } from "@/lib/score";
import type { Scores, WeightChannel, Weighting } from "@/types/analysis";

interface ScoreBreakdownProps {
  scores: Scores;
  weighting: Weighting;
}

/* 채널 색은 랜딩·KPI 와 같은 dim 토큰을 쓴다. ECS 는 가중치 대상이 아닌
   고정 혼합이라 회색으로 구분한다. */
const CHANNEL_COLOR: Record<WeightChannel | "ecs", string> = {
  tes: "var(--color-dim-text)",
  hes: "var(--color-dim-verify)",
  ces: "var(--color-dim-relational)",
  ecs: "var(--color-fg-dim)",
};

const AXIS_BY_CHANNEL = {
  tes: CREDIBILITY_AXES[0],
  hes: CREDIBILITY_AXES[1],
  ces: CREDIBILITY_AXES[2],
} as const;

const CHANNEL_ORDER: WeightChannel[] = ["tes", "hes", "ces"];

interface Row {
  key: WeightChannel | "ecs";
  code: string;
  label: string;
  score: number;
  /** 0..1. ECS 는 가중치가 아니라 고정 계수라 null */
  weight: number | null;
  contribution: number;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(0)}%`;
}

/**
 * ACCS 가 어느 채널에서 몇 점씩 왔는지.
 *
 * 채널 점수(KPI)만으로는 "왜 이 총점인가"가 안 보인다. 같은 점수라도
 * 제품마다 반영 비중이 다르기 때문이다. 이 카드는 엔진이 실제로 쓴
 * 비중과 기여도를 그대로 그린다 — 화면에서 다시 계산하지 않는다.
 *
 * 비중이 크다고 그 채널 점수가 높은 것은 아니다. 그래서 점수·비중·기여를
 * 한 줄에 나란히 둔다.
 */
export function ScoreBreakdown({ scores, weighting }: ScoreBreakdownProps) {
  const { weights, contributions, model_version } = weighting;
  const noChannels =
    weighting.weight_status === "no_usable_channels" ||
    CHANNEL_ORDER.every((c) => !weights?.[c]);

  const channelScore: Record<WeightChannel, number> = {
    tes: scores.text_credibility,
    hes: scores.verification_credibility,
    ces: scores.relational_credibility,
  };

  const rows: Row[] = [
    ...CHANNEL_ORDER.map((c) => ({
      key: c,
      code: AXIS_BY_CHANNEL[c].code,
      label: AXIS_BY_CHANNEL[c].label,
      score: channelScore[c],
      weight: weights?.[c] ?? 0,
      contribution: contributions?.[c] ?? 0,
    })),
    {
      key: "ecs",
      code: "ECS",
      label: "근거 채널 다양성",
      score: scores.ecs,
      weight: null,
      contribution: contributions?.ecs ?? 0,
    },
  ];

  const evidenceAlpha = weighting.evidence_alpha ?? 0.85;
  const ecsAlpha = weighting.ecs_alpha ?? 0.15;
  const learned = Boolean(model_version);

  return (
    <Card>
      <SectionHeader
        eyebrow="weights"
        title="점수는 이렇게 만들어졌어요"
        aside={
          <span>{learned ? "AI 모델(CEN)이 정한 반영 비중" : "규칙 기반 반영 비중"}</span>
        }
      />

      {noChannels ? (
        <p className="text-fg-subtle px-5 py-8 text-center text-sm">
          확인된 근거 채널이 없어 반영 비중을 계산하지 않았습니다.
        </p>
      ) : (
        <div className="px-5 pt-4 pb-5">
          {/* 100점 트랙 위에 채널별 기여를 쌓는다. 채워진 길이 = ACCS */}
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-fg-subtle text-[13px]">ACCS 구성</p>
            <p className="text-fg text-sm font-medium tabular-nums">
              {scores.overall.toFixed(1)}
              <span className="text-fg-dim ml-0.5 text-xs">/100</span>
            </p>
          </div>
          <div
            className="bg-surface-strong mt-2 flex h-3 w-full overflow-hidden rounded-full"
            role="img"
            aria-label={rows
              .map((r) => `${r.label} ${r.contribution.toFixed(1)}점`)
              .join(", ")}
          >
            {rows.map((r) =>
              r.contribution > 0 ? (
                <span
                  key={r.key}
                  className="h-full first:rounded-l-full"
                  style={{
                    width: `${Math.min(100, r.contribution)}%`,
                    backgroundColor: CHANNEL_COLOR[r.key],
                  }}
                />
              ) : null,
            )}
          </div>

          <table className="mt-5 w-full text-sm">
            <thead>
              <tr className="text-fg-subtle border-border border-b text-left text-xs">
                <th scope="col" className="pb-2 font-medium">채널</th>
                <th scope="col" className="pb-2 text-right font-medium">점수</th>
                <th scope="col" className="pb-2 text-right font-medium">반영 비중</th>
                <th scope="col" className="pb-2 text-right font-medium">기여</th>
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {rows.map((r) => {
                const inactive = r.weight === 0;
                return (
                  <tr key={r.key} className={cn(inactive && "text-fg-dim")}>
                    <th scope="row" className="py-2.5 text-left font-medium">
                      <span className="flex items-center gap-2">
                        <span
                          aria-hidden
                          className="size-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: CHANNEL_COLOR[r.key] }}
                        />
                        <span className="truncate">{r.label}</span>
                        <span className="text-fg-faint text-xs font-normal">{r.code}</span>
                      </span>
                    </th>
                    <td className="py-2.5 text-right tabular-nums">{r.score.toFixed(1)}</td>
                    <td className="py-2.5 text-right tabular-nums">
                      {r.weight === null ? (
                        <span className="text-fg-dim text-xs">고정 {pct(ecsAlpha)}</span>
                      ) : inactive ? (
                        <span className="text-xs">근거 없음</span>
                      ) : (
                        pct(r.weight)
                      )}
                    </td>
                    <td className="py-2.5 text-right font-medium tabular-nums">
                      +{r.contribution.toFixed(1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="text-fg-dim mt-4 space-y-1 text-xs leading-relaxed">
            <p>
              기여 = {evidenceAlpha.toFixed(2)} × 채널 점수 × 반영 비중 (ECS 는{" "}
              {ecsAlpha.toFixed(2)} × 점수). 기여를 모두 더하면 ACCS 입니다.
            </p>
            <p>
              {learned
                ? "반영 비중은 제품군과 근거의 양·출처 다양성·최신성을 보고 AI 모델이 제품마다 정했습니다."
                : "반영 비중은 근거의 양·출처 다양성·최신성을 기준으로 규칙에 따라 정했습니다."}{" "}
              비중이 크다고 그 채널 점수가 높다는 뜻은 아닙니다.
            </p>
            {learned ? (
              <p className="font-mono">모델 {model_version}</p>
            ) : null}
          </div>
        </div>
      )}
    </Card>
  );
}
