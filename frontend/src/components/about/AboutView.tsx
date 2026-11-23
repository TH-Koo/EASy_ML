"use client";

import { ArrowRight, Check, Minus, X } from "lucide-react";
import Link from "next/link";

import { TopBar } from "@/components/app/TopBar";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";

/**
 * 서비스 소개 — 검색·결과 화면과 같은 흰 바탕 + 보라/로즈.
 *
 * 첫 화면은 대표 문구 하나를 가운데 크게 둔다. 무엇을 하는 서비스인지는
 * 바로 아래 세 줄 요약(9곳 · 기능별 · 0원)과 3단계 그림이 이어서 말한다.
 * 각 섹션은 문단보다 작은 UI 그림과 칩으로 말한다.
 *
 * 색의 뜻은 결과 화면과 같다: 보라 = 확인, 연보라 = 일부, 로즈 = 미확인.
 *
 * 근거 기관은 server.py 의 `PIPELINE_SOURCES`(실제로 조회하는 9곳)와 맞춘다.
 * 소개에만 있고 조회하지 않는 기관을 적으면 결과 화면과 말이 어긋난다.
 * 내부 가중치는 결과 화면처럼 보여 주지 않는다.
 */
export function AboutView() {
  const { user, mounted } = useAuth();

  return (
    <div className="theme-violet bg-surface flex min-h-dvh flex-col">
      <TopBar user={mounted ? user : null} />
      <main className="flex-1">
        <Hero />
        <Facts />
        <Steps />
        <Why />
        <Evidence />
        <Difference />
        <Start />
      </main>
      <footer className="border-border text-fg-dim mx-auto w-full max-w-[1080px] border-t px-5 py-6 text-xs">
        © 2026 Fides Project
      </footer>
    </div>
  );
}

/* ══ 공통 ═══════════════════════════════════════════════════════════════ */

type Verdict = "ok" | "part" | "no";

const VERDICT: Record<Verdict, { label: string; chip: string; Icon: typeof Check }> = {
  ok: { label: "확인", chip: "bg-[var(--claim-ok-soft)] text-[var(--claim-ok)]", Icon: Check },
  part: { label: "일부", chip: "bg-brand-soft text-[var(--claim-part)]", Icon: Minus },
  no: { label: "미확인", chip: "bg-[var(--claim-no-soft)] text-[var(--claim-no)]", Icon: X },
};

function VerdictChip({ v, className }: { v: Verdict; className?: string }) {
  const { label, chip, Icon } = VERDICT[v];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[13px] font-bold",
        chip,
        className,
      )}
    >
      <Icon size={13} strokeWidth={3} aria-hidden />
      {label}
    </span>
  );
}

/** 바로 해보러 가기 — 첫 화면(검색창)으로. 로그인은 필요 없다. */
function TryButton({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "bg-brand inline-flex items-center gap-2 rounded-xl px-6 py-3.5 text-[15px] font-bold text-white shadow-[0_8px_24px_rgba(103,65,217,0.28)] transition hover:brightness-110",
        className,
      )}
    >
      바로 해보러 가기
      <ArrowRight size={18} aria-hidden />
    </Link>
  );
}

function Heading({ eyebrow, children, id }: { eyebrow: string; children: React.ReactNode; id: string }) {
  return (
    <>
      <p className="text-brand-fg text-[13px] font-bold">{eyebrow}</p>
      <h2
        id={id}
        className="text-fg mt-2 text-[clamp(26px,3.4vw,36px)] leading-[1.3] font-bold tracking-[-0.035em]"
      >
        {children}
      </h2>
    </>
  );
}

/* ══ 1. 첫 화면 ═══════════════════════════════════════════════ */

function Hero() {
  return (
    <section className="relative overflow-hidden px-5 pt-12 pb-16 md:pt-20 md:pb-24">
      {/* 은은한 보라 빛 — 장식 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 h-[520px] w-[920px] -translate-x-1/2 rounded-full opacity-70 blur-3xl"
        style={{
          background:
            "radial-gradient(closest-side, rgba(139,108,240,0.22), rgba(224,69,123,0.08) 60%, transparent)",
        }}
      />
      <div className="relative mx-auto w-full max-w-[860px] py-6 text-center md:py-16">
        <p className="bg-brand-soft text-brand-fg inline-block rounded-full px-3 py-1 text-[13px] font-bold">
          AI 워싱 판별 서비스
        </p>
        <h1 className="text-fg mt-6 text-[clamp(36px,6vw,64px)] leading-[1.2] font-extrabold tracking-[-0.04em]">
          주장이 아니라 <span className="text-brand-fg">근거로</span>
          <br />
          판단하는 AI 검증,
          <br />
          오직 Fides에서
        </h1>
        <p className="text-fg-muted mx-auto mt-6 max-w-[520px] text-[17px] leading-relaxed md:text-lg">
          상품 주소 하나면 광고가 내세운 AI 기능을 뽑아
          <b className="text-fg font-semibold"> 특허·인증·공시 기록</b>과 하나씩 맞춰 봅니다.
        </p>
        <div className="mt-9 flex flex-col items-center gap-3">
          <TryButton />
          <span className="text-fg-dim text-[13px]">로그인 없이 바로 쓸 수 있습니다</span>
        </div>
      </div>
    </section>
  );
}

/* ══ 2. 세 줄 요약 ═════════════════════════════════════════════════════ */

const FACTS = [
  { big: "9곳", label: "공공 기록만 조회", note: "특허 · 인증 · 공시 · 국가 R&D" },
  { big: "기능별", label: "하나하나 따로 판정", note: "확인 · 일부 · 미확인" },
  { big: "0원", label: "로그인 없이 바로", note: "다나와 상품 주소만 있으면 됩니다" },
];

function Facts() {
  return (
    <section aria-label="핵심 요약" className="px-5">
      <dl className="bg-surface-strong mx-auto grid w-full max-w-[1080px] rounded-[24px] sm:grid-cols-3">
        {FACTS.map((f, i) => (
          <div
            key={f.label}
            className={cn("px-6 py-6 md:px-8", i > 0 && "border-border border-t sm:border-t-0 sm:border-l")}
          >
            <dt className="text-fg text-[15px] font-bold">
              <span className="text-brand-fg mr-2 text-[26px] font-extrabold tracking-[-0.03em]">{f.big}</span>
              {f.label}
            </dt>
            <dd className="text-fg-dim mt-1 text-[13.5px]">{f.note}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/* ══ 3. 확인 방법 ════════════════════════════════════════════════ */

function Steps() {
  return (
    <section id="how" aria-labelledby="how-h" className="scroll-mt-16 px-5 py-20 md:py-28">
      <div className="mx-auto w-full max-w-[1080px]">
        <div className="text-center">
          <Heading id="how-h" eyebrow="확인 방법">
            주소를 넣으면, 세 단계로 끝납니다
          </Heading>
        </div>

        <ol className="mt-12 grid gap-4 md:grid-cols-3 md:gap-5">
          <StepCard n={1} title="상품 주소 넣기" body="다나와 상품 상세 페이지 주소를 붙여 넣습니다.">
            <div className="bg-surface border-border flex w-full items-center gap-2 rounded-xl border p-1.5 pl-3">
              <span className="text-fg-dim min-w-0 flex-1 truncate text-[13px]">danawa.com/product/…</span>
              <span className="bg-brand grid size-8 place-items-center rounded-lg text-white">
                <ArrowRight size={16} aria-hidden />
              </span>
            </div>
          </StepCard>

          <StepCard n={2} title="AI 주장 뽑기" body="광고 문구와 상세 이미지에서 AI 기능만 골라냅니다.">
            <div className="flex flex-wrap gap-1.5">
              {["AI 절약 모드", "AI 자동 코스", "인버터 DD 모터"].map((c) => (
                <span
                  key={c}
                  className="bg-surface border-border text-fg rounded-lg border px-2.5 py-1.5 text-[13px] font-semibold"
                >
                  {c}
                </span>
              ))}
            </div>
          </StepCard>

          <StepCard n={3} title="기록과 맞춰 판정" body="기능마다 맞는 공공 기록이 있는지 보고 결과를 냅니다.">
            <div className="flex flex-wrap gap-1.5">
              <VerdictChip v="ok" />
              <VerdictChip v="part" />
              <VerdictChip v="no" />
            </div>
          </StepCard>
        </ol>
      </div>
    </section>
  );
}

function StepCard({
  n,
  title,
  body,
  children,
}: {
  n: number;
  title: string;
  body: string;
  children: React.ReactNode;
}) {
  return (
    <li className="bg-surface-strong flex flex-col rounded-[24px] p-6">
      <div className="flex min-h-[76px] items-center">{children}</div>
      <p className="text-brand-fg mt-5 text-[13px] font-bold">STEP {n}</p>
      <b className="text-fg mt-1 text-xl font-bold tracking-[-0.03em]">{title}</b>
      <p className="text-fg-muted mt-1.5 text-[15px] leading-relaxed">{body}</p>
    </li>
  );
}

/* ══ 4. 왜 필요한가 ════════════════════════════════════════════════════ */

/** 실제 상품 페이지에서 흔히 보이는 표현. 특정 브랜드는 지목하지 않는다. */
const AD_QUOTES = [
  { product: "세탁기", text: "인공지능 DD" },
  { product: "TV 리모컨", text: "AI 매직 리모컨" },
  { product: "냉장고", text: "인공지능 냉기케어 시스템" },
];

function Why() {
  return (
    <section id="why" aria-labelledby="why-h" className="bg-surface-strong scroll-mt-16 px-5 py-20 md:py-28">
      <div className="mx-auto grid w-full max-w-[1080px] items-center gap-10 md:grid-cols-2 md:gap-16">
        <div>
          <Heading id="why-h" eyebrow="왜 필요한가">
            ‘AI’라는 말은
            <br />
            누구나 쓸 수 있기 때문입니다
          </Heading>
          <p className="text-fg-muted mt-4 text-[16px] leading-relaxed">
            실제 AI 기술이 없거나 미미한데도 AI를 앞세워 파는 것을{" "}
            <b className="text-fg font-semibold">AI 워싱</b>이라고 합니다. 소비자는 그 말을 믿고 더 비싼
            값을 치릅니다.
          </p>
          <div className="mt-8 grid grid-cols-2 gap-3">
            <Stat value="58%" label="글로벌 기업" caption="AI 역량을 부풀려 알린 적 있다" />
            <Stat value="61%" label="국내 기업" caption="AI 신뢰성 검토 조직이 없다" />
          </div>
        </div>

        <ul className="flex flex-col gap-3">
          {AD_QUOTES.map((q, i) => (
            <li
              key={q.text}
              className={cn(
                "bg-surface flex items-center gap-4 rounded-2xl px-5 py-4 shadow-[0_6px_20px_-12px_rgba(16,19,23,0.18)]",
                i === 1 && "md:ml-8",
                i === 2 && "md:ml-16",
              )}
            >
              <div className="min-w-0 flex-1">
                <span className="text-fg-dim text-[12.5px] font-semibold">{q.product} 광고</span>
                <b className="text-fg block truncate text-[17px] font-bold tracking-[-0.02em]">“{q.text}”</b>
              </div>
              <span className="shrink-0 text-[13px] font-bold text-[var(--claim-no)]">근거는?</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Stat({ value, label, caption }: { value: string; label: string; caption: string }) {
  return (
    <div className="bg-surface rounded-2xl p-5">
      <span className="block text-[34px] leading-none font-extrabold tracking-[-0.04em] text-[var(--claim-no)]">
        {value}
      </span>
      <span className="text-fg mt-2 block text-[14px] font-bold">{label}</span>
      <span className="text-fg-dim mt-0.5 block text-[13px] leading-snug">{caption}</span>
    </div>
  );
}

/* ══ 5. 근거로 삼는 곳 ═════════════════════════════════════════════════ */

/**
 * server.py `PIPELINE_SOURCES` 의 9곳을 세 갈래로 묶었다. 이름은 결과 화면
 * (lib/resultSummary.ts 의 SOURCE_INFO)과 같은 기관을 가리킨다.
 */
const EVIDENCE_GROUPS = [
  {
    title: "기술 근거",
    question: "그 기술을 실제로 가졌나?",
    sources: ["특허 KIPRIS", "국가 R&D NTIS", "IITP 연구과제"],
    caveat: "제품에 적용됐는지는 따로 확인합니다",
  },
  {
    title: "제품 인증",
    question: "그 제품이 공인 인증을 거쳤나?",
    sources: ["전파인증 RRA", "TTA·GS 인증"],
    caveat: "AI 성능을 시험했다는 뜻은 아닙니다",
  },
  {
    title: "기업 · 공공 이력",
    question: "회사가 AI 사업을 하고 있나?",
    sources: ["공시 DART", "NIPA AI 공급기업", "조달청", "나라장터"],
    caveat: "회사 차원 기록이라 보조로만 씁니다",
  },
];

function Evidence() {
  return (
    <section id="evidence" aria-labelledby="evidence-h" className="scroll-mt-16 px-5 py-20 md:py-28">
      <div className="mx-auto w-full max-w-[1080px]">
        <div className="text-center">
          <Heading id="evidence-h" eyebrow="근거로 삼는 곳">
            회사가 고칠 수 없는
            <br className="sm:hidden" /> 기록만 봅니다
          </Heading>
          <p className="text-fg-muted mx-auto mt-4 max-w-[520px] text-[16px] leading-relaxed">
            기관이 심사하고 남긴 공공 기록 9곳을 조회합니다.
          </p>
          <p className="mt-4 flex flex-wrap items-center justify-center gap-2 text-[13px] font-semibold">
            {["리뷰", "블로그", "광고 문구"].map((x) => (
              <span key={x} className="bg-surface-strong text-fg-dim rounded-full px-3 py-1 line-through">
                {x}
              </span>
            ))}
            <span className="text-fg-dim">는 근거로 세지 않습니다</span>
          </p>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-3 md:gap-5">
          {EVIDENCE_GROUPS.map((g) => (
            <section key={g.title} className="border-border flex flex-col rounded-[24px] border p-6">
              <h3 className="text-fg text-xl font-bold tracking-[-0.03em]">{g.title}</h3>
              <p className="text-fg-muted mt-1 text-[15px]">{g.question}</p>
              <ul className="mt-5 flex flex-1 flex-wrap content-start gap-2">
                {g.sources.map((s) => (
                  <li key={s} className="bg-brand-soft text-brand-fg rounded-lg px-3 py-1.5 text-[14px] font-bold">
                    {s}
                  </li>
                ))}
              </ul>
              <p className="text-fg-dim border-border mt-5 border-t pt-4 text-[13.5px]">{g.caveat}</p>
            </section>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ══ 6. 무엇이 다른가 ══════════════════════════════════════════════════ */

const CONTRASTS = [
  { axis: "보는 대상", before: "회사 안의 AI 운영·리스크", after: "밖으로 내세운 AI 주장" },
  { axis: "확인 방법", before: "정책 준수·내부 점검", after: "공공 기록과 하나씩 대조" },
  { axis: "결과를 읽는 사람", before: "기업 내부 담당자", after: "물건을 사려는 소비자" },
];

function Difference() {
  return (
    <section
      id="difference"
      aria-labelledby="difference-h"
      className="bg-surface-strong scroll-mt-16 px-5 py-20 md:py-28"
    >
      <div className="mx-auto w-full max-w-[860px]">
        <div className="text-center">
          <Heading id="difference-h" eyebrow="무엇이 다른가">
            기존 도구는 안을 봅니다.
            <br />
            <span className="text-brand-fg">Fides는 밖을 봅니다.</span>
          </Heading>
        </div>

        <div className="bg-surface mt-12 overflow-hidden rounded-[24px]">
          <div className="text-fg-dim grid grid-cols-2 gap-x-4 px-5 pt-5 pb-3 text-[13px] font-bold sm:grid-cols-[140px_1fr_1fr] sm:px-7">
            <span className="hidden sm:block" />
            <span>기존 도구</span>
            <span className="text-brand-fg">Fides</span>
          </div>
          {CONTRASTS.map((c) => (
            <div
              key={c.axis}
              className="border-border grid grid-cols-2 gap-x-4 gap-y-1 border-t px-5 py-4 sm:grid-cols-[140px_1fr_1fr] sm:items-center sm:px-7"
            >
              <span className="text-fg-dim col-span-2 text-[13px] font-semibold sm:col-span-1">{c.axis}</span>
              <span className="text-fg-muted text-[15px]">{c.before}</span>
              <span className="text-fg text-[15px] font-bold">{c.after}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ══ 7. 시작 ════════════════════════════════════════════════════════════ */

function Start() {
  return (
    <section className="px-5 py-20 md:py-28">
      <div
        className="mx-auto w-full max-w-[1080px] rounded-[28px] px-6 py-14 text-center md:py-20"
        style={{
          background:
            "radial-gradient(120% 140% at 50% 0%, rgba(139,108,240,0.16), rgba(224,69,123,0.06) 55%, rgba(103,65,217,0.04))",
        }}
      >
        <h2 className="text-fg text-[clamp(26px,3.6vw,40px)] leading-[1.3] font-extrabold tracking-[-0.04em]">
          궁금한 그 제품,
          <br />
          <span className="text-brand-fg">AI가 진짜인지 확인해 보세요</span>
        </h2>
        <p className="text-fg-muted mx-auto mt-4 max-w-[420px] text-[16px] leading-relaxed break-keep text-balance">
          결과는 기능마다 <span className="whitespace-nowrap">확인 · 일부 · 미확인</span>으로 보여 드려요.
        </p>
        <TryButton className="mt-8" />
      </div>
    </section>
  );
}
