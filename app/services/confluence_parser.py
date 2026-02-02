"""
Confluence Parser Service
"""
import re
import time
import json
import requests
import urllib3
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.application import Application
from app.models.department import Department
from app.services.rate_limiter import RateLimiter

# Disable SSL warnings when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def html_to_text(element) -> str:
    """
    Convert HTML element to formatted text preserving structure

    Converts:
    - <br> → newline
    - <p> → newline separation
    - <ul><li> → bullet points
    - <ol><li> → numbered list
    - Preserves line breaks and list formatting
    """
    if not element:
        return ""

    result = []

    def process_element(elem, list_counter=None):
        """Recursively process HTML elements"""
        if elem.name is None:
            # Text node
            text = str(elem).strip()
            if text:
                result.append(text)
        elif elem.name == 'br':
            result.append('\n')
        elif elem.name == 'p':
            for child in elem.children:
                process_element(child)
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
        elif elem.name in ['strong', 'b', 'em', 'i', 'span', 'div']:
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
                        "url": f"{self.base_url}/pages/viewpage.action?pageId={page['id']}"
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
            # III. 신청 내용 파싱
            # ============================================================
            # 섹션 헤더를 찾아서 내용 추출하는 헬퍼 함수
            def find_section_content(section_number: str, section_keyword: str) -> Optional[str]:
                """
                섹션 번호와 키워드로 내용을 찾는 함수
                헤더가 여러 <strong> 태그로 분리될 수 있으므로 td 전체 텍스트를 확인
                HTML 포맷을 유지하여 줄바꿈과 리스트를 보존
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
                                        # HTML을 포맷된 텍스트로 변환
                                        text = html_to_text(content_cell)
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
        
        for page in pages:
            try:
                page_id = page["id"]
                page_url = page["url"]
                
                # Check if already exists
                existing_app = db.query(Application).filter(
                    Application.confluence_page_id == page_id
                ).first()
                
                if existing_app and not force_update:
                    print(f"⏭️  Skipping existing page: {page_id}")
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
                    print(f"✅ Updated application: {page_id}")
                else:
                    # Create new
                    new_app = Application(**parsed_data)
                    db.add(new_app)
                    result["new_count"] += 1
                    print(f"✅ Created new application: {page_id}")
                
                db.commit()
                
            except Exception as e:
                result["error_count"] += 1
                error_msg = f"Error processing page {page['id']}: {str(e)}"
                result["errors"].append(error_msg)
                print(f"❌ {error_msg}")
                db.rollback()
        
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

            # Get page URL (construct from page_id)
            page_url = f"{self.base_url}/wiki/spaces/{os.getenv('CONFLUENCE_SPACE_KEY', '')}/pages/{page_id}"

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
