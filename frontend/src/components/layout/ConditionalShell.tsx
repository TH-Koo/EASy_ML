"use client";

import { usePathname } from "next/navigation";

import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

export function ConditionalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  /* 랜딩·시안·디자인 갤러리·검토용 변형은 자체 헤더와 푸터를 갖는다.
     인증 화면도 셸 밖에 둔다 — 로그인하러 온 사람에게 다른 데로 새어 나갈
     길을 열어 둘 이유가 없고, 셸의 로고와 페이지 자신의 로고가 나란히 두
     번 보이는 문제도 여기서 없어진다. */
  /* `/` 는 로그인 여부에 따라 셸이 필요할 때와 아닐 때가 갈린다. 여기서는
     경로만 보이므로 언제나 셸 밖에 두고, 검색 화면(SearchHome)이 자기
     껍데기를 직접 그린다.

     `/history/{id}` 와 `/analysis/{id}` 도 마찬가지다 — 둘 다 MaybeAppShell
     안에서 그려지고, 로그인 여부에 따라 사이드바 또는 공용 헤더를 스스로
     고른다. 여기서 SiteHeader 를 또 붙이면 내비가 두 벌이 된다. */
  const isBare =
    pathname === "/" ||
    pathname === "/search" ||
    pathname === "/about" ||
    pathname === "/login" ||
    pathname === "/demo" ||
    pathname === "/design" ||
    pathname.startsWith("/analysis/") ||
    pathname.startsWith("/history/") ||
    pathname.startsWith("/preview/");

  if (isBare) return <>{children}</>;

  return (
    <>
      <SiteHeader />
      <main className="flex flex-1 flex-col">{children}</main>
      <SiteFooter />
    </>
  );
}
