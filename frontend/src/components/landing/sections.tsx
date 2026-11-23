import { CaseCard } from "@/components/landing/CaseCard";
import { ChromeObject } from "@/components/landing/ChromeObject";
import { CtaBanner } from "@/components/landing/CtaBanner";
import { HeroCta } from "@/components/landing/HeroCta";
import { HeroSearch } from "@/components/landing/HeroSearch";
import { IconTile } from "@/components/landing/IconTile";
import { LandingFooter } from "@/components/landing/LandingFooter";
import { LandingNav } from "@/components/landing/LandingNav";
import { GradientTile, StaggeredCards } from "@/components/landing/StaggeredCards";
import { WaveLines } from "@/components/landing/WaveLines";
import { AdMockup, type AdQuote } from "@/components/landing/story/AdMockup";
import {
  ClaimMatrix,
  type MatrixClaim,
  type MatrixSource,
} from "@/components/landing/story/ClaimMatrix";
import { ContrastList } from "@/components/landing/story/ContrastList";
import { ImageSlot } from "@/components/landing/story/ImageSlot";
import { SourceTable } from "@/components/landing/story/SourceTable";
import { StatGrid } from "@/components/landing/story/StatGrid";
import { StepFlow } from "@/components/landing/story/StepFlow";
import { RevealGroup } from "@/components/motion/RevealGroup";
import { Eyebrow } from "@/components/primitives/Eyebrow";
import { Section } from "@/components/primitives/Section";
import { cn } from "@/lib/cn";

/**
 * 랜딩 섹션 모음.
 *
 * 화면 수를 줄인 변형(8칸·6칸)이 같은 코드를 쓰도록 조각으로 뽑아 놓았다.
 * 카피와 데이터는 여기 한 곳에만 있으므로, 문구를 고치면 모든 변형에
 * 동시에 반영된다.
 */

/* ══ 데이터 ══════════════════════════════════════════════════════════ */

/**
 * 실제 상품 페이지에서 흔히 보이는 표현. 특정 브랜드는 지목하지 않는다.
 * `product` 는 문구가 붙어 있던 물건이며 목업의 형상이 된다.
 */
const AD_QUOTES: AdQuote[] = [
  {
    headline: "인공지능 DD",
    body: "청바지, 셔츠 등 세탁물의 무게와 부드러움을 감지해 세탁 패턴을 맞춥니다",
    product: "washer",
  },
  {
    headline: "AI 매직 리모컨",
    body: "AI 버튼을 눌러 궁금한 것을 물어보거나 도움을 요청하세요",
    product: "remote",
  },
  {
    headline: "인공지능 냉기케어 시스템",
    body: "사용 패턴에 맞춰 생각하고 움직입니다",
    product: "fridge",
  },
];

const GLOBAL_STATS = [
  {
    value: 58,
    label: "글로벌 기업",
    caption: "AI 역량을 실제보다 부풀려 알린 적이 있다고 답한 비율",
    tone: "missing" as const,
  },
  {
    value: 72,
    label: "북미 기업",
    caption: "같은 질문에 그렇다고 답한 비율 — 시장이 클수록 높아진다",
    tone: "missing" as const,
  },
];

const DOMESTIC_STATS = [
  {
    value: 61,
    label: "전담조직 부재",
    caption: "AI 신뢰성을 검토할 조직을 두지 않은 국내 기업 비율",
    tone: "missing" as const,
  },
  {
    value: 48,
    label: "검증절차 부재",
    caption: "주장을 검증하는 절차 자체가 없다고 답한 비율",
    tone: "missing" as const,
  },
];

const STEPS = [
  {
    title: "AI 주장 추출",
    items: [
      "상품 페이지와 상세 이미지에서 AI 관련 문구를 걷어냅니다",
      "핵심 주장 요소를 기능 단위로 구조화합니다",
      "분석 대상을 자동으로 분류합니다",
    ],
  },
  {
    title: "근거 데이터 검증",
    items: [
      "특허 · 인증 · 공시 9개 소스를 병렬로 조회합니다",
      "주장과 근거가 실제로 맞물리는지 대조합니다",
      "근거 부족과 과장 가능성을 탐지합니다",
    ],
  },
  {
    title: "평가 결과 제공",
    items: [
      "신뢰성과 설명 충분성을 점수로 산출합니다",
      "AI 워싱 위험도를 등급으로 제시합니다",
      "판단에 쓰인 근거를 그대로 공개합니다",
    ],
  },
];

/** ontology/source_credibility_master.csv 의 값을 그대로 옮겼다. */
const SOURCES = [
  { name: "KC · 전파인증 DB", role: "제품 실체와 모델 단위 하드웨어 존재 확인", weight: 0.95 },
  { name: "RRA 전파인증", role: "통신 · 전파 장치 관련 제품과 모델 확인", weight: 0.95 },
  { name: "DART 전자공시", role: "기업 차원의 AI 사업 · 투자 · 기술 방향 확인", weight: 0.92 },
  { name: "KIPRIS 특허", role: "기술 보유와 알고리즘 · 모델 관련 근거", weight: 0.9 },
  { name: "GS 인증", role: "소프트웨어 품질과 제품 단위 인증 근거", weight: 0.88 },
  { name: "NEP 인증", role: "신기술성 인증 근거", weight: 0.88 },
  { name: "TIPA 공급기업", role: "기업 차원의 AI 솔루션 보유 여부 확인", weight: 0.8 },
  { name: "조달청 등록 정보", role: "공공 조달 등록 제품의 설명과 기능 확인", weight: 0.78 },
  { name: "KORAIA 협회 정보", role: "기업의 AI 관련 활동 존재 여부 보조 확인", weight: 0.72 },
];

const CONTRASTS = [
  {
    axis: "타겟 차별성",
    title: "주장의 신뢰성에 초점",
    before: "내부 AI 시스템 운영과 리스크 관리 중심",
    after: "상품과 기업이 밖으로 내세운 AI 주장 자체를 검증",
  },
  {
    axis: "분석 차별성",
    title: "주장과 근거를 연결해 분석",
    before: "정책 준수 · 모니터링 · 컴플라이언스 중심",
    after: "외부 공공 근거 데이터와 교차검증",
  },
  {
    axis: "결과 차별성",
    title: "신뢰성과 설명 충분성을 제시",
    before: "기업 내부용 거버넌스 · 감사 도구 중심",
    after: "소비자가 이해할 수 있는 설명형 평가 결과",
  },
];

/**
 * 대조 매트릭스의 열. 0건이 나온 소스도 빼지 않는다 — 열이 없으면
 * "안 찾아봤다"로 읽히지만 0이 적혀 있으면 "찾아봤는데 없었다"가 된다.
 */
const MATRIX_SOURCES: MatrixSource[] = [
  { id: "kipris", name: "KIPRIS", detail: "특허" },
  { id: "dart", name: "DART", detail: "공시" },
  { id: "tipa", name: "TIPA", detail: "공급기업" },
  { id: "kc", name: "KC", detail: "인증" },
  { id: "rra", name: "RRA", detail: "전파인증" },
];

/** 실데이터 연결 전까지 쓰는 예시. 4단계에서 백엔드 `claims` 로 교체한다. */
const SAMPLE_CLAIMS: MatrixClaim[] = [
  {
    id: "c1",
    text: "에너지 절약 자동 제어",
    quote: "AI 절약 모드로 최대 30% 전기 절감",
    status: "unsupported",
    hits: { kipris: 0, dart: 0, tipa: 0, kc: 0, rra: 0 },
  },
  {
    id: "c2",
    text: "세탁 코스 자동 추천",
    quote: "AI 자동 코스 추천",
    status: "partial",
    hits: { kipris: 0, dart: 0, tipa: 1, kc: 0, rra: 0 },
  },
  {
    id: "c3",
    text: "인버터 DD 모터",
    quote: "인버터 DD 모터 탑재",
    status: "verified",
    hits: { kipris: 2, dart: 0, tipa: 0, kc: 1, rra: 1 },
  },
];

const H2 =
  "text-2xl leading-snug font-medium tracking-[var(--tracking-heading)] md:text-[27px]";

/* ══ 섹션 ════════════════════════════════════════════════════════════ */

/**
 * 첫 화면 — 제목과 오브젝트, 그리고 시작 버튼 하나.
 *
 * 한때 이 자리를 검색창으로 바꿨다가 되돌렸다. 로그인하지 않은 사람에게는
 * 검색창이 눌리는 순간 로그인으로 튕기는 가짜 입력이었다 — 쓸 수 없는
 * 입력창을 첫 화면에 두느니 갈 곳을 분명히 적은 버튼이 낫다.
 *
 * 버튼은 하나만 둔다. `자세히 보기` 는 아래로 내리는 링크였는데, 어차피
 * 스크롤하면 바로 이어지는 화면을 버튼으로 또 안내할 이유가 없었다.
 */
export function HeroSection() {
  return (
    <Section id="hero" tone="gradient" bare full>
      <LandingNav />
      <div className="section-motion mx-auto flex w-full max-w-[1200px] flex-col gap-10 px-5 pt-24 pb-20 md:flex-row md:items-center md:px-10">
        <RevealGroup className="min-w-0 flex-1">
          <Eyebrow className="text-white/70">Evidence over Claims</Eyebrow>
          <h1 className="mt-5 text-[28px] leading-[1.4] font-medium tracking-[var(--tracking-heading)] text-white md:text-[34px]">
            주장이 아니라 근거로
            <br />
            판단하는 AI 검증,
            <br />
            오직 Fides에서
          </h1>
          {/* 갈 곳은 HeroCta 가 실제 세션을 보고 정한다 */}
          <HeroCta className="mt-8" />
        </RevealGroup>

        <ChromeObject className="section-parallax h-[200px] w-[250px] shrink-0 self-center md:h-[270px] md:w-[330px]" />
      </div>
    </Section>
  );
}

/**
 * 문제 제기.
 *
 * 인용문을 3열로 적기만 하던 화면이었다. 문장은 맞았지만 글자만 남아,
 * "지금 팔리는 제품에 적혀 있다"는 주장이 눈으로 확인되지 않았다.
 * 그래서 문구가 붙어 있던 자리(상세 페이지)를 3D 목업으로 뒤에 두고
 * 그 위로 문구가 떠오르게 했다 — 인용문 자체는 그대로다.
 *
 * `withStats` 를 켜면 통계를 같은 화면에 흡수한다 — "이 문장들이 팔린다"와
 * "글로벌 58%가 부풀린 적 있다"는 같은 주장의 앞뒤라 붙어도 무리가 없다.
 * 목업이 화면의 절반을 쓰므로, 이때는 좌우로 나눈다.
 */
export function ProblemSection() {
  return (
    <Section id="problem" tone="ink" full reveal flow>
      <Eyebrow className="text-white/45">The Problem</Eyebrow>
      <h2 className={`mt-4 ${H2}`}>
        이 문장들은 지금 팔리는 제품에
        <br />
        그대로 적혀 있습니다
      </h2>
      {/* 조사 수치는 뺐다. 숫자 두 개를 옆에 세우면 어느 기준선에도 걸리지
          않아 붕 뜨고, 이 화면이 설득하는 방식은 통계가 아니라 실물이다.
          같은 데이터가 필요하면 ScaleSection 이 그대로 갖고 있다. */}
      {/* 한 줄로 떨어지는 폭(측정 824px)에 여유만 얹는다. 두 줄이 되면
          제목과 목업 사이에 덩어리가 하나 더 생겨 흐름이 끊긴다. */}
      <p className="mt-4 max-w-[880px] text-xs leading-loose text-white/60">
        <strong className="font-medium text-white">AI 워싱</strong> — 실제 AI
        기술이 없거나 미미함에도 AI 기능을 과장해 소비자를 오인하게 만드는
        행위. 소비자는 더 비싼 값을 치르고, 정보 비대칭은 깊어지며, 결국 기업과
        플랫폼의 신뢰가 함께 무너집니다.
      </p>

      <AdMockup quotes={AD_QUOTES} className="mt-10" />
    </Section>
  );
}

export function ScaleSection() {
  return (
    <Section id="scale" tone="surface" full reveal flow>
      <Eyebrow>The Scale</Eyebrow>
      <h2 className={`text-fg mt-4 ${H2}`}>
        드문 일이 아닙니다.
        <br />
        그리고 막을 장치도 없습니다.
      </h2>
      <div className="mt-9 grid grid-cols-1 gap-x-12 gap-y-10 lg:grid-cols-2">
        <StatGrid
          stats={GLOBAL_STATS}
          source="Google Cloud · 글로벌 16개국 임원 1,400여 명 조사"
        />
        <StatGrid stats={DOMESTIC_STATS} source="대한상공회의소 · 기업 실태 조사" />
      </div>
    </Section>
  );
}

export function ApproachSection() {
  return (
    <Section id="approach" tone="canvas" full reveal flow>
      <Eyebrow>The Approach</Eyebrow>
      <h2 className={`text-fg mt-4 ${H2}`}>
        그래서 광고가 아니라
        <br />
        <span className="text-brand-fg">기록을 읽기로 했습니다</span>
      </h2>
      <p className="text-fg-dim mt-3.5 max-w-[560px] text-xs leading-loose">
        상품 URL 하나를 넣으면 주장을 문장 단위로 뜯어내고, 국가 데이터베이스에
        남은 흔적과 하나씩 맞춰봅니다.
      </p>
      <StepFlow steps={STEPS} className="mt-10" />
    </Section>
  );
}

/** `withSteps` 를 켜면 3단계 요약을 같이 얹어 `해결 방식` 화면을 대신한다. */
export function LedgerSection({ withSteps }: { withSteps?: boolean }) {
  const proven = SAMPLE_CLAIMS.filter((c) => c.status === "verified").length;

  return (
    <Section id="ledger" tone="surface" full reveal flow>
      <Eyebrow>Claim &amp; Evidence</Eyebrow>
      <h2 className={`text-fg mt-4 ${H2}`}>붙지 않는 문장이 결론입니다</h2>
      <p className="text-fg-dim mt-2.5 max-w-[760px] text-xs leading-loose">
        주장마다 공공 기록 다섯 곳을 조회하고 찾은 건수를 그대로 적습니다.
        한 줄이 전부 0이면, 그 문장은 근거가 없습니다.
        <span className="text-fg-faint hidden lg:inline">
          {" "}
          — 행에 마우스를 올리면 그 줄만 다시 조회합니다.
        </span>
      </p>
      {withSteps ? (
        <p className="text-fg-faint mt-2 font-mono text-xs">
          주장 추출 → 근거 대조 → 판정
        </p>
      ) : null}

      <ClaimMatrix
        claims={SAMPLE_CLAIMS}
        sources={MATRIX_SOURCES}
        className="mt-9"
      />

      <p className="text-fg-dim tnum mt-9 font-mono text-xs">
        {SAMPLE_CLAIMS.length}개 주장 중 {proven}개 입증 · 근거 부재율{" "}
        {Math.round(((SAMPLE_CLAIMS.length - proven) / SAMPLE_CLAIMS.length) * 100)}%
      </p>
    </Section>
  );
}

export function ChannelsSection() {
  return (
    <Section id="channels" tone="ink" bare full flow>
      <WaveLines className="section-parallax w-[170px] opacity-50" />
      <RevealGroup className="section-motion relative mx-auto flex w-full max-w-[1200px] flex-col gap-9 px-5 py-16 md:flex-row md:px-10">
        <div className="md:w-[32%] md:shrink-0">
          <h2 className="text-2xl font-medium tracking-[var(--tracking-heading)] md:text-[26px]">
            Our Channels
          </h2>
          <p className="text-fg-subtle mt-4 text-xs leading-loose">
            세 채널을 교차해 하나의 점수로 수렴시킵니다. 가중치는 고정값이 아니라
            근거 강도에 따라 매번 다시 계산됩니다.
          </p>
        </div>

        <StaggeredCards className="flex-1">
          <GradientTile
            eyebrow="Technical · w 0.40"
            title="기술 근거 검증"
            description={<>KIPRIS 특허 출원 이력과 DART 공시 R&amp;D 대조</>}
          />
          <GradientTile
            eyebrow="Horizontal · w 0.35"
            title="공인 인증 조회"
            description="KC 인증 · 전파인증 RRA 제품 모델 단위 확인"
            glowCorner="tr"
          />
          <GradientTile
            eyebrow="Contextual · w 0.25"
            title="기관 이력 대조"
            description="TIPA · KORAIA · GS · NEP · 조달청 공인 이력"
            glowCorner="bl"
          />
          <GradientTile
            eyebrow="Explainable"
            title="판단 근거 공개"
            description="점수에 기여한 요인과 가중치를 그대로 노출"
            deep
            glowCorner="none"
          />
        </StaggeredCards>
      </RevealGroup>
    </Section>
  );
}

export function SourcesSection() {
  return (
    <Section id="sources" tone="canvas" full reveal flow>
      <Eyebrow>Evidence Sources</Eyebrow>
      <h2 className={`text-fg mt-4 ${H2}`}>무엇을 근거로 삼는지 밝힙니다</h2>
      <p className="text-fg-dim mt-2.5 max-w-[600px] text-xs leading-loose">
        9개 공공 소스를 병렬로 조회합니다. 오른쪽 숫자는 각 소스에 부여된 신뢰도
        가중치로, 채점에 그대로 쓰이는 값입니다.
      </p>
      <SourceTable sources={SOURCES} className="mt-7" />
    </Section>
  );
}

/**
 * 근거 — 채널마다 한 화면씩, 셋.
 *
 * 이전에는 파란 타일 넷과 9행짜리 표를 한 화면에 욱여넣었다. 정보는 다
 * 있었지만 어느 소스가 어느 채널에 속하는지는 어디에도 없었고, 눈에 걸리는
 * 것도 없었다.
 *
 * 그래서 채널마다 한 화면을 주고 [사진 + 그 채널이 조회하는 소스]를 좌우
 * 교대로 놓는다. 소스가 채널에 소속되는 구조가 처음으로 눈에 보이고,
 * 스크롤이 길어지는 만큼 읽는 리듬이 생긴다.
 *
 * 화면이 하나에서 셋으로 늘었으므로 배경색 흐름도 9칸 기준으로 바뀐다
 * (globals.css 의 `fides-page-tone-9`). 스냅 대상이 셋이라 긴 섹션이
 * mandatory 스냅에 갇히는 문제도 없다.
 *
 * 사진은 아직 없다. `public/evidence/` 에 파일을 넣으면 붙고, 없으면
 * ImageSlot 이 비율과 찍을 대상을 적은 판으로 자리를 지킨다.
 */
const EVIDENCE_CHANNELS = [
  {
    id: "evidence",
    eyebrow: "Technical · w 0.40",
    title: "기술 근거",
    body: "특허 출원 이력과 공시된 R&D 방향을 대조합니다. 알고리즘과 모델 수준의 주장은 이 채널에서만 입증됩니다.",
    image: {
      src: "/evidence/technical.jpg",
      subject: "특허 도면 · 설계도 · 기술 문서를 펼쳐 놓은 책상",
    },
    sources: SOURCES.filter((s) =>
      ["KIPRIS 특허", "DART 전자공시"].includes(s.name),
    ),
  },
  {
    id: "evidence-2",
    eyebrow: "Horizontal · w 0.35",
    title: "공인 인증",
    body: "제품 모델 단위로 실체를 확인합니다. 기업이 무엇을 하는지가 아니라 그 제품이 실재하는지를 묻는 자리입니다.",
    image: {
      src: "/evidence/certified.jpg",
      subject: "제품 뒷면 인증 라벨 클로즈업 · 인증 스티커",
    },
    sources: SOURCES.filter((s) =>
      ["KC · 전파인증 DB", "RRA 전파인증", "GS 인증", "NEP 인증"].includes(
        s.name,
      ),
    ),
  },
  {
    id: "evidence-3",
    eyebrow: "Contextual · w 0.25",
    title: "기관 이력",
    body: "기업 차원의 AI 활동 이력을 보조로 확인합니다. 이것만으로는 제품의 주장을 입증하지 못하므로 가중치가 가장 낮습니다.",
    image: {
      src: "/evidence/institution.jpg",
      subject: "공공기관 건물 파사드 · 문서 아카이브 서가",
    },
    sources: SOURCES.filter((s) =>
      ["TIPA 공급기업", "조달청 등록 정보", "KORAIA 협회 정보"].includes(s.name),
    ),
  },
];

export function EvidenceSection() {
  return (
    /* 섹션 하나가 세 화면이다. 시작점만 스냅 지점이고 안쪽에는 없으므로
       세 채널은 자유롭게 스크롤되며, 끝에 닿으면 다음 섹션의 스냅이 다시
       받는다. `full` 이 아니라 `tallSnap` 인 이유가 이것이다. */
    <Section id="evidence" tone="ink" tallSnap flow bare>
      {EVIDENCE_CHANNELS.map((channel, i) => {
        /* 짝수 번째는 사진을 오른쪽으로 넘긴다 */
        const flip = i % 2 === 1;
        return (
          /* 한 채널이 정확히 한 화면. 배경색 흐름이 화면 수를 기준으로
             계산되므로(fides-page-tone-9) 높이가 어긋나면 색이 밀린다. */
          /* 첫 행에는 id 를 주지 않는다 — 섹션이 이미 `evidence` 다.
             같은 id 가 둘이면 SectionNav 의 스크롤 이동이 어디로 갈지
             보장되지 않는다. */
          <div
            key={channel.id}
            id={i === 0 ? undefined : channel.id}
            className="flex min-h-[66dvh] items-center"
          >
            <RevealGroup className="mx-auto w-full max-w-[1200px] px-5 py-8 md:px-10">
              {i === 0 ? (
                <div className="mb-7">
                  <Eyebrow className="text-white/45">Evidence</Eyebrow>
                  <h2 className={`mt-3.5 ${H2}`}>무엇을 근거로 삼는지 밝힙니다</h2>
                </div>
              ) : null}

              <div className="grid grid-cols-1 items-center gap-x-10 gap-y-6 md:grid-cols-2">
                {/* 사진 폭을 묶는다. 한 칸을 다 채우면 4:3 이 400px 가까이
                    되어 채널 하나가 한 화면을 통째로 먹는다. */}
                <ImageSlot
                  src={channel.image.src}
                  ratio="4 / 3"
                  subject={channel.image.subject}
                  className={cn("w-full max-w-[400px]", flip && "md:order-2 md:ml-auto")}
                />

                <div className={flip ? "md:order-1" : undefined}>
                  <p className="font-mono text-xs tracking-[var(--tracking-label)] text-white/40">
                    {channel.eyebrow}
                  </p>
                  <h3 className="mt-2.5 text-[21px] font-medium tracking-[var(--tracking-heading)]">
                    {channel.title}
                  </h3>
                  <p className="mt-3 max-w-[440px] text-xs leading-loose text-white/65">
                    {channel.body}
                  </p>
                  <SourceTable sources={channel.sources} dense className="mt-5" />
                </div>
              </div>
            </RevealGroup>
          </div>
        );
      })}
    </Section>
  );
}

export function DifferenceSection() {
  return (
    <Section id="difference" tone="surface" full reveal flow>
      <Eyebrow>What Makes It Different</Eyebrow>
      <h2 className={`text-fg mt-4 ${H2}`}>
        기존 도구는 안을 봅니다.
        <br />
        Fides는 밖을 봅니다.
      </h2>
      <ContrastList items={CONTRASTS} className="mt-8" />
    </Section>
  );
}

export function ProductSection() {
  return (
    <Section id="product" tone="canvas" full reveal flow>
      <div className="flex flex-col gap-9 md:flex-row md:items-center">
        <StaggeredCards className="flex-1" offset={30}>
          <IconTile
            tone="blue"
            title="대조 뷰"
            description={"주장 문장과 근거를\n선으로 연결해 보여줍니다"}
            href="#ledger"
          />
          <IconTile
            tone="coral"
            title="위험 리포트"
            description={"근거가 끊긴 주장만\n추려 PDF로 내보냅니다"}
          />
          <IconTile
            tone="green"
            title="제품 비교"
            description={"최대 3개 제품의\n채널별 점수를 나란히"}
            href="/compare"
          />
          <IconTile
            tone="violet"
            title="워치리스트"
            description={"관심 제품을 등록하고\n재검증 이력을 추적"}
            href="/dashboard"
          />
        </StaggeredCards>

        <div className="md:w-[30%] md:shrink-0 md:text-right">
          <h2 className="text-fg text-2xl leading-tight font-medium tracking-[var(--tracking-heading)] md:text-[26px]">
            Product
            <br />
            &amp; Report
          </h2>
          <p className="text-fg-dim mt-4 text-xs leading-loose">
            검증 결과를 실무에서
            <br />
            바로 쓸 수 있는 형태로
            <br />
            제공합니다.
          </p>
        </div>
      </div>
    </Section>
  );
}

export function CasesSection() {
  return (
    <Section id="cases" tone="surface" full reveal flow>
      <h2 className="text-fg text-2xl font-medium tracking-[var(--tracking-heading)] md:text-[26px]">
        분석 사례
      </h2>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <CaseCard
          category="가전 · 세탁기"
          headline={"“AI 절약 모드”\n근거는 0건"}
          summary="OO전자 AI 절약 세탁기 21kg, 특허 이력 부재로 High Risk 판정"
          tags={["가전", "특허부재", "HighRisk"]}
          tone="blue"
        />
        <CaseCard
          category="생활가전 · 로봇청소기"
          headline={"사물 인식 AI,\n인증으로 확인"}
          summary="OO로보틱스 올인원, KC 인증과 특허 모두 대조 성공"
          tags={["로봇청소기", "근거확인", "Safe"]}
          tone="green"
        />
        <CaseCard
          category="TV · 디스플레이"
          headline={"AI 화질 엔진,\n부분 입증"}
          summary="OO전자 QNED 75형, 기업 이력만 확인되고 제품 단위 근거 없음"
          tags={["TV", "부분일치", "Medium"]}
          tone="violet"
        />
      </div>
    </Section>
  );
}

/**
 * 마지막 칸.
 *
 * 로그인 전에는 검색창을 놓지 않는다. 눌러 봐야 로그인으로 튕기므로,
 * URL 을 붙여넣게 해 놓고 되돌려보내는 셈이 된다.
 *
 * 버튼은 배너가 가진 것을 쓴다. `Button` 프리미티브를 넣으면 안 된다 —
 * 배너 안은 INVERT_TOKENS 가 걸려 `--color-fg` 가 흰색이라, `secondary`
 * 변형이 밝은 바탕에 흰 글씨가 되어 읽히지 않는다.
 */
export function StartSection({ signedIn }: { signedIn?: boolean }) {
  return (
    <Section id="start" tone="canvas" bare full snapAlign="end" flow>
      <RevealGroup className="section-motion mx-auto flex w-full max-w-[1200px] flex-col justify-center gap-10 px-5 py-14 md:px-10">
        {signedIn ? (
          <CtaBanner
            headline="근거 없는 “AI 탑재”를 지금 걸러내세요"
            action={<HeroSearch className="flex flex-col items-center" />}
          />
        ) : (
          <CtaBanner
            headline="근거 없는 “AI 탑재”를 지금 걸러내세요"
            actionLabel="상품 URL로 검증해보기"
            href="/"
          />
        )}
        <LandingFooter />
      </RevealGroup>
    </Section>
  );
}
