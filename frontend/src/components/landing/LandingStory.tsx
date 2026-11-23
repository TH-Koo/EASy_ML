import { SectionNav } from "@/components/landing/SectionNav";
import { SnapScroll } from "@/components/landing/SnapScroll";
import {
  ApproachSection,
  DifferenceSection,
  EvidenceSection,
  HeroSection,
  LedgerSection,
  ProblemSection,
  StartSection,
} from "@/components/landing/sections";
import { FloatingActions } from "@/components/layout/FloatingActions";
import { PageBackdrop } from "@/components/motion/PageBackdrop";

/**
 * 서사 7단, 화면 8칸.
 *
 * `/about`(서비스 소개)에서 쓴다. `/` 는 검색창이다. 마지막 칸은
 * `바로 해보러 가기` 버튼으로 닫아 그 검색창으로 돌려보낸다.
 *
 * 서사 순서로 읽힌다:
 *   실물을 들이대고(문제) → 해법을 꺼내고(3단계)
 *   → 어떻게 보이는지 증명하고(대조 뷰) → 근거를 밝히고
 *   → 기존과 무엇이 다른지 대조하고 → 전환으로 닫는다.
 *
 * `근거` 만 두 화면을 쓴다. 배경색 매핑은 globals.css 의
 * `fides-page-tone-landing` 에 있고 화면 수와 물려 있다.
 */

const SECTIONS = [
  { id: "hero", label: "소개", dark: true },
  { id: "problem", label: "AI 워싱", dark: true },
  { id: "approach", label: "해결 방식" },
  { id: "ledger", label: "대조 뷰" },
  { id: "evidence", label: "근거", dark: true },
  { id: "difference", label: "차별성" },
  { id: "start", label: "시작하기" },
];

export function LandingStory() {
  return (
    <>
      <PageBackdrop />
      <SnapScroll tone="landing" />
      <SectionNav items={SECTIONS} />
      <FloatingActions />

      <HeroSection />
      <ProblemSection />
      <ApproachSection />
      <LedgerSection />
      <EvidenceSection />
      <DifferenceSection />
      <StartSection />
    </>
  );
}
