"""
Confluence Parser Service (Company Version 3 with Full Markdown + Indentation Support)
Supports: Tables, Headings (h1~h6), Bold, Italic, Indentation (spaces/tabs)
"""
import re
import time
import json
import os
import uuid
import requests
import urllib3
from bs4 import BeautifulSoup, NavigableString
from typing import List, Dict, Any, Optional
from pathlib import Path
from sqlalchemy.orm import Session
from app.config import settings
from app.models.application import Application
from app.models.department import Department
from app.services.rate_limiter import RateLimiter

# Disable SSL warnings when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Images directory
IMAGES_DIR = Path("images")


def download_image(image_url: str, auth: tuple) -> Optional[str]:
    """
    Download image from Confluence and save to local images directory

    Args:
        image_url: Full URL to the image
        auth: Confluence authentication tuple (username, password)

    Returns:
        Local file path (relative to project root) or None if failed
    """
    try:
        # Create images directory if not exists
        IMAGES_DIR.mkdir(exist_ok=True)

        # Download image with authentication
        response = requests.get(image_url, auth=auth, timeout=30, verify=False)
        response.raise_for_status()

        # Determine file extension from URL or Content-Type
        ext = '.png'  # default
        if '.' in image_url.split('/')[-1]:
            url_ext = image_url.split('/')[-1].split('.')[-1].split('?')[0]
            if url_ext.lower() in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp']:
                ext = f'.{url_ext.lower()}'
        else:
            # Try to get from Content-Type header
            content_type = response.headers.get('Content-Type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
            elif 'svg' in content_type:
                ext = '.svg'
            elif 'webp' in content_type:
                ext = '.webp'

        # Generate unique filename
        filename = f"{uuid.uuid4()}{ext}"
        filepath = IMAGES_DIR / filename

        # Save image
        with open(filepath, 'wb') as f:
            f.write(response.content)

        # Return relative path for web access
        return f"/images/{filename}"

    except Exception as e:
        print(f"❌ Failed to download image {image_url}: {e}")
        return None


def html_table_to_markdown(html_content, base_url: str = "", auth: Optional[tuple] = None) -> str:
    """
    Convert HTML content (including tables, headings, bold, italic) to markdown format
    Preserves indentation (leading spaces/tabs)

    Args:
        html_content: HTML string or BeautifulSoup element
        base_url: Base URL for resolving relative image URLs
        auth: Confluence authentication tuple for downloading images

    Returns:
        Markdown formatted string with all HTML converted to markdown
    """
    if not html_content:
        return ""

    # Convert to BeautifulSoup if string
    if isinstance(html_content, str):
        soup = BeautifulSoup(html_content, 'lxml')
    else:
        soup = html_content

    # Find all tables and convert them to markdown
    tables = soup.find_all('table')

    for table in tables:
        markdown_table = convert_table_to_markdown(table)
        # Replace original table with markdown text
        table.replace_with(BeautifulSoup(markdown_table, 'lxml'))

    # Now use html_to_text for the rest (images, text, headings, bold, italic, etc.)
    return html_to_text(soup, base_url, auth)


def convert_table_to_markdown(table_element) -> str:
    """
    Convert BeautifulSoup table element to markdown table string

    Args:
        table_element: BeautifulSoup table element

    Returns:
        Markdown table string
    """
    rows = table_element.find_all('tr')
    if not rows:
        return ""

    markdown_lines = []

    for idx, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        # Extract cell text, replace newlines with spaces, escape pipe characters
        cell_texts = []
        for cell in cells:
            text = cell.get_text(strip=True).replace('\n', ' ').replace('|', '\\|')
            cell_texts.append(text)

        # Create markdown table row
        markdown_line = '| ' + ' | '.join(cell_texts) + ' |'
        markdown_lines.append(markdown_line)

        # Add separator after first row
        if idx == 0:
            separator = '| ' + ' | '.join(['---'] * len(cells)) + ' |'
            markdown_lines.append(separator)

    return '\n' + '\n'.join(markdown_lines) + '\n'


def html_to_text(element, base_url: str = "", auth: Optional[tuple] = None) -> str:
    """
    Convert HTML element to markdown formatted text preserving structure and indentation

    Converts:
    - <h1>~<h6> → # ~ ###### markdown headings
    - <strong>, <b> → **text** markdown bold
    - <em>, <i> → *text* markdown italic
    - <br> → newline
    - <p> → newline separation (preserving leading spaces for indentation)
    - <ul><li> → bullet points
    - <ol><li> → numbered list
    - <img> → ![alt](local_path) markdown format (downloads and saves images locally)
    - Preserves line breaks, list formatting, and indentation

    Args:
        element: BeautifulSoup element to convert
        base_url: Base URL for resolving relative URLs
        auth: Confluence authentication tuple for downloading images
    """
    if not element:
        return ""

    result = []

    def process_element(elem, preserve_whitespace=False):
        """Recursively process HTML elements"""
        if elem.name is None:
            # Text node - preserve leading/trailing spaces if needed
            if preserve_whitespace:
                text = str(elem)
            else:
                text = str(elem).strip()
            if text:
                result.append(text)
        elif elem.name == 'br':
            result.append('\n')
        elif elem.name == 'img':
            # Handle images - download and save locally
            src = elem.get('src', '')
            alt = elem.get('alt', 'image')

            # Convert relative URL to absolute URL
            img_url = None
            if src:
                if src.startswith('http://') or src.startswith('https://'):
                    img_url = src
                elif src.startswith('/'):
                    img_url = f"{base_url}{src}"
                else:
                    img_url = f"{base_url}/{src}"

                # Download image and get local path
                if img_url and auth:
                    local_path = download_image(img_url, auth)
                    if local_path:
                        # Use local path in markdown
                        result.append(f'\n![{alt}]({local_path})\n')
                    else:
                        # Failed to download, use original URL with note
                        result.append(f'\n![{alt} (다운로드 실패)]({img_url})\n')
                else:
                    # No auth provided, use original URL
                    result.append(f'\n![{alt}]({img_url})\n')
        elif elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Convert headings to markdown
            level = int(elem.name[1])  # Extract number from h1~h6
            heading_prefix = '#' * level
            heading_text = elem.get_text(strip=True)
            result.append(f'\n{heading_prefix} {heading_text}\n\n')
        elif elem.name in ['strong', 'b']:
            # Convert bold to markdown
            result.append('**')
            for child in elem.children:
                process_element(child, preserve_whitespace=True)
            result.append('**')
        elif elem.name in ['em', 'i']:
            # Convert italic to markdown
            result.append('*')
            for child in elem.children:
                process_element(child, preserve_whitespace=True)
            result.append('*')
        elif elem.name == 'p':
            # Preserve indentation in paragraphs
            # Check if first child is a text node with leading spaces
            first_child = next(iter(elem.children), None)
            if first_child and isinstance(first_child, NavigableString):
                text_str = str(first_child)
                # Count leading spaces/tabs
                leading_whitespace = len(text_str) - len(text_str.lstrip())
                if leading_whitespace > 0:
                    # Preserve leading spaces (use non-breaking space marker)
                    indent = '&nbsp;' * leading_whitespace
                    result.append(indent)

            for child in elem.children:
                process_element(child, preserve_whitespace=False)
            result.append('\n\n')
        elif elem.name == 'ul':
            for li in elem.find_all('li', recursive=False):
                result.append('• ')
                for child in li.children:
                    if child.name != 'ul' and child.name != 'ol':
                        process_element(child)
                result.append('\n')
                # Handle nested lists
                for nested in li.find_all(['ul', 'ol'], recursive=False):
                    result.append('  ')
                    process_element(nested)
        elif elem.name == 'ol':
            counter = 1
            for li in elem.find_all('li', recursive=False):
                result.append(f'{counter}. ')
                counter += 1
                for child in li.children:
                    if child.name != 'ul' and child.name != 'ol':
                        process_element(child)
                result.append('\n')
                # Handle nested lists
                for nested in li.find_all(['ul', 'ol'], recursive=False):
                    result.append('  ')
                    process_element(nested)
        elif elem.name == 'span':
            # For span, just process children without any formatting
            for child in elem.children:
                process_element(child)
        elif elem.name == 'div':
            for child in elem.children:
                process_element(child)
        elif elem.name == 'li':
            # Skip if already handled by ul/ol
            pass
        else:
            # For other tags, just process children
            if hasattr(elem, 'children'):
                for child in elem.children:
                    process_element(child)

    process_element(element)

    # Join and clean up
    text = ''.join(result)
    # Remove excessive newlines (more than 2 consecutive)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Strip leading/trailing whitespace
    text = text.strip()

    return text


class ConfluenceParser:
    """Confluence API client and HTML parser"""

    def __init__(self):
        self.base_url = settings.confluence_base_url.rstrip('/')
        # 링크용 URL (설정되지 않았으면 base_url 사용)
        self.link_base_url = (settings.confluence_link_base_url or settings.confluence_base_url).rstrip('/')
        self.auth = (settings.confluence_username, settings.confluence_password)
        self.space_key = settings.confluence_space_key
        self.parent_page_id = settings.confluence_parent_page_id
        # Rate limiter: 10 calls per minute
        self.rate_limiter = RateLimiter(max_calls=10, time_window=60)

    def get_child_pages(self) -> List[Dict[str, str]]:
        """
        Get child pages under parent page

        Returns:
            List of pages with id, title, url
        """
        url = f"{self.base_url}/rest/api/content/{self.parent_page_id}/child/page"
        params = {"limit": 500, "expand": "version"}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Apply rate limiting
                self.rate_limiter.wait_if_needed()

                response = requests.get(url, auth=self.auth, params=params, timeout=30, verify=False)

                # Handle 429 Too Many Requests
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"⚠️  429 Too Many Requests. Waiting {retry_after} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()

                pages = []
                for page in data.get("results", []):
                    pages.append({
                        "id": page["id"],
                        "title": page["title"],
                        "url": f"{self.link_base_url}/pages/viewpage.action?pageId={page['id']}"
                    })

                return pages
            except requests.exceptions.HTTPError as e:
                if attempt < max_retries - 1 and e.response.status_code == 429:
                    continue
                print(f"❌ HTTP Error fetching child pages: {e}")
                return []
            except Exception as e:
                print(f"❌ Error fetching child pages: {e}")
                return []

        print(f"❌ Failed to fetch child pages after {max_retries} attempts")
        return []

    def get_page_content(self, page_id: str) -> Optional[str]:
        """
        Get XHTML content of a page

        Args:
            page_id: Confluence page ID

        Returns:
            XHTML content string or None
        """
        url = f"{self.base_url}/rest/api/content/{page_id}"
        params = {"expand": "body.view"}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Apply rate limiting
                self.rate_limiter.wait_if_needed()

                response = requests.get(url, auth=self.auth, params=params, timeout=30, verify=False)

                # Handle 429 Too Many Requests
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"⚠️  429 Too Many Requests for page {page_id}. Waiting {retry_after} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()
                return data.get("body", {}).get("view", {}).get("value")
            except requests.exceptions.HTTPError as e:
                if attempt < max_retries - 1 and e.response.status_code == 429:
                    continue
                print(f"❌ HTTP Error fetching page {page_id}: {e}")
                return None
            except Exception as e:
                print(f"❌ Error fetching page {page_id}: {e}")
                return None

        print(f"❌ Failed to fetch page {page_id} after {max_retries} attempts")
        return None

    def parse_application(self, html_content: str, page_id: str, page_url: str) -> Dict[str, Any]:
        """
        Parse application data from HTML content

        Args:
            html_content: XHTML content
            page_id: Confluence page ID
            page_url: Confluence page URL

        Returns:
            Parsed application data dictionary
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
                            # 괄호로 분리 시도
                            match = re.match(r'(.+?)\s*[\(（](.+?)[\)）]', text)
                            if match:
                                data["representative_name"] = match.group(1).strip()
                                data["representative_knox_id"] = match.group(2).strip()
                            else:
                                # 공백으로 분리 시도
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
            # class="q1"~"q6" 셀과 같은 행의 다음 셀에서 체크 여부 확인
            pre_survey = {}
            for i in range(1, 7):
                q_elem = soup.find(class_=f"q{i}")
                if q_elem:
                    # 같은 행의 다음 셀 확인 (예/아니오 중 체크된 것)
                    row = q_elem.find_parent('tr')
                    if row:
                        cells = row.find_all('td')
                        # q{i} 셀의 인덱스 찾기
                        q_index = -1
                        for idx, cell in enumerate(cells):
                            if f"q{i}" in cell.get('class', []):
                                q_index = idx
                                break

                        # q{i} 셀과 그 다음 셀 확인
                        if q_index >= 0:
                            # q{i} 셀 체크 (보통 "예" 열)
                            q_text = cells[q_index].get_text(strip=True)
                            # 다음 셀 체크 (보통 "아니오" 열)
                            next_text = cells[q_index + 1].get_text(strip=True) if q_index + 1 < len(cells) else ""

                            # 체크된 곳이 있으면 저장
                            if q_text and q_text not in ['', 'O', 'X']:
                                pre_survey[f"q{i}"] = "예"
                            elif next_text and next_text not in ['', 'O', 'X']:
                                pre_survey[f"q{i}"] = "아니오"
                            # O, X 또는 빈칸으로 표시된 경우
                            elif 'O' in q_text or '○' in q_text or '✓' in q_text:
                                pre_survey[f"q{i}"] = "예"
                            elif 'O' in next_text or '○' in next_text or '✓' in next_text:
                                pre_survey[f"q{i}"] = "아니오"

            if pre_survey:
                data["pre_survey"] = pre_survey

            # ============================================================
            # III. 신청 내용 파싱 (테이블, 헤딩, 볼드, 이탤릭, 들여쓰기를 마크다운으로 변환)
            # ============================================================
            # 섹션 헤더를 찾아서 내용 추출하는 헬퍼 함수
            def find_section_content(section_number: str, section_keyword: str) -> Optional[str]:
                """
                섹션 번호와 키워드로 내용을 찾는 함수
                헤더가 여러 <strong> 태그로 분리될 수 있으므로 td 전체 텍스트를 확인
                HTML 포맷을 유지하여 줄바꿈과 리스트를 보존
                이미지를 다운로드하여 로컬에 저장
                테이블, 헤딩, 볼드, 이탤릭, 들여쓰기를 마크다운으로 변환
                """
                # 모든 td 셀을 순회하며 섹션 헤더 찾기
                for td in soup.find_all('td', class_='highlight-#b3d4ff'):
                    td_text = td.get_text(strip=True)
                    # 섹션 번호와 키워드 모두 포함되어 있는지 확인
                    if section_number in td_text and section_keyword in td_text:
                        header_row = td.find_parent('tr')
                        if header_row:
                            # 다음 행 (보통 빈 행 또는 class가 있는 행)
                            next_row = header_row.find_next_sibling('tr')
                            if next_row:
                                # 그 다음 행에서 내용 찾기
                                content_row = next_row.find_next_sibling('tr')
                                if content_row:
                                    content_cell = content_row.find('td')
                                    if content_cell:
                                        # HTML을 마크다운으로 변환 (테이블, 헤딩, 볼드, 이탤릭, 들여쓰기 포함, 이미지 다운로드)
                                        text = html_table_to_markdown(content_cell, self.link_base_url, self.auth)
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
            # IV. 과제 참여자 기술 역량 파싱 (중첩 테이블, 동적 구조)
            # ============================================================
            tech_capabilities = []

            # "IV. 과제 참여자 기술 역량" 헤더 찾기
            tech_header = soup.find('strong', string=re.compile(r'IV\.\s*과제\s*참여자\s*기술\s*역량'))
            if tech_header:
                # 헤더 행의 부모 테이블 찾기
                main_table = tech_header.find_parent('table')
                if main_table:
                    # 중첩된 테이블 찾기 (data-mce-resize 속성이 있는 테이블)
                    nested_table = main_table.find('table', class_='wrapped')
                    if nested_table:
                        current_category = None  # 현재 대분류 (예: "코드 구현", "데이터 분석/시각화")

                        rows = nested_table.find_all('tr')
                        for row in rows:
                            cells = row.find_all('td')

                            # 헤더 행 스킵 (분야/기술/레벨)
                            if len(cells) > 0:
                                first_cell_text = cells[0].get_text(strip=True)
                                if '분야' in first_cell_text or '레벨' in first_cell_text:
                                    continue

                            # 대분류 행 (colspan="9")
                            if len(cells) == 1 and cells[0].get('colspan') == '9':
                                category_text = cells[0].get_text(strip=True)
                                if category_text and category_text not in ['(작성 예시)', '']:
                                    current_category = category_text
                                continue

                            # 상세 행 (2열: 분야, 6열: 기술, 1열: 레벨)
                            # colspan 값을 고려하여 파싱
                            if len(cells) >= 2:
                                # colspan을 고려한 실제 셀 매핑
                                cell_idx = 0
                                field = None
                                skill = None
                                level_text = None

                                # 첫 번째 셀 그룹 (분야, colspan=2)
                                if cell_idx < len(cells):
                                    field_cell = cells[cell_idx]
                                    field = field_cell.get_text(strip=True)
                                    colspan = field_cell.get('colspan', '1')
                                    cell_idx += 1

                                # 두 번째 셀 그룹 (기술, colspan=6)
                                if cell_idx < len(cells):
                                    skill_cell = cells[cell_idx]
                                    skill = skill_cell.get_text(strip=True)
                                    colspan = skill_cell.get('colspan', '1')
                                    cell_idx += 1

                                # 세 번째 셀 (레벨)
                                if cell_idx < len(cells):
                                    level_cell = cells[cell_idx]
                                    level_text = level_cell.get_text(strip=True)

                                # 유효한 데이터가 있을 경우만 저장
                                if field and skill and level_text:
                                    # 예시 텍스트나 비어있는 경우 스킵
                                    if '작성 예시' in field or '작성 예시' in skill:
                                        continue
                                    if field == '여기 파싱' or skill == '여기 파싱':
                                        continue

                                    # em 태그는 예시이므로 스킵
                                    field_elem = cells[0].find('em')
                                    skill_elem = cells[1].find('em') if len(cells) > 1 else None
                                    if field_elem or skill_elem:
                                        continue

                                    # 레벨 숫자 추출 (1, 2, 3)
                                    level_numbers = re.findall(r'\d+', level_text)
                                    level = int(level_numbers[0]) if level_numbers else 0

                                    # 레벨이 0이면 스킵 (비어있는 경우)
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
            error_msg = f"Parsing error for page {page_id}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
            import traceback
            errors.append(traceback.format_exc())

        if errors:
            data["parse_error_log"] = "\n".join(errors)

        return data

    def sync_applications(self, db: Session, batch_id: Optional[str] = None, force_update: bool = False) -> Dict[str, Any]:
        """
        Sync applications from Confluence

        Args:
            db: Database session
            batch_id: Batch identifier
            force_update: Update existing applications

        Returns:
            Sync result statistics
        """
        result = {
            "total_pages": 0,
            "new_count": 0,
            "updated_count": 0,
            "error_count": 0,
            "errors": []
        }

        # Get child pages
        pages = self.get_child_pages()
        result["total_pages"] = len(pages)

        print(f"\n{'='*80}")
        print(f"📥 Confluence 동기화 시작: 총 {len(pages)}개 페이지")
        print(f"{'='*80}\n")

        for idx, page in enumerate(pages, 1):
            try:
                page_id = page["id"]
                page_url = page["url"]

                print(f"[{idx}/{len(pages)}] 처리 중: Page ID {page_id}")

                # Check if already exists
                existing_app = db.query(Application).filter(
                    Application.confluence_page_id == page_id
                ).first()

                if existing_app and not force_update:
                    print(f"  ⏭️  기존 페이지 건너뜀")
                    continue

                # Get and parse content
                html_content = self.get_page_content(page_id)
                if not html_content:
                    result["error_count"] += 1
                    result["errors"].append(f"Failed to fetch page {page_id}")
                    continue

                parsed_data = self.parse_application(html_content, page_id, page_url)

                # Resolve department by division text
                if parsed_data.get("division"):
                    dept = db.query(Department).filter(
                        Department.name.like(f"%{parsed_data['division']}%")
                    ).first()
                    if dept:
                        parsed_data["department_id"] = dept.id

                if batch_id:
                    parsed_data["batch_id"] = batch_id

                if existing_app:
                    # Update existing
                    for key, value in parsed_data.items():
                        setattr(existing_app, key, value)
                    result["updated_count"] += 1
                    print(f"  ✅ 업데이트 완료")
                else:
                    # Create new
                    new_app = Application(**parsed_data)
                    db.add(new_app)
                    result["new_count"] += 1
                    print(f"  ✅ 신규 생성 완료")

                db.commit()

            except Exception as e:
                result["error_count"] += 1
                error_msg = f"Error processing page {page['id']}: {str(e)}"
                result["errors"].append(error_msg)
                print(f"  ❌ 오류 발생: {str(e)}")
                db.rollback()

        print(f"\n{'='*80}")
        print(f"✅ Confluence 동기화 완료")
        print(f"  총 페이지: {result['total_pages']}")
        print(f"  신규 생성: {result['new_count']}")
        print(f"  업데이트: {result['updated_count']}")
        print(f"  오류: {result['error_count']}")
        print(f"{'='*80}\n")

        return result

    def sync_single_application(self, db: Session, page_id: str, batch_id: Optional[str] = None, force_update: bool = True) -> Dict[str, Any]:
        """
        Sync a single application from Confluence by page ID

        Args:
            db: Database session
            page_id: Confluence page ID to sync
            batch_id: Batch identifier
            force_update: Update existing application (default: True)

        Returns:
            Sync result with application data
        """
        result = {
            "success": False,
            "action": None,  # "created", "updated", or "error"
            "application_id": None,
            "page_id": page_id,
            "error": None
        }

        try:
            # Check if already exists
            existing_app = db.query(Application).filter(
                Application.confluence_page_id == page_id
            ).first()

            if existing_app and not force_update:
                result["error"] = "Application already exists. Use force_update=true to update."
                return result

            # Get page URL (construct from page_id) - 사용자 접근용 링크
            page_url = f"{self.link_base_url}/pages/viewpage.action?pageId={page_id}"

            # Get and parse content
            html_content = self.get_page_content(page_id)
            if not html_content:
                result["error"] = f"Failed to fetch page content for {page_id}"
                return result

            parsed_data = self.parse_application(html_content, page_id, page_url)

            # Resolve department by division text
            if parsed_data.get("division"):
                dept = db.query(Department).filter(
                    Department.name.like(f"%{parsed_data['division']}%")
                ).first()
                if dept:
                    parsed_data["department_id"] = dept.id

            if batch_id:
                parsed_data["batch_id"] = batch_id

            if existing_app:
                # Update existing
                for key, value in parsed_data.items():
                    setattr(existing_app, key, value)
                result["action"] = "updated"
                result["application_id"] = existing_app.id
                result["success"] = True
                print(f"✅ Updated application: {page_id} (ID: {existing_app.id})")
            else:
                # Create new
                new_app = Application(**parsed_data)
                db.add(new_app)
                db.flush()  # Get the ID before commit
                result["action"] = "created"
                result["application_id"] = new_app.id
                result["success"] = True
                print(f"✅ Created new application: {page_id} (ID: {new_app.id})")

            db.commit()

        except Exception as e:
            result["error"] = str(e)
            error_msg = f"Error syncing page {page_id}: {str(e)}"
            print(f"❌ {error_msg}")
            db.rollback()

        return result


# Singleton instance
confluence_parser = ConfluenceParser()
