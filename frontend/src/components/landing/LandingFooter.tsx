import Link from "next/link";

import { FidesMark } from "@/components/brand/FidesMark";

/**
 * 랜딩 푸터 — 4열 사이트맵.
 *
 * 마지막 스냅 섹션이 CTA 배너와 이 푸터를 함께 담는다. 푸터만 따로
 * 한 화면을 차지하면 스크롤 한 번이 통째로 낭비된다.
 */

const COLUMNS = [
  {
    heading: "서비스",
    links: [
      { label: "대조 뷰", href: "#ledger" },
      { label: "위험 리포트", href: "#product" },
      { label: "제품 비교", href: "/compare" },
      { label: "워치리스트", href: "/dashboard" },
    ],
  },
  {
    heading: "데이터",
    links: [
      { label: "KIPRIS", href: "#product" },
      { label: "DART", href: "#product" },
      { label: "KC · RRA", href: "#product" },
      { label: "TIPA · KORAIA", href: "#product" },
    ],
  },
  {
    heading: "문서",
    links: [
      { label: "채점 방식", href: "#ledger" },
      { label: "가중치 모델", href: "#channels" },
      { label: "API 문서", href: "#start" },
      { label: "변경 이력", href: "#start" },
    ],
  },
  {
    heading: "회사",
    links: [
      { label: "소개", href: "#channels" },
      { label: "문의", href: "/login" },
      { label: "이용약관", href: "/login" },
      { label: "개인정보처리방침", href: "/login" },
    ],
  },
] as const;

export function LandingFooter() {
  return (
    <footer className="border-border border-t pt-8">
      <div className="grid grid-cols-2 gap-x-6 gap-y-7 sm:grid-cols-4">
        {COLUMNS.map((column) => (
          <div key={column.heading}>
            <p className="text-fg text-xs font-medium">{column.heading}</p>
            <ul className="mt-3 flex flex-col gap-2">
              {column.links.map((link) => (
                <li key={link.label}>
                  <Link
                    href={link.href}
                    className="text-fg-dim hover:text-fg text-xs transition-colors"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-border mt-8 flex flex-col items-start gap-3 border-t pt-5 pb-16 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:pb-2">
        <span className="text-fg flex items-center gap-2 text-[15px] font-medium tracking-[var(--tracking-tight)]">
          Fides
          <FidesMark size={24} />
        </span>
        <span className="text-fg-faint text-xs">
          © 2026 Fides Project. All rights reserved.
        </span>
      </div>
    </footer>
  );
}
