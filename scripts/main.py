import feedparser
import re
import yaml
import csv
from datetime import datetime
from pathlib import Path
import time

import google.generativeai as genai
from . import config
from .summarizer import summarize_article_with_gemini
from .gmail_client import get_links_from_gmail

def get_processed_urls():
    """처리 로그 CSV 파일에서 이미 처리된 URL 목록을 읽어옵니다."""
    if not config.PROCESSED_URLS_LOG.exists():
        return set()
    
    processed_urls = set()
    with open(config.PROCESSED_URLS_LOG, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None) # 헤더 건너뛰기
        for row in reader:
            if row: # 빈 줄 방지
                processed_urls.add(row[0])
    return processed_urls

def add_processed_url(url, status):
    """처리된 URL과 상태를 로그 CSV 파일에 추가합니다."""
    file_exists = config.PROCESSED_URLS_LOG.exists()
    with open(config.PROCESSED_URLS_LOG, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['url', 'status', 'timestamp']) # 파일이 없으면 헤더 추가
        writer.writerow([url, status, datetime.now().isoformat()])

def sanitize_filename(title):
    """파일 이름으로 사용할 수 없는 문자를 제거합니다."""
    return re.sub(r'[\\/*?:"<>|]', "", title).replace(" ", "_")

def get_existing_titles():
    """docs/articles 폴더의 기존 마크다운 파일에서 원본 제목을 추출합니다."""
    existing_titles = set()
    if not config.ARTICLES_PATH.exists():
        config.ARTICLES_PATH.mkdir(parents=True, exist_ok=True)
        return existing_titles
    
    for md_file in config.ARTICLES_PATH.glob("*.md"):
        content = md_file.read_text(encoding='utf-8')
        # **원본 링크:** [ORIGINAL_TITLE](URL) 형식에서 ORIGINAL_TITLE 추출
        match = re.search(r"\*\*원본 링크:\*\* \[(.*?)\]\(", content)
        if match:
            existing_titles.add(match.group(1).strip())
    return existing_titles

def create_markdown_file(article_data):
    """요약된 기사 내용으로 마크다운 파일을 생성합니다."""
    korean_title = article_data['korean_title']
    summary = article_data['summary']
    original_url = article_data['url']
    
    filename = sanitize_filename(korean_title) + ".md"
    filepath = config.ARTICLES_PATH / filename
    
    content = f"""# {korean_title}\n
## 요약
{summary}

---

**원본 링크:** [{article_data['original_title']}]({original_url})
"""
    
    filepath.write_text(content, encoding='utf-8')
    print(f"Created article: {filepath}")

def update_mkdocs_yml():
    """docs/articles 폴더의 md 파일 목록을 읽어 mkdocs.yml을 업데이트합니다."""
    with open(config.MKDOCS_YML_PATH, 'r', encoding='utf-8') as f:
        docs_config = yaml.safe_load(f)

    article_files = sorted(
        [f'articles/{f.name}' for f in config.ARTICLES_PATH.glob('*.md') if f.name != 'index.md'],
        reverse=True
    )
    
    # '관련 기사 모음' 섹션을 찾아 업데이트
    for i, item in enumerate(docs_config['nav']):
        if isinstance(item, dict) and '관련 기사 모음' in item:
            docs_config['nav'][i]['관련 기사 모음'] = ['articles/index.md'] + article_files
            break

    with open(config.MKDOCS_YML_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(docs_config, f, allow_unicode=True, sort_keys=False)
    print("mkdocs.yml updated successfully.")

def process_article_url(url, processed_urls, existing_titles):
    """단일 URL을 처리하여 기사를 생성하고 처리 결과를 반환합니다."""
    if url in processed_urls:
        return False, "skipped_processed"

    # Gmail로 받은 링크는 제목이 없으므로, 요약 후 제목을 얻어 중복 검사
    print(f"  - Processing URL: {url}")
    # Gmail 링크는 원본 제목이 없으므로 임시 제목 사용
    summary_text = summarize_article_with_gemini("(Title from URL)", url)
    
    if summary_text:
        match_title = re.search(r"번역 제목:\s*(.*)", summary_text)
        match_summary = re.search(r"요약:\s*([\s\S]*)", summary_text, re.MULTILINE)

        if match_title and match_summary:
            korean_title = match_title.group(1).strip()
            summary = match_summary.group(1).strip()

            # 요약 후 얻은 제목으로 중복 검사
            if korean_title in existing_titles:
                print(f"  - Skipping (duplicate title found after summarization): {korean_title}")
                add_processed_url(url, "skipped_duplicate_title")
                return False, "skipped_duplicate"

            if len(summary) < 200:
                print(f"  - Skipping: Summary for '{korean_title}' is too short ({len(summary)} chars).")
                add_processed_url(url, "skipped_summary_too_short")
                return False, "skipped_short"

            article = {
                'korean_title': korean_title,
                'summary': summary,
                'url': url,
                'original_title': korean_title # 원본 제목이 없으므로 번역 제목 사용
            }
            create_markdown_file(article)
            add_processed_url(url, "created")
            existing_titles.add(korean_title)
            return True, "created"
        else:
            print(f"  - Skipping: Could not parse summary for '{url}'.")
            add_processed_url(url, "failed_parsing_summary")
    else:
        add_processed_url(url, "failed_summarization")
    return False, "skipped_failed"

def process_rss_feeds(processed_urls, existing_titles):
    """RSS 피드를 순회하며 새 기사를 처리하고, 생성된 기사 수를 반환합니다."""
    new_articles_from_rss = 0
    
    for feed_url in config.RSS_FEEDS:
        print(f"\nFetching feed: {feed_url}")
        new_articles_this_feed_count = 0
        try:
            # feedparser는 약간의 문법 오류가 있어도 최대한 파싱을 시도합니다.
            feed = feedparser.parse(feed_url)
            if feed.bozo:
                print(f"  - Warning: Feed may be malformed. {feed.bozo_exception}")
        except Exception as e:
            print(f"  - Error: Could not parse feed {feed_url}. Reason: {e}")
            continue
        
        for entry in feed.entries:
            if new_articles_this_feed_count >= config.MAX_NEW_ARTICLES_PER_RUN:
                print(f"  - Reached the article limit ({config.MAX_NEW_ARTICLES_PER_RUN}) for this feed.")
                break

            if not hasattr(entry, 'link') or not hasattr(entry, 'title'):
                print(f"  - Skipping entry without link or title in feed {feed_url}")
                continue

            if entry.link in processed_urls:
                continue

            if entry.title in existing_titles:
                print(f"  - Skipping (duplicate title): {entry.title}")
                add_processed_url(entry.link, "skipped_duplicate_title")
                continue

            print(f"  - Processing: {entry.title}")
            summary_text = summarize_article_with_gemini(entry.title, entry.link)
            
            if summary_text:
                match_title = re.search(r"번역 제목:\s*(.*)", summary_text)
                match_summary = re.search(r"요약:\s*([\s\S]*)", summary_text, re.MULTILINE)

                if match_title and match_summary:
                    korean_title = match_title.group(1).strip()
                    summary = match_summary.group(1).strip()

                    if len(summary) < 200:
                        print(f"  - Skipping: Summary for '{entry.title}' is too short ({len(summary)} chars).")
                        add_processed_url(entry.link, "skipped_summary_too_short")
                        continue

                    article = {'korean_title': korean_title, 'summary': summary, 'url': entry.link, 'original_title': entry.title}
                    create_markdown_file(article)
                    add_processed_url(entry.link, "created")
                    existing_titles.add(entry.title)
                    new_articles_this_feed_count += 1
                    new_articles_from_rss += 1
                    time.sleep(1)
                else:
                    add_processed_url(entry.link, "failed_parsing_summary")
            else:
                add_processed_url(entry.link, "failed_summarization")
    return new_articles_from_rss

def run():
    """메인 실행 함수"""
    # API 키 확인 및 설정
    if not config.GOOGLE_API_KEY:
        print("Error: GOOGLE_API_KEY not found in .env file.")
        print("Please create a .env file in the project root and add your Google Gemini API key.")
        return
    
    genai.configure(api_key=config.GOOGLE_API_KEY)

    # 이미 처리된 URL과 기존 기사의 원본 제목을 로드
    processed_urls = get_processed_urls()
    existing_titles = get_existing_titles()
    total_new_articles_this_run = 0

    # 1. Gmail에서 링크 수집 및 처리
    print("--- Checking for new links from Gmail ---")
    emailed_links = get_links_from_gmail()
    if emailed_links:
        for link in emailed_links:
            is_created, _ = process_article_url(link, processed_urls, existing_titles)
            if is_created:
                total_new_articles_this_run += 1
                time.sleep(1) # API 요청 간 딜레이

    # 2. RSS 피드에서 기사 수집 및 처리
    print("\n--- Checking for new articles from RSS Feeds ---")
    rss_article_count = process_rss_feeds(processed_urls, existing_titles)
    total_new_articles_this_run += rss_article_count

    print(f"\nProcessing finished. Total new articles created in this run: {total_new_articles_this_run}")

    update_mkdocs_yml()

if __name__ == "__main__":
    run()
