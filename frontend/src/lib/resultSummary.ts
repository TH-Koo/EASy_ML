import type {
  AnalysisResult,
  Claim,
  ClaimStatus,
  EvidenceRef,
  OverallLabel,
} from "@/types/analysis";

/**
 * 결과 화면이 쓰는 문장·분류를 한곳에서 만든다.
 *
 * 화면 컴포넌트는 여기서 받은 값을 그리기만 한다. 같은 판정을 두 곳에서
 * 따로 문장으로 바꾸면 결론 타일과 팩트체크 목록이 서로 다른 말을 하게
 * 된다. 점수·판정은 백엔드 값을 그대로 쓰고 다시 계산하지 않는다.
 */

/* ── 판정 3단계 ───────────────────────────────────────────────────────── */

export type VerdictLevel = 0 | 1 | 2;

export const VERDICT_STEPS = ["충분", "부족", "매우 부족"] as const;

/** 백엔드 구간 라벨 → 화면 3단계. "판정 제외"는 단계가 없다. */
export function verdictLevel(label: OverallLabel): VerdictLevel | null {
  if (label === "양호 구간") return 0;
  if (label === "주의 구간") return 1;
  if (label === "위험 구간") return 2;
  return null;
}

export function verdictTitle(label: OverallLabel): string {
  const level = verdictLevel(label);
  if (level === null) return "판정 제외";
  return `근거 ${VERDICT_STEPS[level]}`;
}

/* ── 주장별 판정 ─────────────────────────────────────────────────────── */

export interface ClaimStatusMeta {
  /** 화면에 나가는 짧은 판정 */
  label: string;
  /** 정렬 순서. 결론 타일은 확인부터, 팩트체크는 미확인부터 */
  rank: number;
}

export const CLAIM_META: Record<ClaimStatus, ClaimStatusMeta> = {
  verified: { label: "확인", rank: 0 },
  partial: { label: "일부", rank: 1 },
  unsupported: { label: "미확인", rank: 2 },
};

export function countByStatus(claims: Claim[]) {
  return {
    verified: claims.filter((c) => c.status === "verified").length,
    partial: claims.filter((c) => c.status === "partial").length,
    unsupported: claims.filter((c) => c.status === "unsupported").length,
  };
}

export function sortClaims(claims: Claim[], worstFirst: boolean): Claim[] {
  const dir = worstFirst ? -1 : 1;
  return [...claims].sort(
    (a, b) => dir * (CLAIM_META[a.status].rank - CLAIM_META[b.status].rank),
  );
}

/** 결론 타일의 한 줄 요약 */
export function headline(data: AnalysisResult): string {
  const claims = data.claims ?? [];
  if (claims.length === 0) {
    const n = data.product.ai_claims_count;
    return n > 0
      ? `광고한 AI 기능 ${n}개를 공공 기록과 맞춰 봤어요`
      : "광고에서 AI 기능 주장을 찾지 못했어요";
  }
  const { verified } = countByStatus(claims);
  if (verified === claims.length) {
    return `광고한 AI 기능 ${claims.length}개 모두 공공 기록으로 확인됐어요`;
  }
  if (verified === 0) {
    return `광고한 AI 기능 ${claims.length}개 중 공공 기록으로 확인된 게 없어요`;
  }
  return `광고한 AI 기능 ${claims.length}개 중 ${verified}개만 공공 기록으로 확인됐어요`;
}

/* ── 공공 기록 출처 ───────────────────────────────────────────────────── */

export interface SourceInfo {
  /** 사람이 아는 이름 */
  name: string;
  /** 그곳이 하는 일 — "쉽게 말하면" 의 출처 줄 */
  role: string;
}

/**
 * id 는 server.py 의 `SOURCE_LABELS` 와 같다(verificationDescriptions.ts 참고).
 * 없는 id 는 레코드의 label 을 그대로 이름으로 쓴다.
 */
export const SOURCE_INFO: Record<string, SourceInfo> = {
  kipris: { name: "특허청 KIPRIS", role: "등록된 특허를 누구나 조회하는 곳" },
  dart: { name: "금융감독원 DART", role: "회사가 법에 따라 사업보고서를 공개하는 곳" },
  kc: { name: "KC 인증", role: "전기용품이 안전 기준을 통과했다는 국가 인증" },
  rra: { name: "전파인증", role: "무선 기기를 팔기 전에 반드시 받아야 하는 인증" },
  tipa: { name: "TIPA", role: "AI 공급기업 명단" },
  koraia: { name: "한국인공지능산업협회", role: "국내 AI 기업들이 모인 협회의 회원 명단" },
  gs: { name: "GS 인증", role: "소프트웨어가 품질 시험을 통과했다는 인증" },
  nep: { name: "신제품 인증 NEP", role: "새 기술이 처음 적용된 제품에 주는 인증" },
  procurement: { name: "조달청", role: "공공기관 납품을 위해 등록한 제품 목록" },
  seller_page: { name: "판매 페이지", role: "판매자가 올린 상세페이지 (공공 기록은 아니에요)" },
};

/** 백엔드가 `SELLER_PAGE` 처럼 대문자로 보내는 경우도 같은 항목으로 찾는다. */
function infoFor(source: string): SourceInfo | undefined {
  return SOURCE_INFO[source] ?? SOURCE_INFO[source.toLowerCase()];
}

export function sourceName(ref: Pick<EvidenceRef, "source" | "label">): string {
  return infoFor(ref.source)?.name ?? infoFor(ref.label)?.name ?? ref.label;
}

/** 기록 제목. 백엔드가 제목 대신 출처 id(`SELLER_PAGE`)를 넣어 보낸 경우 설명으로 바꾼다. */
export function recordTitle(ref: Pick<EvidenceRef, "label">): string {
  return infoFor(ref.label)?.role ?? ref.label;
}

/** 근거를 출처별로 묶어 칩으로 쓴다. 예) "특허청 KIPRIS 2" */
export function evidenceChips(claim: Claim): string[] {
  if (claim.evidence.length === 0) {
    // 근거가 없으면 백엔드가 남긴 사유("KIPRIS 0건 · DART 0건")를 그대로 쓴다.
    return claim.note ? claim.note.split("·").map((s) => s.trim()).filter(Boolean) : [];
  }
  const counts = new Map<string, number>();
  for (const ref of claim.evidence) {
    const name = sourceName(ref);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts].map(([name, n]) => (n > 1 ? `${name} ${n}` : name));
}

/* ── "쉽게 말하면" ────────────────────────────────────────────────────── */

export interface PlainExplanation {
  meaning: string;
  sources: SourceInfo[];
  role: string;
}

const MEANING: Record<ClaimStatus, string> = {
  verified: "광고한 기능과 맞는 공공 기록을 찾았어요.",
  partial:
    "관련된 공공 기록은 있지만, 광고한 기능 전체를 뒷받침하지는 못해요.",
  unsupported:
    "확인할 수 있는 공식 기록을 찾지 못했어요. 기능이 없다는 뜻이 아니라, 공개된 기록으로는 확인되지 않는다는 뜻이에요.",
};

const ROLE: Record<ClaimStatus, string> = {
  verified: "공공 기록이 광고 문구를 뒷받침해서 ‘확인’이에요.",
  partial: "기록이 일부만 맞아서 ‘일부’예요.",
  unsupported: "뒷받침하는 기록이 없어 ‘미확인’이에요.",
};

export function explain(claim: Claim): PlainExplanation {
  const ids = new Set(claim.evidence.map((e) => e.source.toLowerCase()));
  // 근거가 없을 때는 사유 문구에 적힌 기관만 출처로 보여 준다.
  if (ids.size === 0 && claim.note) {
    for (const id of Object.keys(SOURCE_INFO)) {
      if (claim.note.toLowerCase().includes(id)) ids.add(id);
    }
  }
  return {
    meaning: MEANING[claim.status],
    sources: [...ids].map((id) => SOURCE_INFO[id]).filter(Boolean),
    role: ROLE[claim.status],
  };
}

/* ── 점수 위치 ───────────────────────────────────────────────────────── */

/**
 * 지금까지 분석해 둔 제품의 ACCS 분포(5점 단위 개수).
 *
 * artifacts/rescore_v2_ontology/features.csv 의 rule_dynamic_accs 1,251건으로
 * 셌다. 점수가 35~55점에 몰리고 60점을 넘는 제품이 1% 남짓이라, 숫자만
 * 보여 주면 "늘 낮은 점수"로 읽힌다. 그래서 이 분포 안에서의 위치를 같이
 * 보여 준다. 표본이 바뀌면 이 배열을 다시 세어 갱신한다.
 */
export const SCORE_BINS: readonly number[] = [
  0, 277, 0, 0, 0, 0, 8, 80, 146, 333, 328, 68, 11, 0, 0, 0, 0, 0, 0, 0,
];

export const SCORE_SAMPLE_SIZE = SCORE_BINS.reduce((a, b) => a + b, 0);

/** 분포에서 이 점수보다 높은 제품의 비율(%). 칸 안은 고르게 퍼져 있다고 본다. */
export function topPercent(score: number): number {
  const s = Math.max(0, Math.min(100, score));
  const bin = Math.min(19, Math.floor(s / 5));
  let below = 0;
  for (let i = 0; i < bin; i++) below += SCORE_BINS[i];
  below += SCORE_BINS[bin] * ((s - bin * 5) / 5);
  const top = 100 - (below / SCORE_SAMPLE_SIZE) * 100;
  return Math.max(1, Math.round(top));
}

export function scoreBin(score: number): number {
  return Math.min(19, Math.floor(Math.max(0, score) / 5));
}
