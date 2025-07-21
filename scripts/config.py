import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# 프로젝트 루트 디렉토리 설정
PROJECT_ROOT = Path(__file__).parent.parent

# API 키
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# 경로 설정
DOCS_PATH = PROJECT_ROOT / "docs"
ARTICLES_PATH = DOCS_PATH / "articles"
TOPICS_PATH = DOCS_PATH / "topics" # 'topic' -> 'topics'로 변경하여 복수형으로 통일
MKDOCS_YML_PATH = PROJECT_ROOT / "mkdocs.yml"

# Gmail 처리 관련 설정
GMAIL_ALERTS_QUERY = "(from:googlealerts-noreply@google.com OR from:scholaralerts-noreply@google.com) is:unread"


# 콘텐츠 소스
RSS_FEEDS = [    "https://www.technologyreview.com/feed/",
    "https://singularityhub.com/feed/",
    "https://longevity.technology/feed/",
    "https://www.kurzweilai.net/news/feed",
    "https://spectrum.ieee.org/rss/robotics",
    "https://www.fightaging.org/rss.xml",
    "https://www.futuretimeline.net/blog/rss.xml",
    "https://nautil.us/feed/",
    "https://www.neurotechreports.com/rss.xml",
    "https://a16z.com/feed/",
    "https://the-decoder.com/feed/",
]

# 스크립트 실행 설정
MAX_NEW_ARTICLES_PER_RUN = 10 # 한 번 실행 시 처리할 최대 새 기사 수

# 로그 파일
PROCESSED_URLS_LOG = PROJECT_ROOT / "processed_urls.csv"
GMAIL_PROCESSED_URLS_LOG = PROJECT_ROOT / "gmail_processed_urls.log"

# Google Alerts RSS 피드 (토픽별 수집용)
GOOGLE_ALERTS_RSS_FEEDS = {
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