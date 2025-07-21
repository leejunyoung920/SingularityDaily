# collect_from_gmail.py (RSS 방식으로 개선)
import os
import feedparser
import logging
from datetime import datetime
from .common_utils import (
from concurrent.futures import ThreadPoolExecutor, as_completed
    clean_google_url,
    strip_html_tags,
    fetch_article_body,
    safe_filename,
    is_duplicate_md,
    translate_text,
    summarize_and_translate_body,
    initialize_gemini,
)

# --- Constants ---
RSS_FEEDS = {
    "AGI": "https://www.google.co.kr/alerts/feeds/14276058857012603250/2707178187233880419",
    "AI drug discovery": "https://www.google.co.kr/alerts/feeds/14276058857012603250/2271409061188943971",
    "Anti-aging therapeutics": "https://www.google.co.kr/alerts/feeds/14276058857012603250/1502131717617198121",
    "Cellular reprograming": "https://www.google.co.kr/alerts/feeds/14276058857012603250/2481308844339361893",
    "Longevity research": "https://www.google.co.kr/alerts/feeds/14276058857012603250/9706346182581700369",
    "nanobot": "https://www.google.co.kr/alerts/feeds/14276058857012603250/2271409061188945116",
    "NMN": "https://www.google.co.kr/alerts/feeds/14276058857012603250/1502131717617199599",
    "Rapamycin": "https://www.google.co.kr/alerts/feeds/14276058857012603250/2707178187233881309",
    "Senolytics": "https://www.google.co.kr/alerts/feeds/14276058857012603250/1502131717617200498",
    "Telomere extension": "https://www.google.co.kr/alerts/feeds/14276058857012603250/9135595537824711247",
    "Humanoid Robot": "https://www.google.co.kr/alerts/feeds/14276058857012603250/1273794955109409208"
}
MIN_BODY_LENGTH = 300
MAX_ENTRIES_PER_FEED = 20
API_RATE_LIMIT_DELAY = 1.5  # seconds
OUTPUT_DIR = os.path.join("docs", "keywords")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

def save_markdown(keyword, title_ko, title_en, summary_ko, url):
    """마크다운 파일을 저장하고, 중복을 확인합니다."""
    try:
        safe_title = safe_filename(title_ko)
        folder = os.path.join(OUTPUT_DIR, keyword)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{safe_title}.md")

        if is_duplicate_md(path, title_en):
            logging.info(f"🚫 중복 기사: {title_en}")
            return False

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {title_ko}\n\n")
            f.write(f"**원제목:** {title_en}\n\n")
            f.write(f"**요약:** {summary_ko}\n\n")
            f.write(f"[원문 링크]({url})\n")
        logging.info(f"✅ 저장 완료: {path}")
        return True
    except Exception as e:
        logging.error(f"파일 저장 중 오류 발생 ({title_en}): {e}")
        return False

def process_entry(entry, keyword):
    """개별 RSS 항목을 처리합니다."""
    try:
        raw_title = entry.get("title", "")
        raw_link = entry.get("link", "")
        link = clean_google_url(raw_link)
        title_en = strip_html_tags(raw_title)

        if not title_en or not link:
            logging.warning("제목 또는 링크가 없는 항목을 건너뜁니다.")
            return

        # 본문 먼저 추출 후 필터
        body = fetch_article_body(link)

        # 본문 추출 실패 시 처리
        if not body:
            logging.info(f"⚠️ 본문 추출 실패 — 저장하지 않음: {title_en}")
            return
        # 본문이 너무 짧을 경우 처리
        if len(body.strip()) < MIN_BODY_LENGTH:
            logging.info(f"⚠️ 본문 부족({len(body.strip())}자) — 저장하지 않음: {title_en}")
            return

        # 번역 수행 (비용 발생)
        title_ko = translate_text(title_en)
        summary_ko = summarize_and_translate_body(body)
        
        if not title_ko or not summary_ko:
            logging.error(f"번역 실패: {title_en}")
            return

        save_markdown(keyword, title_ko, title_en, summary_ko, link)

    except Exception as e:
        logging.error(f"항목 처리 중 오류 발생 ({entry.get('title', 'N/A')}): {e}")

def main():
    """모든 RSS 피드를 순회하며 기사를 수집하고 저장합니다."""
    try:
        initialize_gemini()
    except (ValueError, RuntimeError) as e:
        logging.error(f"스크립트 실행 중단: {e}")
        # CI/CD 환경에서 실패를 명확히 알리기 위해 0이 아닌 코드로 종료
        exit(1)

    all_tasks = []
    for keyword, feed_url in RSS_FEEDS.items():
        logging.info(f"========== 🌐 RSS 피드 스캔 중: {keyword} ==========")
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo:
                # bozo가 1이면 피드 파싱에 문제가 있을 수 있음을 의미
                logging.warning(f"'{keyword}' 피드 파싱 문제: {feed.bozo_exception}")

            entries = feed.entries[:MAX_ENTRIES_PER_FEED]
            for entry in entries:
                all_tasks.append((entry, keyword))
        except Exception as e:
            logging.error(f"'{keyword}' 피드 처리 중 오류 발생: {e}")

    if not all_tasks:
        logging.info("처리할 새 RSS 항목이 없습니다.")
        return

    logging.info(f"총 {len(all_tasks)}개의 RSS 항목을 병렬로 처리합니다...")

    # max_workers를 5로 설정하여 동시에 5개의 항목을 처리합니다.
    # 이는 API 속도 제한을 어느 정도 제어하는 효과도 있습니다.
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_task = {executor.submit(process_entry, task[0], task[1]): task for task in all_tasks}
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                future.result()  # 작업 중 발생한 예외가 있다면 여기서 다시 발생시킵니다.
            except Exception as exc:
                logging.error(f"항목 처리 중 예외 발생 ({task[0].get('title', 'N/A')}): {exc}")

    logging.info("========== RSS 수집 종료 ==========\n")

if __name__ == "__main__":
    main()