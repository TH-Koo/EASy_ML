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

/* "부족" 은 광고가 틀렸다고 단정하는 말이라, 찾지 못했다는 사실 그대로
   "미확인" 으로 쓴다. 제목에는 앞에 "근거" 를 붙인다(근거 일부 확인). */
export const VERDICT_STEPS = ["충분", "일부 확인", "미확인"] as const;

/** 판정 단계 색 — 큰 판정 글씨와 점수 막대의 지금 구간에 쓴다. */
export const VERDICT_COLOR = [
  "var(--claim-ok)",
  "var(--claim-part)",
  "var(--claim-no)",
] as const;

/**
 * 점수 막대의 구간 경계. fides_config.py 의 VerdictThresholds
 * (suspected 21.8 · normal 35)와 같다. 엔진은 신뢰도도 함께 보므로 드물게
 * 핀이 판정과 다른 구간에 설 수 있다 — 막대는 판정 단계 색을 따른다.
 */
export const SCORE_ZONES = { low: 21.8, high: 35 } as const;

/** 백엔드 구간 라벨 → 화면 3단계. "판정 제외"는 단계가 없다. */
export function verdictLevel(label: OverallLabel): VerdictLevel | null {
  if (label === "양호 구간") return 0;
  if (label === "주의 구간") return 1;
  if (label === "위험 구간") return 2;
  return null;
}

/**
 * 저장된 기록의 판정 문구 → 화면 3단계. 기록 목록에는 구간 라벨 없이 엔진 문구만
 * 온다. server.py 가 문구를 구간 라벨로 바꾸는 기준과 같다.
 */
export function verdictLevelFromText(verdict: string): VerdictLevel | null {
  if (verdict.includes("신뢰")) return 0;
  if (verdict.includes("AI 워싱 상품")) return 2;
  if (verdict.includes("워싱 의심")) return 1;
  return null;
}

export function verdictTitle(label: OverallLabel): string {
  const level = verdictLevel(label);
  if (level === null) return "판정하지 않았어요";
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
  verified: { label: "근거 확인", rank: 0 },
  partial: { label: "일부 확인", rank: 1 },
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
  // 판정 제외는 광고에서 AI 기능을 찾지 못했다는 뜻이다. ai_claims_count 는 이때도
  // 0 이 아닐 수 있어(판정 이유 개수로 채워진다) "N개를 맞춰 봤어요"라고 하면 틀린다.
  if (verdictLevel(data.scores.overall_label) === null && claims.length === 0) {
    return "이 제품 광고에서 확인할 AI 기능을 찾지 못했어요";
  }
  if (claims.length === 0) {
    const n = data.product.ai_claims_count;
    return n > 0
      ? `광고한 AI 기능 ${n}개와 관련 자료를 대조했어요`
      : "광고에서 AI 기능 주장을 찾지 못했어요";
  }
  // 위 큰 판정(근거 충분 등)은 점수 구간이라, 여기서 "확인된 게 없어요"처럼
  // 판정과 반대로 읽히는 말을 하지 않는다. '일부' 근거가 있으면 그 사실을 말한다.
  const { verified, partial } = countByStatus(claims);
  const n = claims.length;
  if (verified === n) {
    return `광고한 AI 기능 ${n}개 모두 분석 기준에 맞는 근거가 확인됐어요`;
  }
  if (verified === 0 && partial === 0) {
    return `광고한 AI 기능 ${n}개를 뒷받침하는 근거가 이번 조회에서 확인되지 않았어요`;
  }
  if (verified === 0) {
    return partial === n
      ? `광고한 AI 기능 ${n}개 모두 관련 근거가 일부 확인됐어요`
      : `광고한 AI 기능 ${n}개 중 ${partial}개는 관련 근거가 일부 확인됐어요`;
  }
  return partial > 0
    ? `광고한 AI 기능 ${n}개 중 ${verified}개는 확인, ${partial}개는 일부 확인됐어요`
    : `광고한 AI 기능 ${n}개 중 ${verified}개는 분석 기준에 맞는 근거가 확인됐어요`;
}

/* ── 제품 이름 ─────────────────────────────────────────────────────── */

/** 판매처·구매 조건처럼 제품을 설명하지 않는 괄호 내용 */
const NAME_NOISE =
  /일반\s*판매처|일반\s*구매|전국\s*무료|공식\s*인증|설치|단품|정품|해외\s*구매|병행\s*수입/;

/**
 * 다나와 이름 → 이름 + 옵션. `Seagate SkyHawk AI 7200/512M (12TB, ST12000VE003)` 은
 * 제목으로 쓰기에 길어서, 끝의 괄호를 떼어 아랫줄에 작게 쓴다. 판매처 같은 내용은 뺀다.
 */
export function splitProductName(raw: string): {
  title: string;
  detail: string | null;
} {
  const name = raw.replaceAll("&amp;", "&").trim();
  const match = /^(.+?)\s*\(([^()]+)\)\s*$/.exec(name);
  if (!match) return { title: name, detail: null };
  return {
    title: match[1],
    detail: NAME_NOISE.test(match[2]) ? null : match[2],
  };
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
  kipris: {
    name: "특허정보 KIPRIS",
    role: "특허의 기술 내용과 출원·등록 상태를 검색하는 서비스",
  },
  dart: {
    name: "기업 공시 DART",
    role: "기업이 제출한 사업보고서에서 사업·연구개발 내용을 확인하는 서비스",
  },
  kc: { name: "KC 인증", role: "전기용품이 안전 기준을 통과했다는 국가 인증" },
  rra: {
    name: "제품 인증 RRA",
    role: "국립전파연구원의 전파·전자파 관련 적합성평가 기록",
  },
  tipa: { name: "TIPA", role: "AI 공급기업 명단" },
  koraia: {
    name: "한국인공지능산업협회",
    role: "국내 AI 기업들이 모인 협회의 회원 명단",
  },
  gs: { name: "GS 인증", role: "소프트웨어가 품질 시험을 통과했다는 인증" },
  nep: {
    name: "신제품 인증 NEP",
    role: "새 기술이 처음 적용된 제품에 주는 인증",
  },
  procurement: {
    name: "조달청",
    role: "공공기관 납품을 위해 등록한 제품 목록",
  },
  tta: { name: "TTA·GS 인증", role: "소프트웨어 품질 시험·인증 기록" },
  ntis: {
    name: "국가 연구개발 NTIS",
    role: "국가 연구개발 과제와 참여기관·성과를 검색하는 서비스",
  },
  iitp: { name: "IITP 연구과제", role: "정보통신 분야 국가 연구과제 기록" },
  nipa: {
    name: "NIPA AI 공급기업",
    role: "정부가 인정한 AI 솔루션 공급기업 명단",
  },
  koneps: { name: "나라장터", role: "공공기관 입찰에서 낙찰받은 기록" },
  kaiac: { name: "KAIAC 인증", role: "AI 제품 품질 인증 기록" },
  seller_page: {
    name: "판매자 기능 설명",
    role: "판매자가 제품의 기능과 작동 방식을 설명한 상품 상세페이지",
  },
};

/** 출처가 확인해 주는 범위. 자료의 존재와 제품 적용·성능 검증을 구분한다. */
export const SOURCE_SCOPE: Record<string, string> = {
  kipris:
    "관련 기술의 특허 기록을 확인하는 자료예요. 이 제품에 실제 적용됐는지는 별도로 확인해야 해요.",
  rra: "제품의 전파·전자파 관련 인증 이력을 확인해요. AI 작동 방식이나 절전 성능을 입증하는 자료는 아니에요.",
  kc: "제품의 안전 인증 이력을 확인해요. AI 기능의 구현 여부나 성능은 별도로 확인해야 해요.",
  dart: "제조사가 공개한 사업·연구개발 내용을 확인해요. 회사 차원의 기록과 해당 제품의 적용 근거는 구분해요.",
  ntis: "국가 연구개발 참여·성과를 확인해요. 해당 연구가 이 제품에 적용됐는지는 별도로 확인해야 해요.",
  seller_page:
    "판매자가 광고한 기능을 확인해요. 외부 시험이나 실제 성능 검증 결과인지는 별도로 살펴봐야 해요.",
};

export function sourceDetails(source: string): { role: string; scope: string } {
  const id = source.toLowerCase();
  return {
    role: infoFor(source)?.role ?? "분석에 연결된 관련 자료예요.",
    scope:
      SOURCE_SCOPE[id] ??
      "이 기록이 광고한 기능과 같은 기술·제품을 설명하는지 함께 확인해야 해요.",
  };
}

/** 백엔드가 `SELLER_PAGE` 처럼 대문자로 보내는 경우도 같은 항목으로 찾는다. */
function infoFor(source: string): SourceInfo | undefined {
  return SOURCE_INFO[source] ?? SOURCE_INFO[source.toLowerCase()];
}

export function sourceName(ref: Pick<EvidenceRef, "source" | "label">): string {
  return infoFor(ref.source)?.name ?? infoFor(ref.label)?.name ?? ref.label;
}

/**
 * 온톨로지 매핑 id(`sys_tech_baseline`, `CAP_DISHWASH_COURSE`)처럼 사람이
 * 읽을 문장이 아닌 값인가. 백엔드가 광고 문구 자리에 패턴 id 를 넣어 보내는
 * 경우가 있어 화면에 내보내기 전에 거른다.
 */
export function isInternalId(text: string | null | undefined): boolean {
  if (!text) return false;
  return (
    /^[A-Za-z0-9]+(?:[_.:-][A-Za-z0-9]+)+$/.test(text.trim()) && /_/.test(text)
  );
}

/** 화면에 보여 줄 광고 문구. 내부 id 면 null. */
export function displayQuote(claim: Pick<Claim, "quote">): string | null {
  return claim.quote && !isInternalId(claim.quote) ? claim.quote : null;
}

/** 기록 제목. 백엔드가 제목 대신 출처 id(`SELLER_PAGE`)를 넣어 보낸 경우 설명으로 바꾼다. */
export function recordTitle(ref: Pick<EvidenceRef, "label">): string {
  return (
    infoFor(ref.label)?.role ??
    (isInternalId(ref.label) ? "관련 기록" : ref.label)
  );
}

/** 근거를 출처별로 묶어 칩으로 쓴다. 예) "특허청 KIPRIS 2" */
export function evidenceChips(claim: Claim): string[] {
  if (claim.evidence.length === 0) {
    // 근거가 없으면 백엔드가 남긴 사유("KIPRIS 0건 · DART 0건")를 그대로 쓴다.
    return claim.note
      ? claim.note
          .split("·")
          .map((s) => s.trim())
          .filter((s) => s && !isInternalId(s))
      : [];
  }
  const counts = new Map<string, number>();
  for (const ref of claim.evidence) {
    const name = sourceName(ref);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts].map(([name, n]) => (n > 1 ? `${name} ${n}` : name));
}

/**
 * 찾은 공공 기록을 종류별로 센다 — 요약 띠의 "찾은 공공 기록" 칸.
 * 판매 페이지는 공공 기록이 아니라 뺀다.
 */
const RECORD_KIND: Record<string, string> = {
  kipris: "특허",
  kc: "인증",
  rra: "인증",
  gs: "인증",
  nep: "인증",
  dart: "공시",
  tipa: "이력",
  koraia: "이력",
  procurement: "이력",
  ntis: "R&D",
  iitp: "R&D",
};

export function recordTally(claims: Claim[]): {
  total: number;
  kinds: [string, number][];
} {
  const counts = new Map<string, number>();
  const seen = new Set<string>();
  for (const c of claims) {
    for (const e of c.evidence) {
      const key = JSON.stringify([
        e.source.toLowerCase(),
        e.record_id ?? e.label,
      ]);
      if (seen.has(key)) continue;
      seen.add(key);
      const kind = RECORD_KIND[e.source.toLowerCase()];
      if (kind) counts.set(kind, (counts.get(kind) ?? 0) + 1);
    }
  }
  const kinds = [...counts].sort((a, b) => b[1] - a[1]);
  return { total: kinds.reduce((n, [, v]) => n + v, 0), kinds };
}

/* ── "쉽게 말하면" ────────────────────────────────────────────────────── */

export interface PlainExplanation {
  meaning: string;
  sources: SourceInfo[];
  role: string;
}

const MEANING: Record<ClaimStatus, string> = {
  verified:
    "이 기능을 뒷받침하는 관련 자료가 확인돼 ‘근거 확인’으로 판단했어요.",
  partial:
    "이 기능에 연결된 자료는 찾았어요. 다만 제품 적용 여부나 구체적인 작동 방식 등 추가 확인이 필요해요.",
  unsupported:
    "이 기능을 뒷받침할 자료가 없거나, 찾은 자료만으로 기능을 확인하기 어려워 ‘미확인’으로 판단했어요. 기능이 없거나 허위라는 뜻은 아니에요.",
};

const ROLE: Record<ClaimStatus, string> = {
  verified:
    "연결된 자료가 기능별 확인 기준을 충족한 것으로 분석됐어요. 기능의 실제 성능을 시험한 결과와는 구분해 주세요.",
  partial:
    "자료가 광고한 기능의 어떤 부분을 설명하는지, 해당 제품과 직접 연결되는지를 함께 살펴봐요.",
  unsupported:
    "자료의 존재만으로 기능 적용을 확인하지 않아요. 이 제품의 기능을 뒷받침할 근거가 충분하지 않으면 ‘미확인’으로 표시해요.",
};

export function spaceMiddleDots(text: string): string {
  return text.replace(/\s*·\s*/g, " · ");
}

export function explain(claim: Claim): PlainExplanation {
  const ids = new Set(claim.evidence.map((e) => e.source.toLowerCase()));
  // 근거가 없을 때는 사유 문구에 적힌 기관만 출처로 보여 준다.
  if (ids.size === 0 && claim.note) {
    for (const id of Object.keys(SOURCE_INFO)) {
      if (claim.note.toLowerCase().includes(id)) ids.add(id);
    }
  }
  const components = (claim.components ?? [])
    .filter((component) => !["없음", "없음 또는 상황 의존", "해당 없음"].includes(component.name))
    .sort((a, b) => b.support - a.support);
  if (components.length > 0) {
    const supported = components.filter((component) => component.fulfilled);
    const weak = components.filter((component) => !component.fulfilled);
    const names = (items: typeof components) => items.slice(0, 3).map((item) => spaceMiddleDots(item.name)).join(" · ")
      + (items.length > 3 ? ` 등 ${items.length}개 구성 요소` : "");
    let meaning = supported.length > 0
      ? `${names(supported)} 관련 자료를 찾았어요.`
      : `${names(components)}에 관한 자료를 살펴봤지만, 기능을 뒷받침할 근거는 충분하지 않았어요.`;
    if (weak.length > 0 && supported.length > 0) {
      meaning += ` ${names(weak)}는 근거가 부족해 추가 확인이 필요해요.`;
    }
    meaning += claim.status === "verified"
      ? " 이 자료들이 광고한 기능을 뒷받침하는 확인 기준을 충족해 ‘근거 확인’으로 판단했어요."
      : claim.status === "partial"
        ? " 관련 자료는 있지만, 광고한 기능 전체를 뒷받침하기에는 부족해 ‘일부 확인’으로 판단했어요."
        : claim.evidence.length === 0
          ? " 이 기능에 연결된 근거를 찾지 못해 ‘미확인’으로 판단했어요."
          : " 찾은 자료만으로는 광고한 기능을 확인하기 어려워 ‘미확인’으로 판단했어요.";
    return {
      meaning,
      sources: [...ids].map((id) => SOURCE_INFO[id]).filter(Boolean),
      role: "구성 요소 이름은 기능을 살펴보는 분석 항목이에요. 특허·공시는 제조사의 관련 기술 이력을 보여 주며, 이 제품의 실제 적용 여부와 성능은 제품에 직접 연결된 자료로 별도 확인해야 해요.",
    };
  }
  return {
    meaning: MEANING[claim.status],
    sources: [...ids].map((id) => SOURCE_INFO[id]).filter(Boolean),
    role: ROLE[claim.status],
  };
}

/* ── 점수 위치 ───────────────────────────────────────────────────────── */

/**
 * 지금까지 분석해 둔 제품의 표시 점수 분포(5점 단위 개수).
 *
 * artifacts/rescore_v2_ontology/features.csv 의 rule_dynamic_accs 1,251건에
 * 표시 변환(fides_scoring.display_score, v2)을 씌워 셌다. 화면의 점수가
 * 표시 점수라 분포도 같은 눈금이어야 한다. 원점수는 35~55점에 몰려 있어
 * 변환 뒤에도 50~75점이 두텁다. 표본이나 변환 앵커가 바뀌면 다시 센다.
 */
export const SCORE_BINS: readonly number[] = [
  276, 1, 0, 0, 0, 0, 0, 8, 37, 131, 58, 74, 203, 284, 99, 46, 23, 11, 0, 0,
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
