import os
import re
import email
from email.header import decode_header, make_header
from pathlib import Path
import yaml
from datetime import datetime
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- 설정 ---
# 프로젝트 루트 디렉터리
PROJECT_ROOT = Path(__file__).parent
# 토픽 마크다운 파일이 생성될 디렉터리 (docs 폴더 내부)
TOPIC_DIR = PROJECT_ROOT / "docs" / "topic"
# mkdocs.yml 파일 경로
MKDOCS_CONFIG_PATH = PROJECT_ROOT / "mkdocs.yml"

# --- Gmail API 설정 ---
# 처리할 이메일을 식별하는 Gmail 검색어. 예: 'is:unread', 'label:my-label'
# 참고: https://support.google.com/mail/answer/7190
GMAIL_QUERY = 'is:unread'
# 처리 후 이메일을 이동시킬 라벨 이름. 라벨이 없다면 자동 생성됩니다.
# None으로 설정하면 아무 작업도 하지 않습니다.
GMAIL_LABEL_AFTER_PROCESS = 'Processed'
# Google Cloud에서 다운로드한 credentials.json 파일 경로
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
# 인증 후 생성되는 토큰 파일 경로
TOKEN_FILE = PROJECT_ROOT / "token.json"
# API 스코프. 이메일 읽기 및 수정을 위해 'gmail.modify' 사용
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


# --- 함수 정의 ---

def decode_mime_header(header_string):
    """MIME 인코딩된 헤더(제목 등)를 디코딩합니다."""
    if not header_string:
        return ""
    decoded_parts = decode_header(header_string)
    return str(make_header(decoded_parts))

def slugify(text):
    """문자열을 URL 친화적인 슬러그로 변환합니다."""
    # 한글, 영문, 숫자, 하이픈, 공백만 남기고 나머지 제거
    text = re.sub(r'[^A-Za-z0-9가-힣\s-]', '', text).strip().lower()
    # 공백을 하이픈으로 교체
    text = re.sub(r'\s+', '-', text)
    return text

def create_md_from_email(raw_email_bytes, email_id):
    """ Gmail에서 받은 raw email 데이터로 마크다운 파일을 생성합니다. """
    msg = email.message_from_bytes(raw_email_bytes)

    subject = decode_mime_header(msg['subject'])
    from_name = decode_mime_header(msg['from']).split('<')[0].strip().replace('"', '')
    
    try:
        date_obj = datetime.strptime(msg['date'], '%a, %d %b %Y %H:%M:%S %z')
        date_str = date_obj.strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        date_str = datetime.now().strftime('%Y-%m-%d')

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                charset = part.get_content_charset() or 'utf-8'
                body = part.get_payload(decode=True).decode(charset, errors='replace')
                break
    else:
        charset = msg.get_content_charset() or 'utf-8'
        body = msg.get_payload(decode=True).decode(charset, errors='replace')

    if not subject:
        print(f"경고: 이메일 ID {email_id}에 제목이 없어 건너뜁니다.")
        return None

    md_content = f"""---
title: "{subject}"
date: {date_str}
author: "{from_name}"
---

# {subject}

{body}
"""
    slug = slugify(subject)
    if not slug:
        print(f"경고: 이메일 ID {email_id}의 제목으로 유효한 파일명을 만들 수 없어 건너뜁니다.")
        return None
        
    md_filename = f"{slug}.md"
    md_filepath = TOPIC_DIR / md_filename
    
    md_filepath.write_text(md_content, encoding='utf-8')
    print(f"성공: '{md_filepath}' 파일이 생성되었습니다.")
    
    return f"topic/{md_filename}"

def update_mkdocs_nav(new_topic_files):
    """mkdocs.yml 파일의 네비게이션을 업데이트합니다."""
    if not new_topic_files:
        print("네비게이션에 추가할 새 파일이 없습니다.")
        return

    with open(MKDOCS_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    nav = config.get('nav', [])
    topic_section_list = None
    
    for item in nav:
        if isinstance(item, dict) and '주요 토픽' in item:
            topic_section_list = item['주요 토픽']
            break
    
    if topic_section_list is None:
        topic_section_list = ['topic/index.md']
        nav.append({'주요 토픽': topic_section_list})
        topic_index_path = TOPIC_DIR / "index.md"
        if not topic_index_path.exists():
            topic_index_path.write_text("# 주요 토픽\n\n이메일에서 생성된 주요 토픽 목록입니다.", encoding='utf-8')
            print(f"생성: '{topic_index_path}'")

    existing_files = {str(entry) for entry in topic_section_list}
    
    added_count = 0
    for file_path in new_topic_files:
        if file_path not in existing_files:
            topic_section_list.append(file_path)
            added_count += 1

    if added_count > 0:
        with open(MKDOCS_CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        print(f"성공: {MKDOCS_CONFIG_PATH.name} 파일의 네비게이션에 {added_count}개의 새 토픽을 추가했습니다.")
    else:
        print("네비게이션에 이미 모든 파일이 존재합니다.")

def get_gmail_service():
    """Gmail API 서비스 객체를 생성하고 반환합니다."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def get_or_create_label(service, label_name):
    """주어진 이름의 라벨 ID를 찾거나, 없으면 새로 생성합니다."""
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])

    for label in labels:
        if label['name'] == label_name:
            return label['id']

    # 라벨이 없으면 생성
    label_body = {'name': label_name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}
    created_label = service.users().labels().create(userId='me', body=label_body).execute()
    print(f"라벨 '{label_name}'을(를) 생성했습니다.")
    return created_label['id']

def main():
    """메인 실행 함수: Gmail에서 이메일을 가져와 처리합니다."""
    TOPIC_DIR.mkdir(exist_ok=True)
    service = get_gmail_service()
    if not service:
        return

    # 처리할 이메일 목록 가져오기
    results = service.users().messages().list(userId='me', q=GMAIL_QUERY).execute()
    messages = results.get('messages', [])

    if not messages:
        print("처리할 새 이메일이 없습니다.")
        return

    print(f"총 {len(messages)}개의 이메일을 발견했습니다. 처리를 시작합니다...")
    
    # 처리 후 이동할 라벨 ID 가져오기 (또는 생성)
    processed_label_id = None
    if GMAIL_LABEL_AFTER_PROCESS:
        processed_label_id = get_or_create_label(service, GMAIL_LABEL_AFTER_PROCESS)

    newly_created_files = []
    for message in messages:
        msg_id = message['id']
        # 이메일 원문(raw) 가져오기
        raw_msg = service.users().messages().get(userId='me', id=msg_id, format='raw').execute()
        raw_email_bytes = base64.urlsafe_b64decode(raw_msg['raw'].encode('ASCII'))
        
        # 마크다운 파일 생성
        nav_path = create_md_from_email(raw_email_bytes, msg_id)
        if nav_path:
            newly_created_files.append(nav_path)
            
            # 이메일 처리 후 라벨 변경 (예: 읽음 처리 및 'Processed' 라벨 추가)
            if processed_label_id:
                modify_body = {'addLabelIds': [processed_label_id], 'removeLabelIds': ['UNREAD']}
                service.users().messages().modify(userId='me', id=msg_id, body=modify_body).execute()
                print(f"이메일 ID {msg_id}를 '{GMAIL_LABEL_AFTER_PROCESS}'로 이동했습니다.")

    update_mkdocs_nav(newly_created_files)

if __name__ == "__main__":
    main()