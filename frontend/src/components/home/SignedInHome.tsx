"use client";

import { useState } from "react";

import { TopBar } from "@/components/app/TopBar";
import { VerifyForm, type GuideCell } from "@/components/home/VerifyForm";
import { cn } from "@/lib/cn";
import type { AuthUser } from "@/types/auth";

/**
 * 로그인한 사람의 첫 화면 — 위 한 줄 메뉴 + 가운데 검색창 + 주소 안내.
 *
 * 사이드바(기록·폴더)를 걷어냈다. 처음 쓰는 사람과 시연에서 QR 로 들어온
 * 사람에게 필요한 건 "주소 넣기 → 결과 보기" 하나다. 지난 기록은 위 메뉴의
 * '내 기록'(대시보드)에서 본다.
 *
 * 색은 보라 하나로 둔다. 로즈는 분석 화면에서 '미확인'을 뜻하므로 여기서는
 * 안 되는 주소를 알릴 때만 쓴다.
 */
export function SignedInHome({ user }: { user: AuthUser }) {
  // 에러가 난 주소와 관련된 안내 칸을 잠깐 반짝인다. key 를 바꿔 애니메이션을 다시 튼다.
  const [flash, setFlash] = useState<{ cell: GuideCell; n: number } | null>(null);

  return (
    <div className="theme-violet bg-surface flex min-h-dvh flex-col">
      <TopBar user={user} />
      <main className="flex flex-1 flex-col">
        <section className="px-5 pt-[72px] pb-6 text-center">
          <h1 className="text-fg text-[clamp(30px,4.4vw,44px)] leading-[1.3] font-bold tracking-[-0.03em]">
            이 광고 속 AI,
            <br />
            <span className="text-brand-fg">근거가 있을까요?</span>
          </h1>
          <p className="text-fg-muted mx-auto mt-3.5 max-w-[560px] text-base leading-relaxed">
            다나와 상품 주소를 넣으면 광고에 쓰인 AI 기능을 공공 기록과 맞춰 봐요.
          </p>
          <VerifyForm onGuide={(cell) => setFlash((f) => ({ cell, n: (f?.n ?? 0) + 1 }))} />
        </section>

        <section aria-labelledby="guide-h" className="mx-auto w-full max-w-[1040px] px-5 pt-8 pb-20">
          <h2 id="guide-h" className="text-fg mb-[18px] text-[22px] font-bold tracking-[-0.03em]">
            이런 주소를 넣어 주세요
          </h2>
          <dl className="bg-surface-strong grid rounded-[20px] py-1.5 md:grid-cols-4">
            {GUIDE.map((g, i) => (
              <div
                key={`${g.label}-${flash?.cell === i ? flash.n : 0}`}
                className={cn(
                  "px-6 py-[18px]",
                  i > 0 && "border-border border-t md:border-t-0 md:border-l",
                  flash?.cell === i && "guide-flash",
                )}
              >
                <dt className="text-brand-fg text-[12.5px] font-semibold">{g.label}</dt>
                <dd className="text-fg mt-1.5 text-[15px] leading-normal font-semibold">
                  {g.mark ? <span className="text-brand-fg mr-1.5 font-extrabold">{g.mark}</span> : null}
                  {g.value}
                  <small className="text-fg-muted mt-0.5 block text-[13px] font-normal">{g.note}</small>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </main>
    </div>
  );
}

const GUIDE = [
  { label: "넣을 수 있는 주소", mark: "✓", value: "다나와 상품 상세", note: "제품 하나만 보이는 상세 페이지" },
  { label: "아직 안 되는 주소", mark: "✕", value: "쿠팡 · 해외 직구 · 목록", note: "다른 쇼핑몰, 검색 결과" },
  { label: "맞춰 보는 곳", mark: null, value: "공공 기록 9곳", note: "특허 · 인증 · 공시 기록" },
  { label: "결과", mark: null, value: "충분 · 일부 확인 · 미확인", note: "성능이 아니라 광고 근거를 봐요" },
] as const;
