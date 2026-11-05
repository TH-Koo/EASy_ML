"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";

/**
 * 첫 화면의 시작 버튼.
 *
 * 갈 곳이 로그인 여부에 따라 갈리는데, 그걸 부모가 prop 으로 정해 주면
 * 틀린다 — `/about` 은 `signedIn` 을 항상 참으로 넘기지만 로그아웃 상태로도
 * 열 수 있는 화면이라, 그 사람은 `/` 로 갔다가 같은 소개로 되돌아왔다.
 * 그래서 실제 세션을 여기서 직접 본다.
 *
 * 마운트 전에는 로그아웃으로 본다. 서버는 세션을 모르므로 어느 쪽으로든
 * 단정하면 하이드레이션이 어긋나고, 틀렸을 때 로그인 화면을 한 번 거치는
 * 편이 로그인 페이지에서 튕겨 나오는 것보다 덜 이상하다.
 */
export function HeroCta({ className }: { className?: string }) {
  const { user, mounted } = useAuth();
  const href = mounted && user ? "/" : "/search";

  return (
    <Link
      href={href}
      className={cn(
        "text-brand-fg inline-block rounded-[var(--radius-pill)] bg-white px-6 py-2.5 text-xs font-medium transition-opacity hover:opacity-90",
        className,
      )}
    >
      시작하기
    </Link>
  );
}
