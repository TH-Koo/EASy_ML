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
  async redirects() {
    return [
      /**
       * `/history` 는 /dashboard 의 `분석 기록` 탭과 같은 목록이었다.
       * 대시보드 쪽에만 검색 · 정렬 · 비교 · 행 펼치기가 있어 두 화면을
       * 나란히 두면 한쪽이 반드시 뒤처진다. 목록은 대시보드 하나로 모은다.
       *
       * 지우지 않고 넘기는 이유: 이미 나간 링크와 북마크가 있고,
       * `/history/{id}` 상세는 그대로 살아 있어 경로 자체를 없앨 수 없다.
       *
       * 서버에서 넘기므로 빈 화면이 깜빡이지 않는다.
       */
      {
        source: "/history",
        destination: "/dashboard",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
