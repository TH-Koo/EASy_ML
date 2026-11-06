
"use client";

import { SearchHome } from "@/components/home/SearchHome";
import { useAuth } from "@/lib/auth";

/**
 * 첫 화면 — 로그인 여부와 상관없이 검색창이다.
 * CI/CD 자동 배포 테스트용 문구 추가
 */
export default function HomePage() {
  const { user, mounted } = useAuth();

  return (
    <>
      {/* CI/CD 자동 배포 테스트 */}
      <div
        style={{
          padding: "12px",
          backgroundColor: "#dbeafe",
          color: "#1e40af",
          textAlign: "center",
          fontWeight: "bold",
        }}
      >
        CI/CD 자동 배포 테스트 성공! (2026-11-06)
      </div>

      {/* 기존 홈 화면 */}
      <SearchHome user={mounted ? user : null} />
    </>
  );
}
