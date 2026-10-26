import { Check, ChevronDown, Minus, Plus, X } from "lucide-react";

import { cn } from "@/lib/cn";
import {
  CLAIM_META,
  displayQuote,
  evidenceChips,
  explain,
  isInternalId,
  recordTitle,
  sortClaims,
  sourceName,
} from "@/lib/resultSummary";
import { descriptionFor } from "@/lib/verificationDescriptions";
import type { Claim, ClaimStatus, VerificationRow } from "@/types/analysis";

/**
 * 광고 문구 팩트체크 — 기능 하나가 한 줄인 목록.
 *
 * 블록을 쌓지 않고 한 카드 안에 줄로 나열한다. 위 결론 타일과 형식이 달라야
 * 화면 전체가 단조롭지 않다. 근거를 찾은 기능은 처음부터 펼쳐 두고, 못 찾은
 * 기능은 접어 둔다. ＋를 누르면 찾아본 기록과 "쉽게 말하면" 설명이 나온다.
 */
export function ClaimChecklist({ claims }: { claims: Claim[] }) {
  const rows = sortClaims(claims, true);
  // 주장이 많으면 처음 몇 개만 펼친 목록으로 두고 나머지는 접는다. 근거를
  // 찾은 줄을 모두 펼쳐 두면 수십 줄이 화면을 덮는다.
  const few = rows.length <= OPEN_ALL_MAX;
  const head = rows.slice(0, LIST_HEAD);
  const tail = rows.slice(LIST_HEAD);
  return (
    <section aria-labelledby="factcheck-h">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-3 px-0.5">
        <h2 id="factcheck-h" className="text-fg text-[22px] font-extrabold tracking-[var(--tracking-heading)]">
          광고 문구 팩트체크
        </h2>
        <p className="text-fg-dim flex gap-3 pb-1 text-[12.5px]">
          <Legend cls="bg-[var(--claim-ok)]" label="확인" />
          <Legend cls="bg-[var(--claim-part)]" label="일부" />
          <Legend cls="bg-[var(--claim-no)]" label="미확인" />
        </p>
      </div>
      <div className="bg-surface rounded-[var(--radius-panel)] px-5 py-1 shadow-[var(--shadow-panel)] md:px-6">
        {head.map((c) => (
          <ClaimRow key={c.id} claim={c} openFound={few} />
        ))}
        {tail.length > 0 ? (
          <details className="group/more">
            <summary className="text-fg-muted border-border flex cursor-pointer list-none items-center justify-center gap-1.5 border-t py-3.5 text-[13.5px] font-semibold group-open/more:hidden [&::-webkit-details-marker]:hidden">
              나머지 {tail.length}개 기능 보기
              <ChevronDown size={16} aria-hidden />
            </summary>
            <div className="border-border border-t">
              {tail.map((c) => (
                <ClaimRow key={c.id} claim={c} openFound={false} />
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </section>
  );
}

/** 이 개수 이하면 근거를 찾은 줄을 처음부터 펼쳐 둔다 */
const OPEN_ALL_MAX = 5;
/** 접지 않고 바로 보여 줄 줄 수 */
const LIST_HEAD = 8;

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <i className={cn("size-2 rounded-full", cls)} aria-hidden />
      {label}
    </span>
  );
}

const MARK: Record<ClaimStatus, { Icon: typeof Check; bg: string; text: string }> = {
  verified: { Icon: Check, bg: "bg-[var(--claim-ok)]", text: "text-[var(--claim-ok)]" },
  partial: { Icon: Minus, bg: "bg-[var(--claim-part)]", text: "text-[var(--claim-part)]" },
  unsupported: { Icon: X, bg: "bg-[var(--claim-no)]", text: "text-[var(--claim-no)]" },
};

function ClaimRow({ claim, openFound }: { claim: Claim; openFound: boolean }) {
  const { Icon, bg, text } = MARK[claim.status];
  const chips = evidenceChips(claim);
  const quote = displayQuote(claim);
  const found = claim.evidence.length > 0;
  const ex = explain(claim);

  return (
    <details
      id={`claim-${claim.id}`}
      open={found && openFound}
      className="group border-border scroll-mt-4 border-b last:border-b-0"
    >
      <summary className="grid cursor-pointer list-none grid-cols-[28px_minmax(0,1fr)_44px_24px] items-center gap-x-2.5 gap-y-1.5 py-4 md:grid-cols-[28px_minmax(0,1fr)_auto_56px_24px] md:gap-x-3.5 [&::-webkit-details-marker]:hidden">
        <span aria-hidden className={cn("grid size-7 place-items-center rounded-full text-white", bg)}>
          <Icon size={15} strokeWidth={3} />
        </span>
        <span className="flex min-w-0 flex-col">
          <b className="text-fg text-[15.5px] font-bold tracking-[var(--tracking-tight)]">
            {claim.text}
          </b>
          {quote ? (
            <span className="text-fg-dim truncate text-[13px]">“{quote}”</span>
          ) : null}
        </span>
        <span className="col-start-2 row-start-2 flex flex-wrap gap-1.5 md:col-start-auto md:row-start-auto md:justify-end">
          {chips.map((chip) => (
            <span
              key={chip}
              className={cn(
                "rounded-md px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
                found ? "bg-[var(--claim-ok-soft)] text-[var(--claim-ok)]" : "bg-surface-strong text-fg-dim",
              )}
            >
              {chip}
            </span>
          ))}
        </span>
        <span className={cn("col-start-3 row-start-1 text-right text-[13px] font-bold md:col-start-auto md:row-start-auto", text)}>
          {CLAIM_META[claim.status].label}
        </span>
        <Toggle />
      </summary>

      <div className="bg-bg mb-4 rounded-xl px-4 py-1 md:ml-[42px]">
        {found ? (
          claim.evidence.map((ref, i) => (
            <div
              key={`${ref.source}-${ref.record_id ?? i}`}
              className="border-border grid grid-cols-1 gap-x-3 border-b py-2.5 last:border-b-0 md:grid-cols-[120px_minmax(0,1fr)_auto] md:items-baseline"
            >
              <span className="text-fg-dim text-[12.5px]">{sourceName(ref)}</span>
              <span className="text-fg text-[13.5px] font-medium">
                {recordTitle(ref)}
                {ref.record_id && !isInternalId(ref.record_id) ? (
                  <small className="text-fg-dim block font-mono text-[11.5px] font-normal">
                    {ref.record_id}
                  </small>
                ) : null}
              </span>
              <span className="text-[12.5px] font-bold text-[var(--claim-ok)]">찾음</span>
            </div>
          ))
        ) : (
          <p className="text-fg-muted py-2.5 text-[13.5px]">
            {chips.length > 0 ? `${chips.join(" · ")} — 조회했지만 찾지 못했어요` : "조회한 기록에서 찾지 못했어요"}
          </p>
        )}

        <div className="bg-surface my-3 flex flex-col gap-2 rounded-lg px-3.5 py-3">
          <p className="text-brand-fg text-xs font-bold">쉽게 말하면</p>
          <Explain tag="뜻">{ex.meaning}</Explain>
          {ex.sources.length > 0 ? (
            <Explain tag="출처">
              {ex.sources.map((s, i) => (
                <span key={s.name}>
                  {i > 0 ? " · " : null}
                  <b className="text-fg mr-1 font-semibold">{s.name}</b>
                  {s.role}
                </span>
              ))}
            </Explain>
          ) : null}
          <Explain tag="판정">{ex.role}</Explain>
        </div>
      </div>
    </details>
  );
}

function Explain({ tag, children }: { tag: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[40px_minmax(0,1fr)] items-baseline gap-2.5">
      <span className="bg-surface-strong text-fg-dim rounded-md py-0.5 text-center text-[11.5px] font-bold">
        {tag}
      </span>
      <p className="text-fg-muted text-[13.5px] leading-relaxed">{children}</p>
    </div>
  );
}

/** ＋ 는 펼치기, − 는 접기. 아이콘 하나로 상태를 같이 보여 준다. */
function Toggle() {
  return (
    <span
      aria-hidden
      className="border-border text-fg-muted group-open:bg-fg group-open:border-fg grid size-6 place-items-center rounded-full border group-open:text-white"
    >
      <Plus size={12} strokeWidth={3} className="group-open:hidden" />
      <Minus size={12} strokeWidth={3} className="hidden group-open:block" />
    </span>
  );
}

/**
 * 주장 목록이 없는 예전 기록용. `claims` 를 저장하기 전 분석은 기관별 조회
 * 결과(verification.rows)만 있으므로 그것을 같은 목록 모양으로 보여 준다.
 */
export function RecordChecklist({ rows }: { rows: VerificationRow[] }) {
  return (
    <section aria-labelledby="records-h">
      <h2 id="records-h" className="text-fg mb-2 px-0.5 text-[22px] font-extrabold tracking-[var(--tracking-heading)]">
        조회한 공공 기록
      </h2>
      <ul className="bg-surface rounded-[var(--radius-panel)] px-5 py-1 shadow-[var(--shadow-panel)] md:px-6">
        {rows.map((row) => {
          const desc = descriptionFor(row);
          return (
            <li key={row.source ?? row.key} className="border-border flex gap-3.5 border-b py-3.5 last:border-b-0">
              <span
                aria-hidden
                className={cn(
                  "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-white",
                  row.intent === "ok" ? "bg-[var(--claim-ok)]" : row.intent === "warn" ? "bg-[var(--claim-no)]" : "bg-fg-faint",
                )}
              >
                {row.intent === "ok" ? <Check size={13} strokeWidth={3} /> : row.intent === "warn" ? <X size={13} strokeWidth={3} /> : <Minus size={13} strokeWidth={3} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <b className="text-fg text-[14.5px] font-bold">{row.key}</b>
                  <span className="text-fg-muted text-[13px] font-semibold tabular-nums">{row.value}</span>
                </p>
                {desc ? <p className="text-fg-dim mt-0.5 text-[13px]">{desc}</p> : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
