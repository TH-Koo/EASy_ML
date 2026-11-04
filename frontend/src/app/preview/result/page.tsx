import {
  ClaimMatrix,
  type MatrixClaim,
  type MatrixSource,
} from "@/components/landing/story/ClaimMatrix";
import { ResultView } from "@/components/result/ResultView";
import { cn } from "@/lib/cn";
import type { AnalysisResult } from "@/types/analysis";

/**
 * 분석 결과 화면 구성 비교 — 검토용.
 *
 * 결과 화면은 진행·실패 화면과 사정이 다르다. 15개 컴포넌트 중 13개가 이미
 * 토큰을 쓰고 있어서 "자체 CSS 를 걷어낸다" 는 일이 거의 없다. 대신 정해야
 * 할 것은 구성이다 — 지금 순서가 이 서비스의 결론을 앞에 두고 있는가.
 *
 *   A  구성 그대로, 조형만 사이트와 맞춘다
 *   B  결론을 앞으로 당기고 사이드바를 접는다
 *
 * 데이터는 표본이다. 실제 분석을 한 번 돌려서 문구 길이와 점수 분포를
 * 확인해야 최종 판단이 선다.
 */

export const metadata = { title: "Fides — 결과 화면 구성 비교" };

/* ══ 표본 ════════════════════════════════════════════════════════════ */

const PRODUCT = {
  name: "AI 절약 세탁기 21kg",
  maker: "OO전자",
  category: "세탁기",
  claims: 6,
  date: "2026.08.17",
  elapsed: "18s",
  id: "a3f2c81b",
};

const VERDICT = "근거 부족 (워싱 의심)";
const RISK = "높음";
const ACCS = 31.4;

const AXES = [
  { key: "기술 근거", sub: "KIPRIS 특허 · DART 공시", value: 42.0, old: "TES · 기술적 근거성" },
  { key: "공인 인증", sub: "KC 인증 · 전파인증 RRA", value: 18.0, old: "HES · 하드웨어 실체성" },
  { key: "기관 이력", sub: "TIPA · KORAIA · GS · NEP · 조달청", value: 35.0, old: "CES · 인증/공공 신뢰성" },
];

const EXTRA = [
  { key: "근거 채널 다양성", short: "ECS", value: 22.0 },
  { key: "분석 신뢰도", short: "CONF", value: 61.0 },
];

const XAI = [
  { rank: 1, title: "특허 이력 없음", desc: "KIPRIS 에서 이 제조사의 세탁 알고리즘 관련 출원을 찾지 못했습니다.", impact: -34, },
  { rank: 2, title: "모델 단위 인증 미확인", desc: "KC · 전파인증에 해당 모델명이 등록돼 있지 않습니다.", impact: -21 },
  { rank: 3, title: "기업 AI 활동 이력 확인", desc: "TIPA 공급기업 등록이 확인되어 일부 상쇄됐습니다.", impact: 9 },
];

const VERIFY = [
  { s: "kc", k: "KC 인증", v: "모델 미등록", intent: "warn" as const },
  { s: "rra", k: "RRA 전파인증", v: "모델 미등록", intent: "warn" as const },
  { s: "kipris", k: "KIPRIS 특허", v: "0건", intent: "warn" as const },
  { s: "dart", k: "DART 전자공시", v: "AI 언급 없음", intent: "neutral" as const },
  { s: "tipa", k: "TIPA 공급기업", v: "등록 확인", intent: "ok" as const },
];

const SOURCES: MatrixSource[] = [
  { id: "kipris", name: "KIPRIS", detail: "특허" },
  { id: "dart", name: "DART", detail: "공시" },
  { id: "tipa", name: "TIPA", detail: "공급기업" },
  { id: "kc", name: "KC", detail: "인증" },
  { id: "rra", name: "RRA", detail: "전파인증" },
];

const CLAIMS: MatrixClaim[] = [
  { id: "c1", text: "에너지 절약 자동 제어", quote: "AI 절약 모드로 최대 30% 전기 절감", status: "unsupported", hits: { kipris: 0, dart: 0, tipa: 0, kc: 0, rra: 0 } },
  { id: "c2", text: "세탁 코스 자동 추천", quote: "AI 자동 코스 추천", status: "partial", hits: { kipris: 0, dart: 0, tipa: 1, kc: 0, rra: 0 } },
  { id: "c3", text: "인버터 DD 모터", quote: "인버터 DD 모터 탑재", status: "verified", hits: { kipris: 2, dart: 0, tipa: 0, kc: 1, rra: 1 } },
];

/**
 * 위 CLAIMS 와 같은 세 주장을 결과 화면이 받는 모양(`Claim`)으로 옮긴 것.
 * 서버 `build_claims()` 가 내놓는 형태와 같다 — 격자와 대조 뷰가 같은
 * 사실을 말하는지 눈으로 대볼 수 있게 하나의 표본에서 갈라 쓴다.
 */
const LEDGER_CLAIMS: AnalysisResult["claims"] = [
  {
    id: "c1",
    text: "에너지 절약 자동 제어",
    quote: "AI 절약 모드로 최대 30% 전기 절감",
    status: "unsupported",
    evidence: [],
    note: "특허 근거 · 인증 근거",
  },
  {
    id: "c2",
    text: "세탁 코스 자동 추천",
    quote: "AI 자동 코스 추천",
    status: "partial",
    evidence: [{ source: "tipa", label: "TIPA 공급기업", record_id: null }],
    note: "특허 근거",
  },
  {
    id: "c3",
    text: "인버터 DD 모터",
    quote: "인버터 DD 모터 탑재",
    status: "verified",
    evidence: [
      { source: "kipris", label: "KIPRIS 특허", record_id: "10-2023-0091822" },
      { source: "kc", label: "KC 인증", record_id: null },
      { source: "rra", label: "RRA 전파인증", record_id: null },
    ],
    note: null,
  },
];

const MISSING = "var(--color-missing)";
const PARTIAL = "var(--color-partial)";
const VERIFIED = "var(--color-verified)";

const LABEL = "font-mono text-xs tracking-[var(--tracking-label)] text-fg-faint";

const tone = (v: number) => (v < 45 ? MISSING : v < 65 ? PARTIAL : VERIFIED);

function Bar({ v }: { v: number }) {
  return (
    <span className="bg-border block h-[3px] w-full overflow-hidden rounded-full">
      <span
        className="block h-full rounded-full"
        style={{ width: `${v}%`, background: tone(v) }}
      />
    </span>
  );
}

/**
 * 지금 화면을 그대로 띄우기 위한 표본.
 * A · B 와 같은 수치를 쓰므로 셋을 나란히 비교할 수 있다.
 */
const SAMPLE: AnalysisResult = {
  analysis_id: "a3f2c81b-4d90-4b1e-9c77-2f1a5e8d0c34",
  product: {
    name: PRODUCT.name,
    manufacturer: PRODUCT.maker,
    source: "danawa",
    category: PRODUCT.category,
    icon: "WashingMachine",
    tags: ["AI 절약", "인버터", "21kg"],
    ai_claims_count: PRODUCT.claims,
    analysis_duration_seconds: 18.2,
    analysis_date: "2026-08-17",
  },
  scores: {
    overall: ACCS,
    // 엔진 기준(fides_config: suspected 21.8 · normal 35)으로 31.4점은 '워싱 의심' = 주의 구간이다.
    // 예전 값 '위험 구간'은 점수와 맞지 않아 막대에서 핀과 칠한 구간이 어긋나 보였다.
    overall_label: "주의 구간",
    text_credibility: AXES[0].value,
    verification_credibility: AXES[1].value,
    relational_credibility: AXES[2].value,
    ecs: EXTRA[0].value,
    conf: EXTRA[1].value,
  },
  /* 표본의 `impact` 는 점수에 준 영향(음수 = 점수를 깎음)이다. 백엔드의
     `direction` 은 반대 방향을 가리킨다 — `up` 은 워싱 위험이 올랐다는
     뜻이므로 점수를 깎은 항목이 `up` 이다 (server.py 의 positive_claim
     주석 참고). */
  xai_findings: XAI.map((f) => ({
    rank: f.rank,
    title: f.title,
    description: f.desc,
    impact_percent: Math.abs(f.impact),
    direction: f.impact < 0 ? ("up" as const) : ("down" as const),
    category: "washing" as const,
  })),
  verification: {
    rows: VERIFY.map((r) => ({
      source: r.s,
      key: r.k,
      value: r.v,
      intent: r.intent,
    })),
  },
  claims: LEDGER_CLAIMS,
  meta: {
    backend: "mock",
    pipeline_version: "v1.2.0",
    model_version: "ollama/qwen2.5:7b",
    notes: null,
  },
  created_at: "2026-08-17T09:14:00+09:00",
};

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-bg border-border overflow-hidden rounded-[var(--radius-panel)] border">
      <div className="border-border flex items-center justify-between border-b px-6 py-3.5">
        <span className="fides-wordmark text-fg text-[15px] uppercase">Fides</span>
        <span className="text-fg-dim text-sm">대시보드</span>
      </div>
      {children}
    </div>
  );
}

/* ══ A · 구성 그대로, 조형만 ═════════════════════════════════════════ */

function VariantA() {
  return (
    <Frame>
      <div className="px-6 py-8">
        {/* 히어로 */}
        <div className="border-border flex flex-wrap items-start justify-between gap-6 border-b pb-7">
          <div className="min-w-0">
            <p className={LABEL}>Result · #{PRODUCT.id}</p>
            <h1 className="text-fg mt-2.5 text-2xl font-medium tracking-[var(--tracking-heading)]">
              {PRODUCT.name}
            </h1>
            <p className="text-fg-dim mt-1.5 text-xs">
              {PRODUCT.maker} · {PRODUCT.category} · 탐지 주장 {PRODUCT.claims}건
            </p>
          </div>
          <div className="text-right">
            <p className={LABEL}>ACCS</p>
            <p
              className="tnum mt-1.5 text-[40px] leading-none font-medium tracking-[var(--tracking-display)]"
              style={{ color: MISSING }}
            >
              {ACCS.toFixed(1)}
            </p>
            <p className="mt-2 font-mono text-xs tracking-[var(--tracking-label)]" style={{ color: MISSING }}>
              {RISK}
            </p>
          </div>
        </div>

        {/* 경고 */}
        <p
          className="mt-6 border-l-2 py-1 pl-4 text-xs leading-loose"
          style={{ borderColor: MISSING, color: "var(--color-fg-muted)" }}
        >
          {VERDICT} — 주장 6건 중 5건에서 대응하는 공공 기록을 찾지 못했습니다.
        </p>

        <div className="mt-9 grid grid-cols-1 gap-x-12 gap-y-9 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          {/* 본문 */}
          <div>
            <p className={LABEL}>지표별 점수</p>
            <ul className="border-border divide-border mt-3.5 divide-y border-y">
              {[...AXES.map((a) => ({ k: a.key, s: a.sub, v: a.value })),
                ...EXTRA.map((e) => ({ k: e.key, s: e.short, v: e.value }))].map((r) => (
                <li key={r.k} className="grid grid-cols-[minmax(0,1fr)_90px_46px] items-center gap-4 py-3.5">
                  <span>
                    <span className="text-fg block text-sm tracking-[var(--tracking-tight)]">{r.k}</span>
                    <span className="text-fg-dim mt-0.5 block text-xs">{r.s}</span>
                  </span>
                  <Bar v={r.v} />
                  <span className="tnum text-right text-sm font-medium" style={{ color: tone(r.v) }}>
                    {r.v.toFixed(1)}
                  </span>
                </li>
              ))}
            </ul>

            <p className={cn(LABEL, "mt-9")}>판단 근거</p>
            <ul className="border-border divide-border mt-3.5 divide-y border-y">
              {XAI.map((f) => (
                <li key={f.rank} className="py-3.5">
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="text-fg text-sm tracking-[var(--tracking-tight)]">
                      {f.title}
                    </span>
                    <span
                      className="tnum shrink-0 text-sm font-medium"
                      style={{ color: f.impact < 0 ? MISSING : VERIFIED }}
                    >
                      {f.impact > 0 ? "+" : ""}{f.impact}
                    </span>
                  </div>
                  <p className="text-fg-dim mt-1 text-xs leading-relaxed">{f.desc}</p>
                </li>
              ))}
            </ul>

            <p className={cn(LABEL, "mt-9")}>조회 상세</p>
            <ul className="border-border divide-border mt-3.5 divide-y border-y">
              {VERIFY.map((r) => (
                <li key={r.k} className="flex items-center justify-between py-3">
                  <span className="text-fg text-sm">{r.k}</span>
                  <span
                    className="text-xs"
                    style={{
                      color:
                        r.intent === "ok" ? VERIFIED : r.intent === "warn" ? MISSING : "var(--color-fg-dim)",
                    }}
                  >
                    {r.v}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* 사이드바 */}
          <aside>
            <p className={LABEL}>분석 정보</p>
            <ul className="border-border divide-border mt-3.5 divide-y border-y">
              {[["소요", PRODUCT.elapsed], ["분석일", PRODUCT.date], ["파이프라인", "v1.2.0"]].map(([k, v]) => (
                <li key={k} className="flex items-center justify-between py-2.5">
                  <span className="text-fg-dim text-xs">{k}</span>
                  <span className="text-fg tnum text-xs">{v}</span>
                </li>
              ))}
            </ul>

            <p className={cn(LABEL, "mt-8")}>빠른 작업</p>
            <div className="mt-3.5 flex flex-col gap-2">
              {["새 분석 시작", "링크 공유", "PDF 다운로드", "북마크에 저장"].map((a, i) => (
                <button
                  key={a}
                  className={cn(
                    "rounded-[var(--radius-input)] py-2 text-xs transition-colors",
                    i === 0
                      ? "bg-fg text-fg-on-brand"
                      : "border-border text-fg-dim hover:text-fg border",
                  )}
                >
                  {a}
                </button>
              ))}
            </div>

            <p className={cn(LABEL, "mt-8")}>조회 소스</p>
            <p className="text-fg-dim mt-3.5 text-xs leading-relaxed">
              KC · RRA · DART · KIPRIS · GS · NEP · TIPA · 조달청 · KORAIA
            </p>
          </aside>
        </div>
      </div>
    </Frame>
  );
}

/* ══ B · 결론을 앞으로 ═══════════════════════════════════════════════ */

function VariantB() {
  return (
    <Frame>
      {/* 툴바 — 작업을 사이드바에서 위로 올린다 */}
      <div className="border-border flex flex-wrap items-center justify-between gap-3 border-b px-6 py-3">
        <span className="text-fg-dim text-xs">← 새 분석</span>
        <span className="flex items-center gap-4 text-xs">
          <span className={LABEL}>#{PRODUCT.id} · v1.2.0</span>
          <span className="text-fg-dim">공유</span>
          <span className="text-fg-dim">PDF</span>
          <span className="text-fg-dim">북마크</span>
        </span>
      </div>

      <div className="mx-auto w-full max-w-[760px] px-6 py-9">
        {/* 결론 먼저 */}
        <p className={LABEL}>{PRODUCT.maker} · {PRODUCT.category}</p>
        <h1 className="text-fg mt-2.5 text-2xl font-medium tracking-[var(--tracking-heading)]">
          {PRODUCT.name}
        </h1>

        <div className="border-border mt-7 flex flex-wrap items-end justify-between gap-6 border-y py-6">
          <div>
            <p className="text-[19px] font-medium tracking-[var(--tracking-heading)]" style={{ color: MISSING }}>
              {VERDICT}
            </p>
            <p className="text-fg-dim mt-2 text-xs leading-loose">
              주장 6건 중 <span style={{ color: MISSING }}>5건</span>에서 대응하는
              공공 기록을 찾지 못했습니다.
            </p>
          </div>
          <div className="text-right">
            <p className={LABEL}>ACCS</p>
            <p
              className="tnum mt-1.5 text-[44px] leading-none font-medium tracking-[var(--tracking-display)]"
              style={{ color: MISSING }}
            >
              {ACCS.toFixed(1)}
            </p>
          </div>
        </div>

        {/* 랜딩에서 가르친 격자를 그대로 갚는다 */}
        <p className={cn(LABEL, "mt-10")}>주장과 근거</p>
        <p className="text-fg-dim mt-2 text-xs leading-loose">
          주장마다 공공 기록 다섯 곳을 조회하고 찾은 건수를 그대로 적습니다.
          한 줄이 전부 0이면, 그 문장은 근거가 없습니다.
        </p>
        <ClaimMatrix claims={CLAIMS} sources={SOURCES} className="mt-6" />

        {/* 왜 이 점수인가 */}
        <p className={cn(LABEL, "mt-12")}>왜 이 점수인가</p>
        <ul className="border-border divide-border mt-3.5 divide-y border-y">
          {XAI.map((f) => (
            <li key={f.rank} className="flex items-start gap-5 py-4">
              <span className="min-w-0 flex-1">
                <span className="text-fg block text-sm tracking-[var(--tracking-tight)]">
                  {f.title}
                </span>
                <span className="text-fg-dim mt-1 block text-xs leading-relaxed">
                  {f.desc}
                </span>
              </span>
              <span
                className="tnum w-12 shrink-0 text-right text-sm font-medium"
                style={{ color: f.impact < 0 ? MISSING : VERIFIED }}
              >
                {f.impact > 0 ? "+" : ""}{f.impact}
              </span>
            </li>
          ))}
        </ul>

        {/* 3축 — 랜딩과 같은 이름으로 */}
        <p className={cn(LABEL, "mt-12")}>채널별 신뢰도</p>
        <ul className="border-border divide-border mt-3.5 divide-y border-y">
          {AXES.map((a) => (
            <li key={a.key} className="grid grid-cols-[minmax(0,1fr)_110px_46px] items-center gap-5 py-4">
              <span>
                <span className="text-fg block text-sm tracking-[var(--tracking-tight)]">
                  {a.key}
                </span>
                <span className="text-fg-dim mt-0.5 block text-xs">{a.sub}</span>
              </span>
              <Bar v={a.value} />
              <span className="tnum text-right text-sm font-medium" style={{ color: tone(a.value) }}>
                {a.value.toFixed(1)}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-fg-faint mt-3 text-xs">
          근거 채널 다양성 {EXTRA[0].value.toFixed(1)} · 분석 신뢰도{" "}
          {EXTRA[1].value.toFixed(1)}
        </p>

        {/* E 자리 */}
        <div className="border-border mt-12 rounded-[var(--radius-card)] border border-dashed p-5 text-center">
          <p className={LABEL}>나중에</p>
          <p className="text-fg-dim mt-2 text-xs leading-relaxed">
            변형 E — 이 결과에 대해 묻는 자리. 되묻는 값이 전부 위 격자에서
            나오므로 대화가 성립합니다.
          </p>
        </div>
      </div>
    </Frame>
  );
}

/* ══ 페이지 ══════════════════════════════════════════════════════════ */

const VARIANTS = [
  {
    no: "현재",
    name: "지금 화면 — 손대지 않은 원본",
    says: "실물 ResultView 를 그대로 띄웠습니다. 아래 두 안과 같은 수치를 씁니다. `mock data` 배지는 표본이라 뜨는 것이고 실제 분석에서는 나오지 않습니다.",
    cost: "카드 안에 카드가 겹치고, 제목이 800 굵기, KPI 다섯 줄이 결론보다 앞에 옵니다. 사이드바의 조회 소스 목록은 모든 결과에서 같은 내용입니다.",
    render: (
      <div className="border-border overflow-hidden rounded-[var(--radius-panel)] border">
        <ResultView data={SAMPLE} elapsedSeconds={18} />
      </div>
    ),
  },
  {
    no: "A",
    name: "구성 그대로 · 조형만",
    says: "지금 순서(히어로 → 경고 → KPI → XAI → 조회표 / 사이드바)를 유지한 채 상자를 걷어내고 토큰으로 통일합니다. 카드 안에 카드가 겹치던 것과 800 굵기가 사라집니다.",
    cost: "이 서비스의 결론인 '어느 주장에 근거가 없는가'가 여전히 KPI 다섯 줄 뒤에 있습니다. 사이드바의 조회 소스 목록은 모든 결과에서 똑같은 내용입니다.",
    render: <VariantA />,
  },
  {
    no: "B",
    name: "결론을 앞으로 · 한 단",
    says: "판정과 ACCS 를 맨 앞에 두고, 랜딩에서 가르친 주장×소스 격자를 그대로 갚습니다. 작업은 사이드바에서 툴바로 올리고, 매 결과 같은 내용인 조회 소스 목록은 뺐습니다. 3축 이름도 랜딩과 맞춥니다 — HES/TES/CES 대신 공인 인증/기술 근거/기관 이력.",
    cost: "한 단이라 스크롤이 깁니다. 사이드바가 없어 긴 결과에서 작업 버튼이 멀어집니다(툴바를 sticky 로 두면 해결됩니다).",
    render: <VariantB />,
  },
];

export default function ResultPreview() {
  return (
    <main className="bg-surface min-h-dvh pb-24">
      <div className="mx-auto w-full max-w-[1200px] px-5 pt-16 md:px-10">
        <p className={LABEL}>PREVIEW</p>
        <h1 className="text-fg mt-3 text-2xl font-medium tracking-[var(--tracking-heading)] md:text-[27px]">
          분석 결과 화면 — 두 가지
        </h1>
        <p className="text-fg-dim mt-4 max-w-[760px] text-xs leading-loose">
          결과 화면은 사정이 다릅니다. 15개 컴포넌트 중 13개가 이미 토큰을 쓰고
          있어서 걷어낼 자체 CSS 가 거의 없습니다. 정해야 할 것은 구성입니다 —
          지금 순서가 이 서비스의 결론을 앞에 두고 있는가.
        </p>
        <p className="text-fg-faint mt-3 max-w-[760px] text-xs leading-loose">
          데이터는 표본입니다. 실제 분석을 한 번 돌려서 XAI 문구 길이와 점수
          분포를 봐야 최종 판단이 섭니다.
        </p>
      </div>

      <div className="mt-12 flex flex-col gap-16">
        {VARIANTS.map((v) => (
          <section key={v.no} className="mx-auto w-full max-w-[1200px] px-5 md:px-10">
            <div className="border-border border-t pt-5">
              <p className={LABEL}>변형 {v.no}</p>
              <h2 className="text-fg mt-2 text-[17px] font-medium tracking-[var(--tracking-tight)]">
                {v.name}
              </h2>
              <div className="mt-2 grid max-w-[920px] grid-cols-1 gap-x-10 gap-y-1.5 sm:grid-cols-2">
                <p className="text-fg-dim text-xs leading-relaxed">{v.says}</p>
                <p className="text-fg-faint text-xs leading-relaxed">↔ {v.cost}</p>
              </div>
            </div>
            <div className="mt-6">{v.render}</div>
          </section>
        ))}
      </div>
    </main>
  );
}
