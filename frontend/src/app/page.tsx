"use client";

import { SearchHome } from "@/components/home/SearchHome";
import { LandingStory } from "@/components/landing/LandingStory";
import { useAuth } from "@/lib/auth";

/**
 * 첫 화면 — 로그인 여부로 갈린다.
 *
 *   로그인 전 → 서사 (LandingStory). `시작하기` 는 검색 화면(/search)으로 간다
 *   로그인 후 → 검색 화면 (SearchHome)
 *
 * 소개는 /about 에 그대로 있어 로그인한 뒤에도 헤더에서 갈 수 있다.
 *
 * 왜 서버에서 못 가르는가: 토큰이 localStorage 에 있어 서버가 볼 수 없다.
 * 그래서 첫 렌더는 언제나 로그인 전 화면이고, 마운트 후 토큰이 있으면
 * 도구 화면으로 바뀐다. 로그인한 사람은 아주 짧게 서사를 스칠 수 있다.
 *
 * 제대로 없애려면 토큰을 쿠키로 옮겨 미들웨어에서 갈라야 한다. 인증
 * 저장 방식을 바꾸는 일이라 따로 잡는 편이 맞다.
 */
export default function HomePage() {
  const { user, mounted } = useAuth();

  if (mounted && user) return <SearchHome user={user} />;
  return <LandingStory signedIn={false} />;
}
