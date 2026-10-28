"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Download, Search, Share2, Bookmark, BookmarkCheck } from "lucide-react";

import { Button } from "@/components/primitives/Button";
import { apiAddWatchlist } from "@/lib/api/auth";
import { useAuth } from "@/lib/auth";
import type { AnalysisResult } from "@/types/analysis";

interface QuickActionsProps {
  data: AnalysisResult;
  historyId?: number;
}

export function QuickActions({ data, historyId }: QuickActionsProps) {
  const { user } = useAuth();
  const [toast,      setToast]      = useState("");
  const [bookmarked, setBookmarked] = useState(false);
  const [bmBusy,     setBmBusy]     = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showToast(msg: string) {
    setToast(msg);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setToast(""), 2200);
  }

  function handleShare() {
    const url = historyId
      ? `${window.location.origin}/history/${historyId}`
      : window.location.href;
    navigator.clipboard.writeText(url)
      .then(() => showToast("링크가 클립보드에 복사됐습니다"))
      .catch(() => showToast("복사 실패 — 주소창에서 직접 복사해 주세요"));
  }

  function handlePdf() {
    window.print();
  }

  async function handleBookmark() {
    if (!user || bookmarked || bmBusy) return;
    setBmBusy(true);
    try {
      const url = historyId
        ? `${window.location.origin}/history/${historyId}`
        : window.location.href;
      await apiAddWatchlist(user.token, url, data.product.name || "");
      setBookmarked(true);
      showToast("북마크에 저장됐습니다");
    } catch {
      showToast("북마크 저장에 실패했습니다");
    } finally {
      setBmBusy(false);
    }
  }

  return (
    <>
      {/* 결과 화면 맨 아래 한 줄. 결과 화면이 한 단이 되면서 사이드바의
          세로 카드에서 가로 줄로 옮겼다. */}
      <div className="no-print flex flex-wrap gap-2">
          {/* 다른 제품 검색 — 홈의 검색창으로. 결과 화면은 보라 테마라 cta 의
              네이비 그라데이션 대신 브랜드 색 한 가지로 채운다. */}
          <Button
            asChild
            variant="cta"
            size="lg"
            className="flex-[2_1_12rem]"
            style={{ background: "var(--color-brand)" }}
          >
            <Link href="/">
              <Search size={16} aria-hidden />
              다른 제품 검색하기
            </Link>
          </Button>

          {/* 링크 공유 */}
          <Button
            type="button"
            variant="secondary"
            size="lg"
            className="flex-[1_1_9rem]"
            onClick={handleShare}
          >
            <Share2 size={14} aria-hidden />
            링크 공유
          </Button>

          {/* 인쇄 — `window.print()` 는 인쇄 대화상자를 열 뿐 파일을 만들지
              않는다. 거기서 "PDF로 저장"을 고르는 것은 사용자다. 버튼이
              파일을 주는 것처럼 적어 두면 약속을 어기게 된다. */}
          <Button
            type="button"
            variant="secondary"
            size="lg"
            className="flex-[1_1_9rem]"
            onClick={handlePdf}
          >
            <Download size={14} aria-hidden />
            인쇄 · PDF로 저장
          </Button>

          {/* 북마크 */}
          <Button
            type="button"
            variant="secondary"
            size="lg"
            className="flex-[1_1_9rem]"
            onClick={handleBookmark}
            disabled={bookmarked || bmBusy || !user}
            style={
              bookmarked
                ? {
                    borderColor: "var(--color-partial)",
                    color: "var(--color-partial)",
                    background: "var(--color-partial-soft)",
                  }
                : undefined
            }
          >
            {bookmarked
              ? <><BookmarkCheck size={14} aria-hidden /> 북마크 저장됨</>
              : <><Bookmark size={14} aria-hidden /> {bmBusy ? "저장 중…" : "북마크에 저장"}</>
            }
          </Button>
      </div>

      {/* 토스트 — 규칙은 globals.css 의 `.qa-toast` 에 있다. 이전에는 인라인
          스타일에 자체 색과 `'Inter'` 를 박고, 토스트가 뜰 때마다 `<style>`
          태그로 keyframe 을 새로 주입했다. */}
      {toast ? (
        <div role="status" aria-live="polite" className="qa-toast no-print">
          {toast}
        </div>
      ) : null}
    </>
  );
}
