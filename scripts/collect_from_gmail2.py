import os
import base64
import re
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import requests
from urllib.parse import urlparse, parse_qs

# --- 설정 ---
# 토큰과 인증서 파일 경로를 설정하세요.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_PATH = 'token.json'
CREDS_PATH = 'credentials.json'
ARTICLES_DIR = os.path.join('docs', 'articles')

def get_gmail_service():
    """Gmail API 서비스 객체를 인증하고 반환합니다."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def resolve_redirect_url(url):
    """리디렉션 URL을 따라가 최종 목적지 URL을 반환합니다."""
    try:
        # HEAD 요청을 보내면 전체 페이지를 다운로드하지 않아 효율적입니다.
        response = requests.head(url, allow_redirects=True, timeout=10)
        # scholar.google.com/scholar_url 의 경우, 쿼리 파라미터에 실제 url이 들어있기도 합니다.
        parsed_url = urlparse(url)
        if 'scholar.google.com' in parsed_url.netloc and 'url=' in parsed_url.query:
             return parse_qs(parsed_url.query)['url'][0]
        
        if response.status_code == 200:
            return response.url
    except requests.RequestException as e:
        print(f" - Error resolving redirect for {url}: {e}")
    return None

def extract_links_from_body(body):
    """이메일 본문에서 URL들을 추출합니다."""
    # 간단한 정규식으로 URL을 찾습니다. 필요시 더 정교하게 수정할 수 있습니다.
    return re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', body)

def is_utility_link(url):
    """처리할 필요 없는 유틸리티성 링크인지 확인합니다."""
    utility_domains = [
        'google.com/search',
        'google.com/alerts',
        'google.com/citations',
        'scholar.google.com/scholar_alerts',
    ]
    return any(domain in url for domain in utility_domains)

def process_article(url, title):
    """기사/논문 처리: 요약, 번역 및 마크다운 파일 생성 (향후 구현)"""
    # 파일명으로 사용할 수 없는 문자 제거
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
    filename = f"{safe_title.replace(' ', '-')}.md"
    filepath = os.path.join(ARTICLES_DIR, filename)

    if os.path.exists(filepath):
        print(f" - SKIPPING: Article already exists - {filename}")
        return

    print(f"Found article: {title}")
    
    # TODO: 여기에 기사/논문 내용을 가져와서 LLM으로 요약/번역하는 로직 추가
    summary_ko = "이곳에 한국어 요약이 들어갑니다."
    
    content = f"""---
title: "{title}"
---

# {title}

## 한국어 요약

{summary_ko}

## 원문 링크

[{url}]({url})
"""
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Created: {filepath}")

def main():
    """메인 실행 함수: Gmail에서 메일을 읽어와 처리합니다."""
    service = get_gmail_service()
    # 'from:scholaralerts-noreply@google.com' 와 같이 특정 발신자나 제목으로 쿼리를 구체화할 수 있습니다.
    results = service.users().messages().list(userId='me', q='is:unread from:scholaralerts-noreply@google.com').execute()
    messages = results.get('messages', [])

    if not messages:
        print("No new messages found.")
        return

    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id']).execute()
        payload = msg['payload']
        
        # 이메일 제목(기사 제목으로 활용)
        headers = payload.get("headers", [])
        subject = next((i['value'] for i in headers if i['name'] == "Subject"), None)
        
        if 'data' in payload['body']:
            data = payload['body']['data']
            body = base64.urlsafe_b64decode(data).decode('utf-8')
            links = extract_links_from_body(body)
            
            for link in links:
                print(f"- Checking link: {link}")
                
                final_url = link
                if 'scholar.google.com' in link:
                    resolved = resolve_redirect_url(link)
                    if resolved:
                        print(f"  - Resolved to: {resolved}")
                        final_url = resolved
                    else:
                        print(f"  - SKIPPING: Could not resolve redirect.")
                        continue

                if is_utility_link(final_url):
                    print(f"  - SKIPPING: Utility or non-article link.")
                    continue

                # TODO: 여기서 final_url을 가지고 실제 기사인지 한번 더 확인하는 로직이 있으면 좋습니다.
                # 예: newspaper3k 라이브러리 사용 등
                
                # 제목이 여러개일 수 있으므로, 알림 메일의 제목을 기사 제목으로 사용합니다.
                process_article(final_url, subject)
                
                # 하나의 이메일에서 유효한 링크 하나만 처리하고 다음 메일로 넘어갑니다.
                break 

if __name__ == '__main__':
    main()