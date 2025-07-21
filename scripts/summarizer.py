import requests
import google.generativeai as genai
import re
import trafilatura
from io import BytesIO
from bs4 import BeautifulSoup
from . import config

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

def get_article_text(url):
    """주어진 URL에서 기사 본문을 추출합니다. HTML과 PDF를 지원하며, 추출 실패 시 대체 방법을 사용합니다."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status() # HTTP 에러 발생 시 예외 발생

        content_type = response.headers.get('Content-Type', '').lower()

        if 'application/pdf' in content_type:
            if not PYPDF_AVAILABLE:
                print(f"  - WARNING: PDF content at {url}, but 'pypdf' is not installed. Skipping.")
                return None
            
            print(f"  - INFO: PDF content detected. Extracting text from {url}")
            with BytesIO(response.content) as pdf_file:
                reader = PdfReader(pdf_file)
                text = "".join(page.extract_text() or "" for page in reader.pages)
            
            if not text:
                print(f"  - WARNING: Could not extract text from PDF at {url}")
                return None
            return text.strip()

        # 1. trafilatura를 사용하여 HTML에서 본문을 추출 시도 (기본 방법)
        article_text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        
        # 2. trafilatura가 실패하면 BeautifulSoup으로 대체 추출 시도 (대체 방법)
        if not article_text:
            print(f"  - INFO: trafilatura failed. Falling back to BeautifulSoup for {url}")
            soup = BeautifulSoup(response.text, "html.parser")
            # <article> 태그를 먼저 찾아봅니다.
            article_tag = soup.find("article")
            if article_tag:
                article_text = article_tag.get_text(separator='\n', strip=True)
            else:
                # <article> 태그가 없으면 <p> 태그들을 모읍니다.
                paragraphs = soup.find_all("p")
                if paragraphs:
                    article_text = "\n".join(p.get_text(strip=True) for p in paragraphs)

        if not article_text:
            print(f"Could not extract main content from {url} (Content-Type: {content_type})")
            return None
        return article_text.strip()

    except requests.exceptions.RequestException as e:
        print(f"Error fetching or extracting article content from {url}: {e}")
        return None
    except Exception as e:
        # pypdf 등 다른 라이브러리에서 발생할 수 있는 예외 처리
        print(f"Error processing content from {url}: {e}")
        return None

def summarize_article_with_gemini(title, url):
    """Gemini API를 사용하여 기사를 요약하고 번역합니다."""
    content = get_article_text(url)
    if not content:
        return None, None

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')

        prompt = f"""
        아래는 기술 관련 기사입니다. 제목과 내용을**한국어로 읽고**, 다음 2가지를 작성해주세요:

        1. 원제목을 한국어로 번역한 제목 (한 문장, 너무 직역하지 말고 자연스럽게)
        2. 기사 내용의 핵심 요약 (한국어로 5줄 이내)

        다음 형식으로만 출력하고, 다른 설명은 절대 추가하지 마세요:

        번역 제목: ...
        요약:
        ...

        ---
        제목: {title}
        내용: {content[:3500]}
        """
        response = model.generate_content(prompt)
        summary_text = response.text

        match_title = re.search(r"번역 제목:\s*(.*)", summary_text)
        match_summary = re.search(r"요약:\s*([\s\S]*)", summary_text, re.MULTILINE)

        if match_title and match_summary:
            korean_title = match_title.group(1).strip()
            summary = match_summary.group(1).strip()
            return korean_title, summary
        else:
            print(f"  - WARNING: Could not parse summary response for {url}. Raw response: {summary_text[:200]}...")
            return None, None
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return None, None