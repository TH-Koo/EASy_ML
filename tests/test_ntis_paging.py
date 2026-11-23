import os
import tempfile
import unittest
from unittest import mock

import logic.api as api


def _hit(number, title, agency, abstract=""):
    return (f"<HIT><ProjectNumber>{number}</ProjectNumber>"
            f"<ProjectTitle><Korean>{title}</Korean></ProjectTitle>"
            f"<Abstract><Full>{abstract}</Full></Abstract>"
            f"<ResearchAgency><Name>{agency}</Name></ResearchAgency></HIT>")


class _Resp:
    status_code = 200

    def __init__(self, text):
        self.text = text


def _fake_ntis(pages_by_query, total_by_query):
    """검색어·시작 위치별로 정해 둔 HIT 를 돌려주는 가짜 NTIS."""
    calls = []

    def get(url, params=None, timeout=None):
        query, pos = params["SRWR"], params["startPosition"]
        calls.append((query, pos))
        hits = pages_by_query.get(query, {}).get(pos, [])
        total = total_by_query.get(query, 0)
        return _Resp(f"<RESULT><TOTALHITS>{total}</TOTALHITS><RESULTSET>{''.join(hits)}</RESULTSET></RESULT>")

    return get, calls


class NtisPagingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.dict(os.environ, {"EASY_NTIS_CACHE_DIR": self.tmp.name}),
            mock.patch.object(api, "NTIS_API_KEY", "key"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_ai_project_beyond_first_page_is_found(self):
        # 예전에는 상위 50건만 봐서, 뒤 페이지의 삼성 AI 과제를 놓쳤다.
        filler = [_hit(f"N{i}", f"인공지능 반도체 공정 {i}", "삼성전기(주)") for i in range(100)]
        later = [_hit("AI1", "세탁물 인식 인공지능 기술 개발", "삼성전자(주)")]
        get, calls = _fake_ntis({"삼성전자 인공지능": {1: filler, 101: later}}, {"삼성전자 인공지능": 101})
        with mock.patch.object(api.requests, "get", side_effect=get):
            res = api.verify_ntis_rnd(["삼성전자"])
        self.assertEqual(res["status"], "verified")
        self.assertEqual([r["project_number"] for r in res["records"]], ["AI1"])
        self.assertIn(("삼성전자 인공지능", 101), calls)

    def test_company_name_only_query_reads_first_page_only(self):
        # 회사 이름만으로 한 검색은 수천 건이라 끝까지 읽지 않는다.
        get, calls = _fake_ntis({}, {"삼성전자": 7094})
        with mock.patch.object(api.requests, "get", side_effect=get):
            api.verify_ntis_rnd(["삼성전자"])
        self.assertEqual([pos for q, pos in calls if q == "삼성전자"], [1])

    def test_yearly_duplicates_merge_and_escaped_markup_is_removed(self):
        # 같은 과제가 연차마다 번호만 달리 나오고, 기관명에 검색 강조 태그가 글자로 들어온다.
        agency = "&lt;span class=&quot;search_word&quot;&gt;엘지전자&lt;/span&gt;(주)"
        hits = [_hit(f"Y{i}", "실외 경비 로봇 인공지능 개발", agency) for i in range(4)]
        get, _ = _fake_ntis({"엘지전자 인공지능": {1: hits}}, {"엘지전자 인공지능": 4})
        with mock.patch.object(api.requests, "get", side_effect=get):
            res = api.verify_ntis_rnd(["엘지전자"])
        self.assertEqual(len(res["records"]), 1)
        self.assertEqual(res["records"][0]["research_agency"], "엘지전자(주)")

    def test_affiliate_is_not_counted_as_company(self):
        hits = [_hit("D1", "디스플레이 인공지능 검사", "엘지디스플레이(주)"),
                _hit("E1", "가전 인공지능 음성인식", "<span class=\"search_word\">엘지전자</span>(주)")]
        get, _ = _fake_ntis({"엘지전자": {1: hits}}, {"엘지전자": 2})
        with mock.patch.object(api.requests, "get", side_effect=get):
            res = api.verify_ntis_rnd(["엘지전자"])
        self.assertEqual([r["project_number"] for r in res["records"]], ["E1"])
        self.assertEqual(res["records"][0]["research_agency"], "엘지전자(주)")

    def test_ai_keyword_queries_are_merged_and_cached(self):
        hit = _hit("AI2", "딥러닝 기반 냉장고 식품 인식", "삼성전자(주)")
        get, calls = _fake_ntis({"삼성전자 딥러닝": {1: [hit]}, "삼성전자 인공지능": {1: [hit]}},
                                {"삼성전자 딥러닝": 1, "삼성전자 인공지능": 1})
        with mock.patch.object(api.requests, "get", side_effect=get):
            first = api.verify_ntis_rnd(["삼성전자"])
            n_calls = len(calls)
            second = api.verify_ntis_rnd(["삼성전자"])
        self.assertEqual(len(first["records"]), 1)  # 같은 과제는 한 번만
        self.assertEqual(second["records"], first["records"])
        self.assertEqual(len(calls), n_calls)  # 두 번째는 캐시

    def test_api_error_is_reported_not_hidden(self):
        def get(url, params=None, timeout=None):
            return _Resp("<?xml version='1.0'?><error>접근 허용 IP가 아닙니다.</error>")
        with mock.patch.object(api.requests, "get", side_effect=get):
            res = api.verify_ntis_rnd(["삼성전자"])
        self.assertEqual(res["status"], "error")
        self.assertIn("접근 허용 IP", res["error"])
        self.assertEqual(os.listdir(self.tmp.name), [])  # 실패는 캐시하지 않는다


if __name__ == "__main__":
    unittest.main()
