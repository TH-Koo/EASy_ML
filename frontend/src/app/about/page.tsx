import { MaybeAppShell } from "@/components/app/MaybeAppShell";
import { LandingStory } from "@/components/landing/LandingStory";

/**
 * 소개 — 서사를 언제든 다시 보는 자리.
 *
 * `/` 는 검색창이므로, "무엇을 근거로 어떻게 판단하는가"는 여기서 본다.
 * 위 메뉴의 '서비스 소개'가 이리로 온다.
 *
 * 마지막 칸에 검색창을 둔다 — 읽다가 바로 분석을 시작할 수 있는 편이 낫다.
 */

export const metadata = {
  title: "Fides — 무엇을 근거로 판단하는가",
  description:
    "AI 워싱을 가려내는 방법. 상품이 내세운 AI 주장을 문장 단위로 뜯어내고 특허·인증·공시 등 9개 공공 기록과 대조합니다.",
};

export default function AboutPage() {
  return (
    <MaybeAppShell>
      <LandingStory signedIn />
    </MaybeAppShell>
  );
}
