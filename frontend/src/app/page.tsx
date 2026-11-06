"use client";

import { SearchHome } from "@/components/home/SearchHome";
import { useAuth } from "@/lib/auth";

/**
 * 첫 화면 — 로그인 여부와 상관없이 검색창이다.
 *
 * 들어오자마자 주소를 넣어 볼 수 있게 했다. 서비스 설명(서사)은 위 메뉴의
 * '서비스 소개'(/about)로 옮겼다. 계정이 필요한 건 내 기록과 북마크뿐이라
 * 그 버튼을 누를 때 로그인으로 보낸다.
 *
 * 토큰이 localStorage 에 있어 서버는 세션을 모른다. 그래서 첫 렌더는 언제나
 * 비로그인 모양이고, 마운트 후 토큰이 있으면 위 메뉴만 계정 표시로 바뀐다.
 */
export default function HomePage() {
  const { user, mounted } = useAuth();
  return <SearchHome user={mounted ? user : null} />;
}
