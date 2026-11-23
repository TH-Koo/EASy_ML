import { Check, ChevronDown, Minus, Plus, X } from "lucide-react";

import { cn } from "@/lib/cn";
import {
  CLAIM_META,
  SOURCE_SCOPE,
  displayQuote,
  evidenceChips,
  explain,
  isInternalId,
  sortClaims,
  sourceName,
  sourceDetails,
} from "@/lib/resultSummary";
import { descriptionFor } from "@/lib/verificationDescriptions";
import type { Claim, ClaimStatus, EvidenceRef, VerificationRow } from "@/types/analysis";

/**
 * 광고 문구 팩트체크 — 기능 하나가 한 줄인 목록.
 *
 * 블록을 쌓지 않고 한 카드 안에 줄로 나열한다. 위 결론 타일과 형식이 달라야
 * 화면 전체가 단조롭지 않다. 근거를 찾은 기능은 처음부터 펼쳐 두고, 못 찾은
 * 기능은 접어 둔다. ＋를 누르면 찾아본 기록과 "쉽게 말하면" 설명이 나온다.
 */
export function ClaimChecklist({
  claims,
  sourceRows,
}: {
  claims: Claim[];
  sourceRows: VerificationRow[];
}) {
  const rows = sortClaims(claims, true);
  // 주장이 많으면 처음 몇 개만 펼친 목록으로 두고 나머지는 접는다. 근거를
  // 찾은 줄을 모두 펼쳐 두면 수십 줄이 화면을 덮는다.
  const few = rows.length <= OPEN_ALL_MAX;
  const head = rows.slice(0, LIST_HEAD);
  const tail = rows.slice(LIST_HEAD);
  return (
    <section aria-labelledby="factcheck-h">
      <div className="mb-2 flex flex-wrap items-end justify-between gap-3 px-0.5">
        <h2
          id="factcheck-h"
          className="text-fg text-[22px] font-extrabold tracking-[var(--tracking-heading)]"
        >
          광고 문구 팩트체크
        </h2>
        <p className="text-fg-dim flex gap-3 pb-1 text-[12.5px]">
          <Legend cls="bg-[var(--claim-ok)]" label="근거 확인" />
          <Legend cls="bg-[var(--claim-part)]" label="일부 확인" />
          <Legend cls="bg-[var(--claim-no)]" label="미확인" />
        </p>
      </div>
      <div className="bg-surface print:border-border rounded-[var(--radius-panel)] px-5 py-1 shadow-[var(--shadow-panel)] md:px-6 print:border">
        {head.map((c) => (
          <ClaimRow key={c.id} claim={c} openFound={few} sourceRows={sourceRows} />
        ))}
        {tail.length > 0 ? (
          <details className="group/more">
            <summary className="text-fg-muted border-border flex cursor-pointer list-none items-center justify-center gap-1.5 border-t py-3.5 text-[13.5px] font-semibold group-open/more:hidden [&::-webkit-details-marker]:hidden">
              나머지 {tail.length}개 기능 보기
              <ChevronDown size={16} aria-hidden />
            </summary>
            <div className="border-border border-t">
              {tail.map((c) => (
                <ClaimRow key={c.id} claim={c} openFound={false} sourceRows={sourceRows} />
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

const MARK: Record<
  ClaimStatus,
  { Icon: typeof Check; bg: string; text: string }
> = {
  verified: {
    Icon: Check,
    bg: "bg-[var(--claim-ok)]",
    text: "text-[var(--claim-ok)]",
  },
  partial: {
    Icon: Minus,
    bg: "bg-[var(--claim-part)]",
    text: "text-[var(--claim-part)]",
  },
  unsupported: {
    Icon: X,
    bg: "bg-[var(--claim-no)]",
    text: "text-[var(--claim-no)]",
  },
};

function ClaimRow({
  claim,
  openFound,
  sourceRows,
}: {
  claim: Claim;
  openFound: boolean;
  sourceRows: VerificationRow[];
}) {
  const { Icon, bg, text } = MARK[claim.status];
  const isSellerPage = (source: string) => source.toLowerCase() === "seller_page";
  const evidence = claim.evidence.slice().sort(
    (a, b) => Number(isSellerPage(b.source)) - Number(isSellerPage(a.source)),
  );
  const chips = evidenceChips({ ...claim, evidence });
  const quote = displayQuote(claim);
  const found = evidence.length > 0;
  const ex = explain(claim);
  const dartContext = sourceRows.find((row) => row.source === "dart");
  const showDartContext = Boolean(
    dartContext?.record_titles?.length &&
    !evidence.some((ref) => ref.source.toLowerCase() === "dart"),
  );
  const publicLabels = [...new Set(evidence.filter((ref) => !isSellerPage(ref.source)).map(
    (ref) => {
      const source = ref.source.toLowerCase();
      if (source === "rra") return "전파인증 기록";
      if (source === "kipris") return "관련 특허";
      return sourceName(ref);
    },
  ))];
  const foundRecords = publicLabels.length > 0
    ? publicLabels.join(", ") + " 자료를 찾았어요."
    : "";
  const sellerFound = evidence.some((ref) => isSellerPage(ref.source));
  const explanation = claim.status === "partial" && found
    ? [
        sellerFound ? "판매 페이지에는 이 기능이 안내돼 있어요." : "",
        foundRecords,
        "이 자료들은 제품과 관련 기술을 살펴보는 데 도움이 돼요.",
      ].filter(Boolean).join(" ")
    : ex.meaning;

  return (
    <details
      id={`claim-${claim.id}`}
      open={found && openFound}
      className="group border-border scroll-mt-4 border-b last:border-b-0"
    >
      <summary className="grid cursor-pointer list-none grid-cols-[28px_minmax(0,1fr)_64px_24px] items-center gap-x-2.5 gap-y-1.5 py-4 print:py-3 md:grid-cols-[28px_minmax(0,1fr)_auto_64px_24px] md:gap-x-3.5 [&::-webkit-details-marker]:hidden">
        <span
          aria-hidden
          className={cn(
            "grid size-7 place-items-center rounded-full text-white",
            bg,
          )}
        >
          <Icon size={15} strokeWidth={3} />
        </span>
        <span className="flex min-w-0 flex-col">
          <b className="text-fg text-[15.5px] font-bold tracking-[var(--tracking-tight)]">
            {claim.text}
          </b>
          {quote ? (
            <span className="text-fg-dim truncate text-[13px] print:whitespace-normal">
              “{quote}”
            </span>
          ) : null}
        </span>
        <span
          className={cn(
            "col-start-2 row-start-2 flex flex-wrap gap-1.5 md:col-start-auto md:row-start-auto md:justify-end",
            // 종이에서는 바로 아래 기록 줄이 같은 기관 이름을 다시 적는다
            found && "print:hidden",
          )}
        >
          {chips.map((chip) => (
            <span
              key={chip}
              className={cn(
                "rounded-md px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
                found
                  ? "bg-[var(--claim-ok-soft)] text-[var(--claim-ok)]"
                  : "bg-surface-strong text-fg-dim",
              )}
            >
              {chip}
            </span>
          ))}
        </span>
        <span
          className={cn(
            "col-start-3 row-start-1 text-right text-[13px] font-bold md:col-start-auto md:row-start-auto",
            text,
          )}
        >
          {CLAIM_META[claim.status].label}
        </span>
        <Toggle />
      </summary>

      <div className="bg-bg mb-4 rounded-xl px-4 py-1 md:ml-[42px] print:mb-3 print:ml-[38px]">
        {found ? (
          evidence.map((ref, i) => (
            <EvidenceRow
              key={`${ref.source}-${ref.record_id ?? i}`}
              item={ref}
              sourceRows={sourceRows}
            />
          ))
        ) : (
          <p className="text-fg-muted py-2.5 text-[13.5px]">
            {chips.length > 0
              ? `${chips.join(" · ")} — 조회했지만 찾지 못했어요`
              : "조회한 기록에서 찾지 못했어요"}
          </p>
        )}

        {showDartContext ? (
          <EvidenceRow
            item={{ source: "dart", label: "DART 전자공시", record_id: null }}
            sourceRows={sourceRows}
            companyContext
          />
        ) : null}
        <div className="bg-surface my-3 flex flex-col gap-2 rounded-lg px-3.5 py-3 print:my-2 print:gap-1.5 print:py-2.5">
          <p className="text-brand-fg text-xs font-bold">
            왜 이렇게 평가했나요?
          </p>
          <Explain tag="결과">{explanation}</Explain>
          <Explain tag="기준">{ex.role}</Explain>
          {claim.note && !isInternalId(claim.note) ? (
            <Explain tag="상세">{claim.note}</Explain>
          ) : null}
        </div>
      </div>
    </details>
  );
}

const EVIDENCE_ROW_TITLES: Record<string, string> = {
  seller_page: "판매 페이지",
  rra: "RRA 전파인증",
  kipris: "KIPRIS 특허",
  dart: "DART 전자공시",
};

function EvidenceRow({
  item,
  sourceRows,
  companyContext = false,
}: {
  item: EvidenceRef;
  sourceRows: VerificationRow[];
  companyContext?: boolean;
}) {
  const source = item.source.toLowerCase();
  const title = EVIDENCE_ROW_TITLES[source] ?? sourceName(item);
  const description = SOURCE_SCOPE[source] ?? sourceDetails(source).role;
  const recordId = isInternalId(item.record_id) ? null : item.record_id;
  const row = sourceRows.find((entry) => entry.source === source);
  const example = evidenceExample(source, row) ?? recordId;

  return (
    <div className="border-border grid grid-cols-1 gap-x-3 border-b py-2.5 last:border-b-0 print:py-2 md:grid-cols-[120px_minmax(0,1fr)_auto] md:items-baseline print:grid-cols-[110px_minmax(0,1fr)_auto] print:items-baseline">
      <b className="text-fg text-xs font-bold">{title}</b>
      <div className="min-w-0">
        <p className="text-fg-muted text-xs leading-relaxed">{description}</p>
        {example ? (
          <p className="text-fg-dim mt-1 text-xs leading-relaxed">{example}</p>
        ) : null}
      </div>
      <span className="text-xs font-bold text-[var(--claim-part)]">
        {companyContext ? "회사 이력" : "찾음"}
      </span>
    </div>
  );
}

function evidenceExample(source: string, row?: VerificationRow): string | null {
  const title = row?.record_titles?.[0];
  if (!title) return null;
  if (source === "rra") {
    const count = row.matched_model_count;
    return title + (count ? " · 동일 모델 " + count + "건" : "");
  }
  if (source === "kipris") {
    const count = row.count ?? 1;
    return "제조사 특허 조회 · 「" + title + "」" + (count > 1 ? " 등 " + count + "건" : "");
  }
  return title;
}

function Explain({
  tag,
  children,
}: {
  tag: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[40px_minmax(0,1fr)] items-baseline gap-2.5">
      <span className="bg-surface-strong text-fg-dim rounded-md py-0.5 text-center text-[11.5px] font-bold">
        {tag}
      </span>
      <p className="text-fg-muted text-[12.5px] leading-relaxed">{children}</p>
    </div>
  );
}

/** ＋ 는 펼치기, − 는 접기. 아이콘 하나로 상태를 같이 보여 준다. */
function Toggle() {
  return (
    <span
      aria-hidden
      className="border-border text-fg-muted group-open:bg-fg group-open:border-fg grid size-6 place-items-center rounded-full border group-open:text-white print:invisible"
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
      <h2
        id="records-h"
        className="text-fg mb-2 px-0.5 text-[22px] font-extrabold tracking-[var(--tracking-heading)]"
      >
        조회한 공공 기록
      </h2>
      <ul className="bg-surface print:border-border rounded-[var(--radius-panel)] px-5 py-1 shadow-[var(--shadow-panel)] md:px-6 print:border">
        {rows.map((row) => {
          const desc = descriptionFor(row);
          return (
            <li
              key={row.source ?? row.key}
              className="border-border flex gap-3.5 border-b py-3.5 last:border-b-0"
            >
              <span
                aria-hidden
                className={cn(
                  "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-white",
                  row.intent === "ok"
                    ? "bg-[var(--claim-ok)]"
                    : row.intent === "warn"
                      ? "bg-[var(--claim-no)]"
                      : "bg-fg-faint",
                )}
              >
                {row.intent === "ok" ? (
                  <Check size={13} strokeWidth={3} />
                ) : row.intent === "warn" ? (
                  <X size={13} strokeWidth={3} />
                ) : (
                  <Minus size={13} strokeWidth={3} />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <b className="text-fg text-[14.5px] font-bold">{row.key}</b>
                  <span className="text-fg-muted text-[13px] font-semibold tabular-nums">
                    {row.value}
                  </span>
                </p>
                {desc ? (
                  <p className="text-fg-dim mt-0.5 text-[13px]">{desc}</p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
