import os
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from logic import api


class NtisLiveSchemaTests(unittest.TestCase):
    def parse(self, title='인공지능 기반 사물 인식', agency='삼성전자(주)', extra=''):
        hit = ET.fromstring(
            '<HIT><ProjectNumber>1415112058</ProjectNumber>'
            f'<ProjectTitle><![CDATA[{title}]]></ProjectTitle>'
            f'<ResearchAgency><![CDATA[{agency}]]></ResearchAgency>{extra}</HIT>'
        )
        return api._ntis_project_from_hit(hit, '삼성전자')

    def test_direct_agency_text_with_search_highlighting_is_accepted(self):
        result = self.parse(
            title='<span class="search_word">인공지능</span> 기반 객체 인식 연구',
            agency='<span class="search_word">삼성전자</span>(주)',
        )
        self.assertIsNotNone(result)
        self.assertEqual(result['research_agency'], '삼성전자(주)')
        self.assertTrue(result['company_verified'])
        self.assertNotIn('<span', result['project_name'])

    def test_ai_can_be_present_in_flat_body_fields(self):
        for tag in ['Goal','Abstract','Keyword','Effect']:
            with self.subTest(tag=tag):
                result = self.parse(title='로봇 환경 분석 연구', extra=f'<{tag}>딥러닝 모델 개발</{tag}>')
                self.assertIsNotNone(result)

    def test_company_mentioned_in_title_does_not_validate_another_agency(self):
        self.assertIsNone(self.parse(title='삼성전자 인공지능 설계 시스템', agency='(주)마이다스아이티'))
        self.assertIsNone(self.parse(agency='사회복지법인삼성생명공익재단'))

    def test_company_match_without_ai_evidence_is_not_enough(self):
        self.assertIsNone(self.parse(title='고효율 전열교환기 개발'))

    def test_nested_agency_format_remains_supported(self):
        hit = ET.fromstring(
            '<HIT><ProjectNumber>AI1</ProjectNumber>'
            '<ProjectTitle><Korean>인공지능 로봇 연구</Korean></ProjectTitle>'
            '<ResearchAgency><Name>삼성전자(주)</Name></ResearchAgency></HIT>'
        )
        self.assertIsNotNone(api._ntis_project_from_hit(hit, '삼성전자'))

    def test_empty_cache_from_previous_parser_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.dict(os.environ, {'EASY_NTIS_CACHE_DIR':directory}):
            path = api._ntis_cache_path('삼성전자')
            old_path = path.replace(f'_v{api._NTIS_CACHE_VERSION}.json','_v3.json')
            self.assertNotEqual(path, old_path)
            with open(old_path,'w',encoding='utf-8') as stream:
                stream.write('[]')
            self.assertIsNone(api._ntis_cache_load('삼성전자'))


if __name__ == '__main__':
    unittest.main()
