"use client";

import { Check, ChevronDown, Minus, X } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";
import { CLAIM_META } from "@/lib/resultSummary";
import type { Claim, ClaimStatus } from "@/types/analysis";

/** 결론 타일에 처음부터 이름을 보여 줄 주장 수 */
const INITIAL = 5;

/**
 * 결론 타일 안의 기능 목록.
 *
 * 처음에는 문제가 되는 것부터 몇 개만 보이고, "나머지 N개 기능 보기" 를
 * 누르면 그 자리에서 목록이 늘어난다. 아래 팩트체크로 화면을 옮기면 지금
 * 보던 결론에서 눈이 떨어진다. 줄을 누르면 해당 기능의 자세한 근거로 간다.
 */
export function VerdictClaimList({ claims }: { claims: Claim[] }) {
  const [expanded, setExpanded] = useState(false);
  const rest = claims.length - INITIAL;
  const shown = expanded ? claims : claims.slice(0, INITIAL);

  return (
    <>
      <ul className="mt-1 divide-y divide-white/10">
        {shown.map((c) => (
          <li key={c.id}>
            <a
              href={`#claim-${c.id}`}
              className="flex items-center gap-3 rounded-lg px-1 py-2.5 hover:bg-white/10"
            >
              <StatusMark status={c.status} />
              <span className="min-w-0 flex-1 truncate text-[15px] font-semibold tracking-[var(--tracking-tight)]">
                {c.text}
              </span>
              <span
                className={cn(
                  "text-[13px] font-bold",
                  c.status === "partial" && "text-[#c9d3f7]",
                  c.status === "unsupported" && "text-[#ffb07a]",
                )}
              >
                {CLAIM_META[c.status].label}
              </span>
            </a>
          </li>
        ))}
      </ul>
      {rest > 0 ? (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 flex w-full items-center justify-between rounded-lg border-t border-white/15 px-1 pt-3 pb-1 text-[13px] font-semibold text-white/85 hover:text-white"
        >
          {expanded ? "접기" : `나머지 ${rest}개 기능 보기`}
          <ChevronDown
            size={16}
            aria-hidden
            className={cn("transition-transform", expanded && "rotate-180")}
          />
        </button>
      ) : null}
    </>
  );
}

const MARK: Record<ClaimStatus, { Icon: typeof Check; cls: string }> = {
  verified: { Icon: Check, cls: "bg-white text-[#0f35b4]" },
  partial: { Icon: Minus, cls: "bg-[var(--claim-part-on-dark)] text-[#08195f]" },
  unsupported: { Icon: X, cls: "bg-[var(--claim-no-on-dark)] text-white" },
};

function StatusMark({ status }: { status: ClaimStatus }) {
  const { Icon, cls } = MARK[status];
  return (
    <span
      aria-hidden
      className={cn("grid size-6 shrink-0 place-items-center rounded-full", cls)}
    >
      <Icon size={14} strokeWidth={3} />
    </span>
  );
}
