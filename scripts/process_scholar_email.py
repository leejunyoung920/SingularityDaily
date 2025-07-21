import email
import logging
import os
import re
import base64
import json
from email.header import decode_header
from time import sleep

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .common_utils import (
    clean_google_url,
    fetch_article_body,
    is_duplicate_md,
    safe_filename,
    translate_text,
    summarize_and_translate_body,
)

# --- Constants ---
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = "token.json"
CREDENTIALS_PATH = "credentials.json"
SEEN_PAPERS_FILE = "seen_scholar_messages.json"

PAPERS_OUTPUT_DIR = os.path.join("docs", "keywords")
MIN_BODY_LENGTH = 300
API_RATE_LIMIT_DELAY = 1.5  # seconds


# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


def get_gmail_service():
    """Gmail API 서비스 객체를 인증하고 반환합니다."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                logging.error(f"'{CREDENTIALS_PATH}' 파일을 찾을 수 없습니다. Google Cloud에서 다운로드 받아주세요.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def get_html_payload_from_message(msg):
    """Gmail API 메시지 객체에서 HTML payload를 재귀적으로 찾습니다."""
    if "parts" in msg["payload"]:
        for part in msg["payload"]["parts"]:
            if part["mimeType"] == "text/html":
                return part["body"].get("data")
            data = get_html_payload_from_message({"payload": part})
            if data:
                return data
    elif msg["payload"]["mimeType"] == "text/html":
        return msg["payload"]["body"].get("data")
    return None


def parse_scholar_email(msg):
    """Gmail 메시지를 파싱하여 키워드와 논문 목록을 추출합니다."""
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    subject = headers.get("Subject", "")
    keyword = subject.split(" - ")[0].strip()
    logging.info(f"🔑 추출된 키워드: {keyword}")

    # HTML 본문 추출
    body_data = get_html_payload_from_message(msg)
    if not body_data:
        logging.error("이메일에서 HTML 콘텐츠를 찾을 수 없습니다.")
        return keyword, []

    html_content = base64.urlsafe_b64decode(body_data).decode("utf-8")
    if not html_content:
        logging.error("이메일에서 HTML 콘텐츠를 찾을 수 없습니다.")
        return keyword, []

    soup = BeautifulSoup(html_content, "html.parser")
    articles = []

    # 각 논문 항목을 파싱합니다.
    # Google 이메일 템플릿 변경에 대응하기 위해 h3 태그 대신 a 태그를 직접 찾도록 수정합니다.
    for link_tag in soup.find_all("a", class_="gse_alrt_title"):
        title_en = link_tag.get_text(strip=True)
        url = link_tag.get("href", "")

        if not title_en or not url:
            continue

        # 스니펫(요약)을 찾습니다. a 태그의 부모(h3)를 찾고, 그 다음 형제 요소를 찾습니다.
        # 이 구조는 유연성을 제공합니다. 스니펫을 못찾아도 에러가 발생하지 않습니다.
        snippet = ""
        h3_parent = link_tag.find_parent("h3")
        if h3_parent:
            snippet_tag = h3_parent.find_next_sibling("div", class_="gse_alrt_sni")
            if snippet_tag:
                snippet = snippet_tag.get_text(strip=True)

        articles.append({"title_en": title_en, "url": url, "snippet": snippet})

    logging.info(f"📄 이메일에서 {len(articles)}개의 논문을 찾았습니다.")
    return keyword, articles


def get_existing_titles(keyword):
    """키워드 디렉토리에서 기존에 저장된 모든 논문의 원본 제목 set을 가져옵니다."""
    titles = set()
    folder = os.path.join(PAPERS_OUTPUT_DIR, keyword)
    if not os.path.exists(folder):
        return titles

    for filename in os.listdir(folder):
        if filename.endswith(".md"):
            filepath = os.path.join(folder, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    match = re.search(r"\*\*원제목:\*\*\s*(.*)", content)
                    if match:
                        titles.add(match.group(1).strip())
            except Exception as e:
                logging.warning(f"기존 파일 읽기 오류 {filepath}: {e}")
    return titles


def save_paper_markdown(keyword, title_ko, title_en, summary_ko, url, existing_titles):
    """논문 요약을 마크다운 파일로 저장하고 중복을 확인합니다."""
    try:
        if title_en in existing_titles:
            logging.info(f"🚫 중복 논문: {title_en}")
            return

        safe_title = safe_filename(title_ko)
        folder = os.path.join(PAPERS_OUTPUT_DIR, keyword)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{safe_title}.md")

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {title_ko}\n\n")
            f.write(f"**원제목:** {title_en}\n\n")
            f.write(f"**요약:** {summary_ko}\n\n")
            f.write(f"[원문 링크]({url})\n")
        logging.info(f"✅ 저장 완료: {path}")
        existing_titles.add(title_en)  # 처리된 목록에 추가

    except Exception as e:
        logging.error(f"파일 저장 중 오류 발생 ({title_en}): {e}")


def load_seen_ids():
    """처리된 이메일 ID 목록을 불러옵니다."""
    if os.path.exists(SEEN_PAPERS_FILE):
        with open(SEEN_PAPERS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_ids(ids):
    """처리된 이메일 ID 목록을 저장합니다."""
    with open(SEEN_PAPERS_FILE, "w") as f:
        json.dump(list(ids), f)


def main():
    service = get_gmail_service()
    if not service:
        return

    # 읽지 않은 구글 스칼라 알리미 메일만 가져오도록 쿼리를 복원합니다.
    query = "from:scholaralerts-noreply@google.com is:unread"
    results = service.users().messages().list(userId="me", q=query).execute()
    messages = results.get("messages", [])

    if not messages:
        logging.info("처리할 새 Google Scholar 알리미 메일이 없습니다.")
        return

    logging.info(f"총 {len(messages)}개의 새 알리미 메일을 발견했습니다.")
    seen_ids = load_seen_ids()

    for msg_info in messages:
        msg_id = msg_info["id"]
        if msg_id in seen_ids:
            continue

        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        keyword, articles = parse_scholar_email(msg)
        if not articles:
            continue

        existing_titles = get_existing_titles(keyword)
        logging.info(f"기존에 저장된 '{keyword}' 논문 {len(existing_titles)}개를 확인했습니다.")

        for article in articles:
            title_en, link_url, snippet = article["title_en"], article["url"], article["snippet"]
            logging.info(f"--- ⚙️ 처리 시작: {title_en} ---")

            link = clean_google_url(link_url)
            
            # 1. 본문 추출을 먼저 시도합니다.
            body = fetch_article_body(link)

            # 2. 본문 추출에 실패했거나 내용이 너무 짧으면, 이메일의 스니펫을 대체재로 사용합니다.
            if not body or len(body.strip()) < MIN_BODY_LENGTH:
                logging.info(f"  - ℹ️ 정보: 본문 추출 실패 또는 내용 부족. 이메일 스니펫을 사용합니다.")
                body = snippet

            # 3. 본문과 스니펫이 모두 비어있으면 건너뜁니다.
            if not body or not body.strip():
                logging.warning(f"본문/스니펫이 모두 비어있어 건너뜁니다: {title_en}")
                continue

            title_ko = translate_text(title_en)
            summary_ko = summarize_and_translate_body(body)
            if title_ko and summary_ko:
                save_paper_markdown(keyword, title_ko, title_en, summary_ko, link, existing_titles)
            else:
                logging.error(f"번역 실패: {title_en}")
            sleep(API_RATE_LIMIT_DELAY)

        # 처리가 끝난 메일은 '읽음'으로 표시하고, seen 목록에 추가
        service.users().messages().modify(userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}).execute()
        seen_ids.add(msg_id)

    save_seen_ids(seen_ids)


if __name__ == "__main__":
    main()