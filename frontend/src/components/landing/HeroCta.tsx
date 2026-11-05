import Link from "next/link";

import { cn } from "@/lib/cn";

/** 소개 화면의 시작 버튼 — 첫 화면(검색창)으로 간다. 로그인은 필요 없다. */
export function HeroCta({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "text-brand-fg inline-block rounded-[var(--radius-pill)] bg-white px-6 py-2.5 text-xs font-medium transition-opacity hover:opacity-90",
        className,
      )}
    >
      시작하기
    </Link>
  );
}
