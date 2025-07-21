# common_utils.py
import os
import re
import requests
import trafilatura
from dotenv import load_dotenv
import google.generativeai as genai
from io import BytesIO
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# .env 파일에서 환경 변수 로드
load_dotenv()

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


# Gemini API 설정
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# API가 이미 설정되었는지 확인하기 위한 플래그
_gemini_configured = False

def _ensure_gemini_configured():
    """Gemini API가 사용 전에 설정되었는지 확인합니다."""
    global _gemini_configured
    if _gemini_configured:
        return True
    
    if not GOOGLE_API_KEY:
        print("⚠️ API 호출 실패: GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다.")
        return False
    
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        _gemini_configured = True
        return True
    except Exception as e:
        print(f"⚠️ Gemini API 설정 실패: {e}")
        return False

def strip_html_tags(text):
    return re.sub(r"<.*?>", "", text or "")


def clean_google_url(url):
    """Google Alerts 및 Scholar의 리디렉션 URL에서 실제 기사 URL을 추출합니다."""
    if not url:
        return url
    
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    
    if hostname and 'google.com' in hostname and ('/url' in parsed_url.path or '/scholar_url' in parsed_url.path):
        query_params = parse_qs(parsed_url.query)
        target_url = query_params.get('q', [None])[0] or query_params.get('url', [None])[0]
        if target_url:
            return target_url
    return url


def translate_text(text):
    """Gemini API를 사용하여 텍스트를 한국어로 번역합니다."""
    if not text.strip():
        return ""
    if not _ensure_gemini_configured():
        return ""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = (
            "Please translate the following text into Korean. "
            "Return only the translation, with no explanation, no greetings, and no formatting.\n"
            f"Text to translate:\n{text}"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ 번역 실패 (Gemini API): {e}")
        return ""


def summarize_and_translate_body(text):
    """Gemini API를 사용하여 논문 본문을 더 긴 한국어 요약으로 생성합니다."""
    if not text.strip():
        return ""
    if not _ensure_gemini_configured():
        return ""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = (
            "You are a helpful assistant for a researcher. "
            "The following text is an abstract or the body of a research paper. "
            "Please read it and provide a comprehensive summary in Korean. "
            "The summary should be detailed, around 8-10 sentences long, capturing the key points, methodology, and conclusions of the paper. "
            "Return only the Korean summary, with no other explanations or greetings.\n\n"
            f"Text to summarize:\n{text}"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ 요약 실패 (Gemini API): {e}")
        return ""


def fetch_article_body(url, max_length=4000):
    """주어진 URL에서 기사/논문 본문을 추출합니다. HTML과 PDF를 지원하며, 추출 실패 시 대체 방법을 사용합니다."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '').lower()

        # PDF 처리
        if 'application/pdf' in content_type:
            if not PYPDF_AVAILABLE:
                print(f"  - ⚠️ 경고: PDF 콘텐츠({url}) 발견, 하지만 'pypdf'가 설치되지 않아 건너뜁니다.")
                return None
            
            print(f"  - ℹ️ 정보: PDF 콘텐츠 감지. 텍스트 추출 중... ({url})")
            with BytesIO(response.content) as pdf_file:
                reader = PdfReader(pdf_file)
                text = "".join(page.extract_text() or "" for page in reader.pages)
            
            if not text:
                print(f"  - ⚠️ 경고: PDF에서 텍스트를 추출할 수 없습니다 ({url})")
                return None
            return text.strip()[:max_length]

        # HTML 처리 (trafilatura가 기본, BeautifulSoup이 대체)
        article_text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        
        if not article_text:
            print(f"  - ℹ️ 정보: trafilatura 실패. BeautifulSoup으로 대체합니다 ({url})")
            soup = BeautifulSoup(response.text, "html.parser")
            article_tag = soup.find("article")
            if article_tag:
                article_text = article_tag.get_text(separator='\n', strip=True)

        if not article_text:
            print(f"⚠️ 본문 크롤 실패: 메인 콘텐츠를 추출할 수 없습니다 ({url})")
            return None
            
        return article_text.strip()[:max_length]

    except Exception as e:
        print(f"⚠️ 본문 크롤 실패 (오류 발생): {url}: {e}")
        return None

def is_duplicate_md(filepath, original_title):
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            return original_title in content
    except:
        return False

def safe_filename(text, max_length=80):
    text = re.sub(r"[\\/:*?\"<>|]", "", text)
    return text.strip()[:max_length]
