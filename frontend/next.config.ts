import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins:["3.39.41.117"],
	/* 개발 모드 전용 Next 인디케이터가 기본값(bottom-left)에서 우리
     SectionNav(섹션 이동 점 · 화살표, 같은 자리에 fixed)와 겹친다.
     bottom-right 는 FloatingActions(문의 버튼)가 이미 쓰므로 남는
     top-right 로 옮긴다. 프로덕션 빌드에는 이 인디케이터 자체가 없다. */
  devIndicators: {
    position: "top-right",
  },
};

export default nextConfig;
