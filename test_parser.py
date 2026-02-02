#!/usr/bin/env python3
"""
Test Confluence Parser with sample HTML
"""
import sys
import re
from pathlib import Path
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
import json


def parse_application(html_content: str, page_id: str = "test", page_url: str = "http://test") -> Dict[str, Any]:
    """
    Parse application data from HTML content
    (Standalone version for testing without app dependencies)
    """
    soup = BeautifulSoup(html_content, 'lxml')
    data = {
        "confluence_page_id": page_id,
        "confluence_page_url": page_url,
        "parse_error_log": ""
    }
    errors = []

    try:
        # ============================================================
        # I. 기본사항 파싱
        # ============================================================

        # 과제명 (class="subject") - 셀 안에 직접 내용이 있음
        subject_elem = soup.find(class_="subject")
        if subject_elem:
            text = subject_elem.get_text(strip=True)
            if text and text != "여기 파싱":
                data["subject"] = text

        # 소속/사업부 (class="division") - 셀 안에 직접 내용이 있음
        division_elem = soup.find(class_="division")
        if division_elem:
            text = division_elem.get_text(strip=True)
            if text and text != "여기 파싱":
                data["division"] = text

        # 참여인원 (class="dept") - 셀 안에 직접 내용이 있음
        dept_elem = soup.find(class_="dept")
        if dept_elem:
            dept_text = dept_elem.get_text(strip=True)
            if dept_text and dept_text != "여기 파싱":
                # 숫자만 추출
                numbers = re.findall(r'\d+', dept_text)
                if numbers:
                    data["participant_count"] = int(numbers[0])

        # 과제 대표자 - "과제 대표자" 헤더를 찾고 같은 행의 다음 셀에서 내용 추출
        rep_header_elem = soup.find('strong', string=re.compile(r'과제\s*대표자'))
        if rep_header_elem:
            header_cell = rep_header_elem.find_parent('td')
            if header_cell:
                # 같은 행의 다음 셀들 확인
                next_cells = header_cell.find_next_siblings('td')
                for cell in next_cells:
                    text = cell.get_text(strip=True)
                    if text and text != "여기 파싱" and len(text) > 0:
                        # "이름 (Knox ID)" 또는 "이름 Knox ID" 형식 파싱
                        match = re.match(r'(.+?)\s*[\(（](.+?)[\)）]', text)
                        if match:
                            data["representative_name"] = match.group(1).strip()
                            data["representative_knox_id"] = match.group(2).strip()
                        else:
                            parts = text.split()
                            if len(parts) >= 2:
                                data["representative_name"] = parts[0]
                                data["representative_knox_id"] = parts[1]
                            elif len(parts) == 1:
                                data["representative_name"] = parts[0]
                        break

        # ============================================================
        # II. 사전 설문 파싱
        # ============================================================
        pre_survey = {}
        for i in range(1, 7):
            q_elem = soup.find(class_=f"q{i}")
            if q_elem:
                row = q_elem.find_parent('tr')
                if row:
                    cells = row.find_all('td')
                    q_index = -1
                    for idx, cell in enumerate(cells):
                        if f"q{i}" in cell.get('class', []):
                            q_index = idx
                            break

                    if q_index >= 0:
                        q_text = cells[q_index].get_text(strip=True)
                        next_text = cells[q_index + 1].get_text(strip=True) if q_index + 1 < len(cells) else ""

                        if q_text and q_text not in ['', 'O', 'X']:
                            pre_survey[f"q{i}"] = "예"
                        elif next_text and next_text not in ['', 'O', 'X']:
                            pre_survey[f"q{i}"] = "아니오"
                        elif 'O' in q_text or '○' in q_text or '✓' in q_text:
                            pre_survey[f"q{i}"] = "예"
                        elif 'O' in next_text or '○' in next_text or '✓' in next_text:
                            pre_survey[f"q{i}"] = "아니오"

        if pre_survey:
            data["pre_survey"] = pre_survey

        # ============================================================
        # III. 신청 내용 파싱
        # ============================================================
        def find_section_content(section_number: str, section_keyword: str) -> Optional[str]:
            """섹션 번호와 키워드로 내용을 찾는 함수"""
            for td in soup.find_all('td', class_='highlight-#b3d4ff'):
                td_text = td.get_text(strip=True)
                if section_number in td_text and section_keyword in td_text:
                    header_row = td.find_parent('tr')
                    if header_row:
                        next_row = header_row.find_next_sibling('tr')
                        if next_row:
                            content_row = next_row.find_next_sibling('tr')
                            if content_row:
                                content_cell = content_row.find('td')
                                if content_cell:
                                    text = content_cell.get_text(strip=True)
                                    if text and text != "여기 파싱":
                                        return text
            return None

        # 현재 업무
        current_work = find_section_content("1.", "현재 업무")
        if current_work:
            data["current_work"] = current_work

        # Pain Point
        pain_point = find_section_content("2.", "Pain point")
        if pain_point:
            data["pain_point"] = pain_point

        # 개선 아이디어
        improvement_idea = find_section_content("3.", "개선 아이디어")
        if improvement_idea:
            data["improvement_idea"] = improvement_idea

        # 기대 효과
        expected_effect = find_section_content("4.", "기대 효과")
        if expected_effect:
            data["expected_effect"] = expected_effect

        # 바라는 점
        hope = find_section_content("5.", "바라는 점")
        if hope:
            data["hope"] = hope

        # ============================================================
        # IV. 과제 참여자 기술 역량 파싱
        # ============================================================
        tech_capabilities = []

        tech_header = soup.find('strong', string=re.compile(r'IV\.\s*과제\s*참여자\s*기술\s*역량'))
        if tech_header:
            main_table = tech_header.find_parent('table')
            if main_table:
                nested_table = main_table.find('table', class_='wrapped')
                if nested_table:
                    current_category = None

                    rows = nested_table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')

                        if len(cells) > 0:
                            first_cell_text = cells[0].get_text(strip=True)
                            if '분야' in first_cell_text or '레벨' in first_cell_text:
                                continue

                        # 대분류 행
                        if len(cells) == 1 and cells[0].get('colspan') == '9':
                            category_text = cells[0].get_text(strip=True)
                            if category_text and category_text not in ['(작성 예시)', '']:
                                current_category = category_text
                            continue

                        # 상세 행
                        if len(cells) >= 2:
                            cell_idx = 0
                            field = None
                            skill = None
                            level_text = None

                            if cell_idx < len(cells):
                                field_cell = cells[cell_idx]
                                field = field_cell.get_text(strip=True)
                                cell_idx += 1

                            if cell_idx < len(cells):
                                skill_cell = cells[cell_idx]
                                skill = skill_cell.get_text(strip=True)
                                cell_idx += 1

                            if cell_idx < len(cells):
                                level_cell = cells[cell_idx]
                                level_text = level_cell.get_text(strip=True)

                            if field and skill and level_text:
                                if '작성 예시' in field or '작성 예시' in skill:
                                    continue
                                if field == '여기 파싱' or skill == '여기 파싱':
                                    continue

                                field_elem = cells[0].find('em')
                                skill_elem = cells[1].find('em') if len(cells) > 1 else None
                                if field_elem or skill_elem:
                                    continue

                                level_numbers = re.findall(r'\d+', level_text)
                                level = int(level_numbers[0]) if level_numbers else 0

                                if level > 0:
                                    tech_capabilities.append({
                                        "category": current_category or field,
                                        "field": field,
                                        "skill": skill,
                                        "level": level
                                    })

        if tech_capabilities:
            data["tech_capabilities"] = tech_capabilities

    except Exception as e:
        error_msg = f"Parsing error: {str(e)}"
        errors.append(error_msg)
        print(f"❌ {error_msg}")
        import traceback
        errors.append(traceback.format_exc())

    if errors:
        data["parse_error_log"] = "\n".join(errors)

    return data


def test_parse_html():
    """Test parsing with conf.html"""

    # Read sample HTML
    html_file = Path("conf.html")
    if not html_file.exists():
        print("❌ conf.html not found")
        return

    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Parse
    print("🔍 Parsing HTML...")
    result = parse_application(html_content, "test_page_id", "http://test.url")

    # Display results
    print("\n" + "=" * 60)
    print("📊 Parsing Results")
    print("=" * 60)

    print(f"\n✅ Subject: {result.get('subject', 'N/A')}")
    print(f"✅ Division: {result.get('division', 'N/A')}")
    print(f"✅ Participant Count: {result.get('participant_count', 'N/A')}")
    print(f"✅ Representative: {result.get('representative_name', 'N/A')} ({result.get('representative_knox_id', 'N/A')})")

    print(f"\n📋 Pre-Survey:")
    for key, value in result.get('pre_survey', {}).items():
        print(f"  {key}: {value}")

    print(f"\n📝 Application Content:")
    print(f"  Current Work: {result.get('current_work', 'N/A')[:100]}...")
    print(f"  Pain Point: {result.get('pain_point', 'N/A')[:100]}...")
    print(f"  Improvement Idea: {result.get('improvement_idea', 'N/A')[:100]}...")
    print(f"  Expected Effect: {result.get('expected_effect', 'N/A')[:100]}...")
    print(f"  Hope: {result.get('hope', 'N/A')[:100]}...")

    print(f"\n🛠️  Tech Capabilities ({len(result.get('tech_capabilities', []))} items):")
    for i, tech in enumerate(result.get('tech_capabilities', [])[:10], 1):
        print(f"  {i}. [{tech.get('category', 'N/A')}] {tech.get('field', 'N/A')} - {tech.get('skill', 'N/A')}: Level {tech.get('level', 0)}")

    if result.get('parse_error_log'):
        print(f"\n⚠️  Parse Errors:")
        print(result['parse_error_log'])

    print("\n" + "=" * 60)
    print("💾 Full JSON Output:")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    test_parse_html()
