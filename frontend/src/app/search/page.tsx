"use client";

import { SearchHome } from "@/components/home/SearchHome";
import { useAuth } from "@/lib/auth";

/**
 * 검색 화면 — 로그인 없이 바로 쓴다.
 *
 * `/` 는 로그인 전에는 소개(랜딩)를 보여 주므로, 소개의 `시작하기` 는 이리로 온다.
 */
export default function SearchPage() {
  const { user, mounted } = useAuth();
  return <SearchHome user={mounted ? user : null} />;
}
