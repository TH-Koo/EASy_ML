import { AboutView } from "@/components/about/AboutView";

/**
 * 서비스 소개 — "무엇을 근거로 어떻게 판단하는가".
 *
 * `/` 는 검색창이므로 설명은 여기서 본다. 위 메뉴의 '서비스 소개'가 이리로
 * 온다. 검색·결과 화면과 같은 보라 테마로 그리고, 마지막은 검색창으로
 * 돌아가는 `바로 해보러 가기` 버튼으로 닫는다.
 */

export const metadata = {
  title: "Fides — 무엇을 근거로 판단하는가",
  description:
    "AI 워싱을 가려내는 방법. 상품이 내세운 AI 주장을 기능 단위로 뽑아 특허·인증·공시 등 공공 기록 9곳과 대조합니다.",
};

export default function AboutPage() {
  return <AboutView />;
}
