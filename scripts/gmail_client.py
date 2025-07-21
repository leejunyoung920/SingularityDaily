import os.path
import base64
import re
from . import config

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_PATH = config.PROJECT_ROOT / "token.json"
CREDENTIALS_PATH = config.PROJECT_ROOT / "credentials.json"

def get_gmail_service():
    """Gmail API 서비스 객체를 인증하고 반환합니다."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                print(f"Token has been revoked or expired, please re-authenticate: {e}")
                TOKEN_PATH.unlink() # Delete expired token
                return get_gmail_service() # Retry
        else:
            if not CREDENTIALS_PATH.exists():
                print(f"Error: credentials.json not found at {CREDENTIALS_PATH}")
                print("Please download it from Google Cloud Console and place it in the project root.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def get_links_from_gmail():
    """읽지 않은 모든 이메일을 검색하고 본문에서 URL을 추출합니다."""
    service = get_gmail_service()
    if not service:
        return []

    # 읽지 않은 모든 메일을 대상으로 검색
    query = 'is:unread'
    try:
        results = service.users().messages().list(userId='me', q=query).execute()
    except HttpError as error:
        print(f"An error occurred while searching emails: {error}")
        return []

    messages = results.get('messages', [])

    if not messages:
        print("No new unread emails found.")
        return []

    links = []
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'

    print(f"Found {len(messages)} new unread email(s). Processing...")
    for message_info in messages:
        try:
            msg = service.users().messages().get(userId='me', id=message_info['id'], format='full').execute()
            payload = msg.get('payload', {})
            
            body_data = None
            if 'data' in payload.get('body', {}):
                body_data = payload['body']['data']
            # multipart 이메일 처리 (e.g., text/plain and text/html)
            elif 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                        body_data = part['body']['data']
                        break # text/plain을 우선적으로 사용
            
            if body_data:
                body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                found_urls = re.findall(url_pattern, body)
                if found_urls:
                    links.extend(found_urls)
            
            # 처리된 이메일은 '읽음'으로 표시 (UNREAD 라벨 제거)
            service.users().messages().modify(userId='me', id=message_info['id'], body={'removeLabelIds': ['UNREAD']}).execute()
        
        except HttpError as error:
            print(f"An error occurred while processing message ID {message_info['id']}: {error}")
            continue # 다음 메시지로 계속 진행
    
    return list(set(links)) # 중복 제거 후 반환

if __name__ == '__main__':
    """
    이 스크립트를 직접 실행할 때 테스트를 위해 사용됩니다.
    Gmail에서 링크를 가져와서 출력합니다.
    """
    print("--- Testing get_links_from_gmail() ---")
    links_found = get_links_from_gmail()
    if links_found:
        print("\nFound links:")
        for link in links_found:
            print(f"- {link}")