"use client";

import { TopBar } from "@/components/app/TopBar";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { useAuth } from "@/lib/auth";

/**
 * 로그인했으면 위 한 줄 메뉴(TopBar) 아래에서, 아니면 그대로.
 *
 * 예전에는 기록 사이드바(AppShell)를 붙였다. 첫 화면과 같은 한 줄 메뉴로
 * 바꿨다 — 지난 기록은 '내 기록'(대시보드)에서 본다.
 *
 * 사이드바는 그 사람의 기록을 보여주는 물건이라 세션이 없으면 채울 게
 * 없다. 그런데 셸을 붙일지 말지는 경로만으로 정할 수 없다 — `/about` 도
 * `/analysis/{id}` 도 로그인 여부와 무관하게 열린다(분석은 비로그인도
 * 된다). 그래서 여기서 세션을 직접 보고 가른다.
 *
 * 마운트 전에는 셸 없이 그린다. 서버는 세션을 모르므로 어느 쪽으로든
 * 단정하면 하이드레이션이 어긋난다. 사이드바가 한 박자 늦게 붙는 편이
 * 화면이 한 번 깨졌다 맞춰지는 것보다 낫다.
 */
export function MaybeAppShell({
  children,
  signedOutChrome = "none",
}: {
  children: React.ReactNode;
  /**
   * 로그인하지 않았을 때 무엇으로 감쌀지.
   *
   * `site` — 공용 헤더·푸터. 셸이 없으면 돌아갈 길도 없는 화면에 쓴다
   *          (분석 진행 화면이 그렇다)
   * `none` — 아무것도. 자체 내비를 가진 화면에 쓴다 (소개 서사)
   */
  signedOutChrome?: "site" | "none";
}) {
  const { user, mounted } = useAuth();

  if (mounted && user) {
    return (
      <>
        <TopBar user={user} />
        <main className="flex flex-1 flex-col">{children}</main>
      </>
    );
  }

  if (signedOutChrome === "site") {
    return (
      <>
        <SiteHeader />
        <main className="flex flex-1 flex-col">{children}</main>
        <SiteFooter />
      </>
    );
  }

  return <>{children}</>;
}
