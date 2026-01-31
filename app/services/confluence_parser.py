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
            # 기본사항 파싱 - 헤더 행 다음 행에서 실제 내용 추출
            # class="subject" 등의 헤더 셀은 보통 비어있고, 다음 <tr>의 <td>에 내용이 있음
            
            # 과제명 (class="subject")
            subject_elem = soup.find(class_="subject")
            if subject_elem:
                header_row = subject_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            data["subject"] = content_cell.get_text(strip=True)
            
            # 소속 (class="division")
            division_elem = soup.find(class_="division")
            if division_elem:
                header_row = division_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            data["division"] = content_cell.get_text(strip=True)
            
            # 참여인원 (class="dept")
            dept_elem = soup.find(class_="dept")
            if dept_elem:
                header_row = dept_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            dept_text = content_cell.get_text(strip=True)
                            # 숫자만 추출
                            numbers = re.findall(r'\d+', dept_text)
                            if numbers:
                                data["participant_count"] = int(numbers[0])
            
            # 대표자 정보 - colspan 기반 파싱 (구조 분석 필요)
            # 예: 테이블에서 "대표자" 라벨을 찾고 다음 td에서 이름, Knox ID 추출
            rep_cells = soup.find_all('td', colspan=True)
            for cell in rep_cells:
                text = cell.get_text(strip=True)
                if '대표자' in text or 'Knox' in text:
                    # 이름과 Knox ID 분리 로직
                    parts = text.split()
                    if len(parts) >= 2:
                        data["representative_name"] = parts[0]
                        data["representative_knox_id"] = parts[1] if len(parts) > 1 else None
            
            # 사전 설문 파싱 - 헤더 행 다음 행에서 실제 내용 추출
            pre_survey = {}
            for i in range(1, 7):
                q_elem = soup.find(class_=f"q{i}")
                if q_elem:
                    header_row = q_elem.find_parent('tr')
                    if header_row:
                        next_row = header_row.find_next_sibling('tr')
                        if next_row:
                            content_cell = next_row.find('td')
                            if content_cell:
                                pre_survey[f"q{i}"] = content_cell.get_text(strip=True)
            if pre_survey:
                data["pre_survey"] = pre_survey
            
            # 신청 내용 파싱 - 헤더 행 다음 행에서 실제 내용 추출
            # class="pain" 등의 헤더 셀은 보통 비어있고, 다음 <tr>의 <td>에 내용이 있음
            
            # 현업업무 (class="pain")
            pain_elem = soup.find(class_="pain")
            if pain_elem:
                # 헤더 행(<tr>)의 다음 형제 행에서 내용 추출
                header_row = pain_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            data["current_work"] = content_cell.get_text(strip=True)
            
            # Pain Point (class="pain_point" 또는 별도 섹션)
            pain_point_elem = soup.find(class_="pain_point")
            if pain_point_elem:
                header_row = pain_point_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            data["pain_point"] = content_cell.get_text(strip=True)
            
            # 개선아이디어 (class="improve")
            improve_elem = soup.find(class_="improve")
            if improve_elem:
                header_row = improve_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            data["improvement_idea"] = content_cell.get_text(strip=True)
            
            # 기대효과 (class="effect")
            effect_elem = soup.find(class_="effect")
            if effect_elem:
                header_row = effect_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            data["expected_effect"] = content_cell.get_text(strip=True)
            
            # AI팀에 바라는 점 (class="hope")
            hope_elem = soup.find(class_="hope")
            if hope_elem:
                header_row = hope_elem.find_parent('tr')
                if header_row:
                    next_row = header_row.find_next_sibling('tr')
                    if next_row:
                        content_cell = next_row.find('td')
                        if content_cell:
                            data["hope"] = content_cell.get_text(strip=True)
            
            # 기술 역량 파싱 (중첩 테이블)
            tech_capabilities = []
            # 기술 역량 섹션 찾기
            for table in soup.find_all('table'):
                headers = [th.get_text(strip=True) for th in table.find_all('th')]
                if any('기술' in h or '역량' in h for h in headers):
                    for row in table.find_all('tr')[1:]:  # 헤더 제외
                        cells = row.find_all('td')
                        if len(cells) >= 3:
                            category = cells[0].get_text(strip=True)
                            skill = cells[1].get_text(strip=True)
                            level_text = cells[2].get_text(strip=True)
                            # 레벨 숫자 추출
                            level_numbers = re.findall(r'\d+', level_text)
                            level = int(level_numbers[0]) if level_numbers else 0
                            
                            tech_capabilities.append({
                                "category": category,
                                "skill": skill,
                                "level": level
                            })
            if tech_capabilities:
                data["tech_capabilities"] = tech_capabilities
            
            # 기타 데이터 수집 (class 없는 데이터)
            etc_data = {}
            # 추가적인 파싱 로직...
            if etc_data:
                data["etc_data"] = etc_data
            
        except Exception as e:
            error_msg = f"Parsing error for page {page_id}: {str(e)}"
            errors.append(error_msg)
            print(f"❌ {error_msg}")
        
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


# Singleton instance
confluence_parser = ConfluenceParser()
