import { AlertTriangle, CheckCircle2, CircleDashed, Info } from "lucide-react";

import { tierForLabel, tierStyles, type VerdictTone } from "@/lib/score";
import type { OverallLabel } from "@/types/analysis";

interface AlertBannerProps {
  overallLabel: OverallLabel;
}

const COPY = {
  ok: {
    title: "AI 워싱 위험이 낮은 제품입니다",
    description:
      "공공 인증과 특허 등 검증 가능한 근거가 충분히 확인되었습니다. AI 주장의 구체성도 높은 편입니다.",
    Icon: CheckCircle2,
  },
  warn: {
    title: "AI 기능을 뒷받침하는 근거를 추가로 확인해 보세요",
    description:
      "AI 기능 주장은 있으나 이를 확인할 공공 기록이 충분하지 않습니다. 워싱으로 단정할 단계는 아니며, 구매 전 제조사 자료나 인증 정보를 함께 확인하길 권장합니다.",
    Icon: Info,
  },
  danger: {
    title: "AI 워싱 가능성이 높은 제품입니다",
    description:
      "AI 핵심 기술 설명이 부재하고 공공 인증·특허 등 객관적 검증 근거가 매우 부족합니다. 표기된 'AI' 기능이 실체와 다를 가능성이 큽니다.",
    Icon: AlertTriangle,
  },
  neutral: {
    title: "AI 기능 주장이 확인되지 않아 평가하지 않았습니다",
    description:
      "상품 페이지에서 AI 기능을 내세우는 표현을 찾지 못했습니다. 점수가 낮게 보여도 AI 워싱이라는 뜻은 아닙니다.",
    Icon: CircleDashed,
  },
} as const;

const NEUTRAL_STYLES = { text: "text-fg-muted", bgSoft: "bg-surface-strong" };

/**
 * 결과 상단 안내.
 *
 * 문구는 백엔드 판정 라벨로만 고른다. 이전에는 ACCS 를 옛 60/50 기준으로
 * 다시 나눠서, 엔진이 "신뢰 상품"이라 한 51점 제품에 "검증되지 않았다"는
 * 경고가 붙었고, 주장이 없어 평가를 건너뛴 제품에는 "워싱 가능성이
 * 높다"가 떴다. 판정 경계는 fides_config 가 정본이다.
 */
export function AlertBanner({ overallLabel }: AlertBannerProps) {
  const tone: VerdictTone = tierForLabel(overallLabel);
  const { title, description, Icon } = COPY[tone];
  const styles = tone === "neutral" ? NEUTRAL_STYLES : tierStyles[tone];

  return (
    <div
      role="alert"
      className={`${styles.bgSoft} flex items-start gap-3 rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--color-fg)_4%,transparent)] px-5 py-4`}
    >
      <Icon size={20} className={`${styles.text} mt-0.5 shrink-0`} aria-hidden />
      <div className="min-w-0 flex-1">
        <p
          className={`${styles.text} flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm font-bold tracking-tight`}
        >
          <span>{title}</span>
          <span className="text-fg-dim font-mono text-[13px] uppercase tracking-[0.08em]">
            {overallLabel}
          </span>
        </p>
        <p className="text-fg-muted mt-1 text-[13px] leading-relaxed">
          {description}
        </p>
      </div>
    </div>
  );
}
