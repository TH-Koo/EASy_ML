"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";
import type { AuthUser } from "@/types/auth";

/**
 * 로그인한 사람의 상단 바.
 *
 * 왼쪽 사이드바(기록·폴더)를 걷어내고 이 한 줄로 바꿨다. 처음 쓰는 사람과
 * 시연에서 QR 로 들어온 사람에게 필요한 건 "주소 넣기 → 결과 보기" 하나라서,
 * 지난 기록을 늘 옆에 세워 둘 이유가 없었다. 지난 기록과 북마크는 '내 기록'
 * (대시보드)에 모여 있다.
 */
export function TopBar({ user }: { user: AuthUser }) {
  const router = useRouter();
  const { logout } = useAuth();

  return (
    <header className="theme-violet border-border bg-surface sticky top-0 z-20 border-b">
      <div className="mx-auto flex h-16 w-full max-w-[1080px] items-center justify-between px-5">
        <Link href="/" className="text-fg text-[22px] font-extrabold tracking-[-0.05em]">
          fides
          <i aria-hidden className="ml-0.5 inline-block size-[7px] -translate-y-3 rounded-full bg-[var(--claim-no)]" />
        </Link>
        <nav className="text-fg-muted flex items-center gap-5 text-sm font-semibold">
          <Link href="/" className="hover:text-fg hidden sm:inline">
            확인하기
          </Link>
          <Link href="/dashboard" className="hover:text-fg">
            내 기록
          </Link>
          <span
            className="bg-brand-soft text-brand-fg grid size-8 place-items-center rounded-full text-xs font-extrabold"
            title={user.nickname}
            aria-label={`${user.nickname} 계정`}
          >
            {user.nickname.slice(0, 1)}
          </span>
          <button
            type="button"
            onClick={() => {
              logout();
              router.push("/");
            }}
            className="text-fg-dim hover:text-fg text-xs"
          >
            로그아웃
          </button>
        </nav>
      </div>
    </header>
  );
}
