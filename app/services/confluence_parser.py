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

# Disable SSL warnings when verify=False is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ConfluenceParser:
    """Confluence API client and HTML parser"""
    
    def __init__(self):
        self.base_url = settings.confluence_base_url.rstrip('/')
        self.auth = (settings.confluence_username, settings.confluence_password)
        self.space_key = settings.confluence_space_key
        self.parent_page_id = settings.confluence_parent_page_id
        
    def get_child_pages(self) -> List[Dict[str, str]]:
        """
        Get child pages under parent page
        
        Returns:
            List of pages with id, title, url
        """
        url = f"{self.base_url}/rest/api/content/{self.parent_page_id}/child/page"
        params = {"limit": 500, "expand": "version"}
        
        try:
            response = requests.get(url, auth=self.auth, params=params, timeout=30, verify=False)
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
        except Exception as e:
            print(f"❌ Error fetching child pages: {e}")
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
        
        try:
            response = requests.get(url, auth=self.auth, params=params, timeout=30, verify=False)
            response.raise_for_status()
            data = response.json()
            return data.get("body", {}).get("view", {}).get("value")
        except Exception as e:
            print(f"❌ Error fetching page {page_id}: {e}")
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
            # 기본사항 파싱
            subject_elem = soup.find(class_="subject")
            if subject_elem:
                data["subject"] = subject_elem.get_text(strip=True)
            
            division_elem = soup.find(class_="division")
            if division_elem:
                data["division"] = division_elem.get_text(strip=True)
            
            dept_elem = soup.find(class_="dept")
            if dept_elem:
                dept_text = dept_elem.get_text(strip=True)
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
            
            # 사전 설문 파싱
            pre_survey = {}
            for i in range(1, 7):
                q_elem = soup.find(class_=f"q{i}")
                if q_elem:
                    pre_survey[f"q{i}"] = q_elem.get_text(strip=True)
            if pre_survey:
                data["pre_survey"] = pre_survey
            
            # 신청 내용 파싱
            pain_elem = soup.find(class_="pain")
            if pain_elem:
                data["current_work"] = pain_elem.get_text(strip=True)
            
            # Pain point는 별도 섹션에서 추출 (class 없을 수 있음)
            # 헤더 텍스트로 찾기
            for heading in soup.find_all(['h2', 'h3', 'strong']):
                heading_text = heading.get_text(strip=True)
                if 'Pain' in heading_text or 'pain' in heading_text:
                    # 다음 요소에서 텍스트 추출
                    next_elem = heading.find_next(['p', 'div'])
                    if next_elem:
                        data["pain_point"] = next_elem.get_text(strip=True)
            
            improve_elem = soup.find(class_="improve")
            if improve_elem:
                data["improvement_idea"] = improve_elem.get_text(strip=True)
            
            effect_elem = soup.find(class_="effect")
            if effect_elem:
                data["expected_effect"] = effect_elem.get_text(strip=True)
            
            hope_elem = soup.find(class_="hope")
            if hope_elem:
                data["hope"] = hope_elem.get_text(strip=True)
            
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
                
                # Rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                result["error_count"] += 1
                error_msg = f"Error processing page {page['id']}: {str(e)}"
                result["errors"].append(error_msg)
                print(f"❌ {error_msg}")
                db.rollback()
        
        return result


# Singleton instance
confluence_parser = ConfluenceParser()
