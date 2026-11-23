import type { VerificationRow } from "@/types/analysis";

/**
 * 검증 표의 각 행이 "어떤 기록을 뒤졌는가" 를 한 줄로 설명한다.
 *
 * **안정 id(`source`)로 찾는다.** 이전에는 표시 문자열(`key`)을 열쇠로 썼는데,
 * 백엔드는 `조달청 MAS` 를 보내고 사전에는 `조달청 AI 우수제품` 이 들어 있는
 * 식으로 양쪽이 따로 흘러가 일곱 행이 **전부** 어긋났다. 그래서 결과
 * 화면에는 오랫동안 설명이 한 줄도 뜨지 않았고, 사용자는 "조달청 MAS —
 * 스킵" 만 보고 있었다.
 *
 * id 는 server.py 의 `SOURCE_LABELS` 와 같은 것을 쓴다. 새 채널이 늘면
 * 여기에 한 줄 추가하면 되고, 없으면 설명 없이 조용히 넘어간다.
 */
const BY_SOURCE: Record<string, string> = {
  kipris:
    "KIPRIS(키프리스)는 특허를 검색하는 서비스예요. 관련 기술의 출원·등록 이력을 확인하며, 해당 제품의 실제 적용 여부는 별도 확인이 필요해요.",
  dart: "DART는 금융감독원의 전자공시시스템이에요. 기업이 제출한 사업보고서의 사업·연구개발 설명을 확인하는 보조 자료예요.",
  kc: "전기용품안전관리법상 KC 인증에 이 모델이 등록돼 있는지 확인합니다.",
  rra: "RRA는 국립전파연구원이에요. 제품의 전파·전자파 관련 적합성평가 기록을 확인하며, AI 기능이나 성능을 인증하는 자료는 아니에요.",
  tipa: "정보통신산업진흥원(TIPA)의 AI 공급기업 명단에 있는지 확인합니다.",
  koraia: "한국인공지능산업협회(KORAIA) 회원사 등록 여부입니다.",
  gs: "GS(Good Software) 인증과 산업부 신제품(NEP) 인증 보유 건수입니다.",
  nep: "산업통상자원부 신제품(NEP) 인증 보유 여부입니다.",
  procurement:
    "조달청 나라장터 종합쇼핑몰(MAS)에 등록된 제품인지 확인합니다. 제3자 검증을 한 번 거쳤다는 뜻입니다.",
  tta: "TTA 등 시험기관의 GS·신제품 인증 기록이 이 제조사 이름으로 있는지 봅니다.",
  ntis: "NTIS는 국가 연구개발 정보를 검색하는 서비스예요. 관련 과제 참여와 성과를 확인하며, 이 제품에 적용됐는지는 별도 확인이 필요해요.",
  iitp: "정보통신기획평가원(IITP)이 관리하는 ICT 연구과제에 이 제조사가 참여했는지 봅니다.",
  nipa: "정보통신산업진흥원(NIPA)의 AI 솔루션 공급기업 명단에 있는지 확인합니다.",
  koneps: "나라장터에서 최근 1년간 관련 낙찰 실적이 있는지 확인합니다.",
  kaiac: "한국인공지능인증센터(KAIAC)의 AI 품질 인증 보유 여부입니다.",
};

/**
 * 이 변경 이전에 저장된 기록에는 `source` 가 없다. 그때 쓰던 표시
 * 문자열만이라도 받아 준다 — 옛 결과를 다시 열어도 설명이 뜨도록.
 */
const BY_LEGACY_KEY: Record<string, string> = {
  "RRA 전파인증 (로컬DB)": BY_SOURCE.rra,
  "조달청 MAS": BY_SOURCE.procurement,
  "TIPA AI기업": BY_SOURCE.tipa,
  KORAIA: BY_SOURCE.koraia,
  "DART 공시": BY_SOURCE.dart,
  "특허 보유": BY_SOURCE.kipris,
  "GS/NEP 인증": BY_SOURCE.gs,
};

export function descriptionFor(row: VerificationRow): string | null {
  if (row.source && BY_SOURCE[row.source]) return BY_SOURCE[row.source];
  return BY_LEGACY_KEY[row.key] ?? null;
}
