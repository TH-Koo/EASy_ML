import Link from "next/link";

import { ClaimLedger } from "@/components/claim/ClaimLedger";
import { Button } from "@/components/primitives/Button";
import { Eyebrow } from "@/components/primitives/Eyebrow";
import { CLAIM_STATUS } from "@/lib/claimStatus";
import { cn } from "@/lib/cn";
import { CREDIBILITY_AXES } from "@/lib/score";
import type { CompareItem } from "@/types/auth";

/**
 * 제품 비교.
 *
 * 이전 화면은 최고점 하나를 뽑아 "AI 추천"이라는 파란 배너를 띄웠다. 세
 * 제품이 31점 · 22점 · 18점이어도 31점짜리에 추천 배지가 붙었다. Fides 는
 * 제품을 고르라고 만든 서비스가 아니라 광고 문구에 근거가 붙는지 보는
 * 서비스다. 그래서 배너를 없애고, 근거가 확인된 주장이 하나도 없으면
 * 그 사실을 먼저 말한다.
 *
 * 축 이름도 세 개 다 틀려 있었다 — `text_credibility` 를 "텍스트 신뢰도 ·
 * AI 주장 구체성"이라 불렀는데 그 값은 KIPRIS 특허와 DART 공시다. 이제
 * `lib/score.ts` 의 `CREDIBILITY_AXES` 를 결과 화면과 함께 쓴다.
 *
 * 조형은 카드 세 장에서 표로 바꿨다. 비교는 나란히 놓고 같은 줄에서 읽는
 * 일이고, 카드를 세 장 세우면 눈이 위아래로 오간다.
 */

export interface CompareViewProps {
  items: CompareItem[];
  /** 표본으로 띄울 때 헤더의 대시보드 링크를 감춘다 */
  bare?: boolean;
}

const LABEL =
  "font-mono text-xs tracking-[var(--tracking-label)] text-fg-faint";

/* accs_score 는 표시 점수다. 85·40 은 원점수 60·35 와 같은 자리. */
function toneFor(score: number) {
  if (score >= 85) return "var(--color-verified)";
  if (score >= 40) return "var(--color-partial)";
  return "var(--color-missing)";
}

/** 근거가 확인된 주장 수. 없으면 null — 옛 기록에는 주장 자료가 없다. */
function verifiedCount(item: CompareItem): { n: number; total: number } | null {
  const r = item.claims_rollup;
  if (!r || r.total === 0) return null;
  return { n: r.verified, total: r.total };
}

export function CompareView({ items, bare }: CompareViewProps) {
  const cols = items.length;

  /* 결론 한 줄. 점수가 아니라 붙은 주장 수로 말한다. */
  const counted = items
    .map((it) => ({ it, c: verifiedCount(it) }))
    .filter((x): x is { it: CompareItem; c: { n: number; total: number } } =>
      Boolean(x.c),
    );
  const leader = [...counted].sort((a, b) => b.c.n - a.c.n)[0];
  const anyVerified = counted.some((x) => x.c.n > 0);

  return (
    <div className="bg-bg flex flex-1 flex-col">
      <div className="mx-auto w-full max-w-[1200px] px-5 py-14 md:px-10">
        {/* 머리 */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Eyebrow>Compare</Eyebrow>
            <h1 className="text-fg mt-3 text-2xl font-medium tracking-[var(--tracking-heading)] md:text-[27px]">
              제품 비교
            </h1>
          </div>
          {bare ? null : (
            <Button asChild variant="secondary" size="sm">
              <Link href="/dashboard">대시보드로</Link>
            </Button>
          )}
        </div>

        {/* 결론 — 추천이 아니라 관찰 */}
        <p className="text-fg mt-8 max-w-[62ch] text-[15px] leading-relaxed tracking-[var(--tracking-tight)]">
          {counted.length === 0 ? (
            <>
              이 기록들에는 주장별 자료가 없습니다. 아래는 세 축 점수만
              비교한 결과입니다.
            </>
          ) : anyVerified ? (
            <>
              근거가 가장 많이 확인된 것은{" "}
              <span className="font-medium">{leader.it.product_name}</span> 로,
              주장 {leader.c.total}건 중 {leader.c.n}건입니다. 나머지는 아래
              표에서 나란히 확인하세요.
            </>
          ) : (
            <>
              비교한 {items.length}개 제품 모두{" "}
              <span
                className="font-medium"
                style={{ color: "var(--color-missing)" }}
              >
                근거가 확인된 주장이 하나도 없습니다.
              </span>{" "}
              점수 차이는 부분 일치와 기업 이력에서 나온 것이지, 어느 쪽이
              더 입증됐다는 뜻이 아닙니다.
            </>
          )}
        </p>

        {/* ── 비교표 ─────────────────────────────────────────────── */}
        <div className="mt-12 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <caption className="sr-only">제품별 지표 비교</caption>
            <colgroup>
              <col style={{ width: "22%" }} />
              {items.map((it) => (
                <col key={it.id} style={{ width: `${78 / cols}%` }} />
              ))}
            </colgroup>

            <thead>
              <tr className="border-border border-b">
                <th scope="col" className={cn(LABEL, "pb-3 font-normal")}>
                  지표
                </th>
                {items.map((it) => (
                  <th key={it.id} scope="col" className="pb-3 pl-4 align-bottom">
                    <span className="text-fg block text-sm font-medium tracking-[var(--tracking-tight)]">
                      {it.product_name}
                    </span>
                    <span className="text-fg-dim mt-1 block text-xs font-normal">
                      {it.company_name || "브랜드 미상"}
                      {it.category ? ` · ${it.category}` : ""}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>

            <tbody className="divide-border divide-y">
              {/* 근거가 붙은 주장 — 이 표의 결론이므로 맨 위 */}
              <tr>
                <th
                  scope="row"
                  className="py-4 pr-4 align-top text-sm font-normal"
                >
                  <span className="text-fg block tracking-[var(--tracking-tight)]">
                    근거 확인 주장
                  </span>
                  <span className="text-fg-dim mt-1 block text-xs">
                    공공 기록이 실제로 붙은 문구
                  </span>
                </th>
                {items.map((it) => {
                  const c = verifiedCount(it);
                  return (
                    <td key={it.id} className="py-4 pl-4 align-top">
                      {c ? (
                        <>
                          <span
                            className="text-lg font-medium tabular-nums"
                            style={{
                              color:
                                c.n > 0
                                  ? "var(--color-verified)"
                                  : "var(--color-missing)",
                            }}
                          >
                            {c.n}
                          </span>
                          <span className="text-fg-dim text-sm tabular-nums">
                            {" / "}
                            {c.total}
                          </span>
                          <RollupBar item={it} />
                        </>
                      ) : (
                        <span className="text-fg-faint text-sm">자료 없음</span>
                      )}
                    </td>
                  );
                })}
              </tr>

              {/* 세 축 */}
              {CREDIBILITY_AXES.map((axis) => (
                <tr key={axis.code}>
                  <th
                    scope="row"
                    className="py-4 pr-4 align-top text-sm font-normal"
                  >
                    <span className="text-fg block tracking-[var(--tracking-tight)]">
                      {axis.label}
                      <span className="text-fg-faint ml-1.5 text-xs">
                        {axis.code}
                      </span>
                    </span>
                    <span className="text-fg-dim mt-1 block text-xs">
                      {axis.sources}
                    </span>
                  </th>
                  {items.map((it) => {
                    const v = it[axis.field] ?? 0;
                    return (
                      <td key={it.id} className="py-4 pl-4 align-top">
                        <span
                          className="text-sm font-medium tabular-nums"
                          style={{ color: toneFor(v) }}
                        >
                          {v.toFixed(1)}
                        </span>
                        <Bar value={v} />
                      </td>
                    );
                  })}
                </tr>
              ))}

              {/* 종합 */}
              <tr>
                <th
                  scope="row"
                  className="py-4 pr-4 align-top text-sm font-normal"
                >
                  <span className="text-fg block tracking-[var(--tracking-tight)]">
                    종합 ACCS
                  </span>
                  <span className="text-fg-dim mt-1 block text-xs">
                    세 축을 합친 값
                  </span>
                </th>
                {items.map((it) => (
                  <td key={it.id} className="py-4 pl-4 align-top">
                    <span
                      className="text-2xl font-medium tabular-nums tracking-[var(--tracking-heading)]"
                      style={{ color: toneFor(it.accs_score) }}
                    >
                      {it.accs_score.toFixed(1)}
                    </span>
                    <Bar value={it.accs_score} />
                  </td>
                ))}
              </tr>

              {/* 판정 — 백엔드가 이미 내린 것을 그대로 */}
              <tr>
                <th
                  scope="row"
                  className="py-4 pr-4 align-top text-sm font-normal"
                >
                  <span className="text-fg block tracking-[var(--tracking-tight)]">
                    판정
                  </span>
                  <span className="text-fg-dim mt-1 block text-xs">
                    분석 시점 {items[0]?.created_at}
                  </span>
                </th>
                {items.map((it) => (
                  <td key={it.id} className="py-4 pl-4 align-top">
                    <span
                      className="text-sm font-medium tracking-[var(--tracking-tight)]"
                      style={{ color: toneFor(it.accs_score) }}
                    >
                      {it.verdict || "—"}
                    </span>
                    {it.risk_level ? (
                      <span className="text-fg-dim mt-1 block text-xs">
                        위험도 {it.risk_level}
                      </span>
                    ) : null}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>

        {/* ── 주장별 대조 ────────────────────────────────────────── */}
        {counted.length > 0 ? (
          <section className="mt-16">
            <Eyebrow>Claims</Eyebrow>
            <h2 className="text-fg mt-3 text-xl font-medium tracking-[var(--tracking-heading)]">
              주장별 대조
            </h2>
            <p className="text-fg-dim mt-2 max-w-[62ch] text-sm leading-relaxed">
              제품마다 내세운 기능이 다르므로 같은 줄에 놓을 수 없습니다.
              대신 제품별로 어떤 문구에 근거가 붙고 어떤 문구가 비었는지를
              나란히 둡니다.
            </p>

            <div
              className="mt-8 grid gap-x-10 gap-y-12"
              style={{
                gridTemplateColumns: `repeat(${Math.min(cols, 2)}, minmax(0,1fr))`,
              }}
            >
              {counted.map(({ it }) => (
                <div key={it.id}>
                  <p className="text-fg text-sm font-medium tracking-[var(--tracking-tight)]">
                    {it.product_name}
                  </p>
                  <ClaimLedger claims={it.claims ?? []} className="mt-4" />
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}

/* ── 조각 ─────────────────────────────────────────────────────────── */

function Bar({ value }: { value: number }) {
  return (
    <span className="bg-border mt-2 block h-[3px] w-full max-w-[160px] overflow-hidden rounded-full">
      <span
        className="block h-full rounded-full"
        style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: toneFor(value) }}
      />
    </span>
  );
}

/**
 * 주장 판정 분포. 대시보드의 `ClaimBar` 와 같은 언어를 쓴다 —
 * 파랑 확인 · 노랑 부분 · 주황 근거 없음.
 */
function RollupBar({ item }: { item: CompareItem }) {
  const r = item.claims_rollup;
  if (!r || r.total === 0) return null;
  const seg = [
    { n: r.verified, s: CLAIM_STATUS.verified },
    { n: r.partial, s: CLAIM_STATUS.partial },
    { n: r.missing, s: CLAIM_STATUS.unsupported },
  ];
  return (
    <span
      className="mt-2 flex gap-[3px]"
      title={seg.map((x) => `${x.s.label} ${x.n}`).join(" · ")}
    >
      {seg.flatMap((x, si) =>
        Array.from({ length: x.n }).map((_, i) => (
          <span
            key={`${si}-${i}`}
            className="h-[6px] w-[9px] rounded-[1px]"
            style={{ background: x.s.color, opacity: si === 2 ? 1 : 0.55 }}
          />
        )),
      )}
    </span>
  );
}
