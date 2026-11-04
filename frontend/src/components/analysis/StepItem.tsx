import { AlertTriangle, Check } from "lucide-react";

import { cn } from "@/lib/cn";
import type { StageStatus } from "@/types/analysis";

/**
 * 파이프라인 한 단계.
 *
 * 홈·결과 화면과 같은 말씨와 색을 쓴다. 연보라 카드 위에서 끝난 단계는
 * 보라 체크, 지금 단계는 흰 줄 위 연보라 점이 숨 쉬듯 깜빡이고, 기다리는
 * 단계는 옅은 보라 점이다. 오류만 로즈다(결과 화면에서 로즈는 '문제'를 뜻한다).
 */

interface StepItemProps {
  stage: StageStatus;
}

const STATE: Record<StageStatus["state"], { label: string; cls: string }> = {
  done: { label: "완료", cls: "text-brand-fg" },
  running: { label: "진행 중", cls: "text-brand-fg" },
  wait: { label: "대기", cls: "text-fg-dim" },
  error: { label: "오류", cls: "text-[var(--claim-no)]" },
};

export function StepItem({ stage }: StepItemProps) {
  const s = STATE[stage.state];
  const isError = stage.state === "error";

  return (
    <li
      className={cn(
        "flex min-w-0 items-center gap-3 border-b border-[rgba(103,65,217,.10)] py-3",
        // 연보라 카드 위에서 지금 단계 줄만 흰 바탕으로 띄운다
        stage.state === "running" &&
          "bg-surface -mx-3 rounded-xl border-transparent px-3 shadow-[0_1px_3px_rgba(103,65,217,.10)]",
      )}
    >
      <Mark state={stage.state} />
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "text-[15px] tracking-[var(--tracking-tight)]",
            stage.state === "wait" ? "text-fg-muted" : "text-fg font-semibold",
          )}
        >
          {stage.label}
        </p>
        <p className={cn("mt-0.5 truncate text-xs", isError ? "text-[var(--claim-no)]" : "text-fg-dim")}>
          {isError && stage.error_message ? stage.error_message : stage.sub_label}
        </p>
      </div>
      <span className={cn("shrink-0 text-[13px] font-semibold", s.cls)}>{s.label}</span>
    </li>
  );
}

function Mark({ state }: { state: StageStatus["state"] }) {
  if (state === "done") {
    return (
      <span aria-hidden className="bg-brand grid size-5 shrink-0 place-items-center rounded-full text-white">
        <Check size={12} strokeWidth={3} />
      </span>
    );
  }
  if (state === "error") {
    return (
      <span aria-hidden className="grid size-5 shrink-0 place-items-center rounded-full bg-[var(--claim-no)] text-white">
        <AlertTriangle size={11} strokeWidth={2.6} />
      </span>
    );
  }
  if (state === "running") {
    return (
      <span aria-hidden className="grid size-5 shrink-0 place-items-center">
        <span className="size-2.5 animate-pulse rounded-full bg-[var(--claim-part)] shadow-[0_0_0_5px_rgba(160,139,234,.25)] motion-reduce:animate-none" />
      </span>
    );
  }
  return (
    <span aria-hidden className="grid size-5 shrink-0 place-items-center">
      <span className="size-2.5 rounded-full bg-[rgba(103,65,217,.18)]" />
    </span>
  );
}
