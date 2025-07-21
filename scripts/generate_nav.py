import os
import yaml
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DOCS_ROOT = PROJECT_ROOT / "docs"

def shorten_title(title, max_length=60):
    """긴 제목을 자르고, 개행 및 특수문자를 제거합니다."""
    title = title.strip().replace('\n', ' ').replace('\r', '')
    title = re.sub(r'\s+', ' ', title)
    title = re.sub(r'[\"\'`]', '', title)
    if len(title) > max_length:
        title = title[:max_length].rstrip() + "..."
    return title

def group_files_by_date(file_paths):
    """파일 경로 목록을 수정일을 기준으로 연도와 월별로 그룹화합니다."""
    grouped = {}
    for file_path in file_paths:
        try:
            mtime = os.path.getmtime(file_path)
            dt = datetime.fromtimestamp(mtime)
            year = str(dt.year)
            month = f"{dt.month:02d}"

            if year not in grouped:
                grouped[year] = {}
            if month not in grouped[year]:
                grouped[year][month] = []

            title = shorten_title(file_path.stem)
            rel_path = os.path.relpath(file_path, DOCS_ROOT)
            grouped[year][month].append({title: str(rel_path).replace("\\", "/")})
        except Exception as e:
            print(f"경고: 파일 처리 중 오류 발생 {file_path}: {e}")
    return grouped

def format_grouped_nav(grouped_data):
    """그룹화된 데이터를 mkdocs 내비게이션 형식으로 변환합니다."""
    nav = []
    for year in sorted(grouped_data.keys(), reverse=True):
        year_content = []
        for month in sorted(grouped_data[year].keys(), reverse=True):
            month_files = grouped_data[year][month]
            year_content.append({f"{month}월": month_files})
        nav.append({f"{year}년": year_content})
    return nav

def collect_markdown_files():
    """docs 폴더를 스캔하여 내비게이션 구조를 생성합니다."""
    sections = {}

    # 1. '기사' 섹션 처리 (docs/articles)
    articles_path = DOCS_ROOT / "articles"
    if articles_path.exists() and articles_path.is_dir():
        md_file_paths = [
            articles_path / f
            for f in sorted(os.listdir(articles_path), reverse=True)
            if f.endswith(".md") and f != "index.md"
        ]
        if md_file_paths:
            grouped_articles = group_files_by_date(md_file_paths)
            sections['기사'] = format_grouped_nav(grouped_articles)

    # 2. '키워드' 섹션 처리 (docs/keywords)
    keywords_path = DOCS_ROOT / "keywords"
    if keywords_path.exists() and keywords_path.is_dir():
        keyword_entries = {}
        for keyword in sorted(os.listdir(keywords_path)):
            keyword_dir = keywords_path / keyword
            if not keyword_dir.is_dir():
                continue

            md_file_paths = [
                keyword_dir / f
                for f in sorted(os.listdir(keyword_dir), reverse=True)
                if f.endswith(".md")
            ]

            if md_file_paths:
                grouped_files = group_files_by_date(md_file_paths)
                keyword_entries[keyword] = format_grouped_nav(grouped_files)

        if keyword_entries:
            sections['키워드'] = [{kw: keyword_entries[kw]} for kw in sorted(keyword_entries.keys())]

    return sections

def write_mkdocs_yml(sections):
    """수집된 파일 목록으로 mkdocs.yml 파일을 생성합니다."""
    config = {
        "site_name": "Singularity Daily",
        "site_url": "https://leejunyoung920.github.io/SingularityDaily/",
        "theme": {
            "name": "material",
            "language": "ko",
            "features": [
                "navigation.instant",
                "navigation.sections",
                "navigation.top",
                "content.code.copy",
                "toc.integrate",
            ]
        },
        "use_directory_urls": False,
        "markdown_extensions": [
            "admonition",
            {"toc": {"permalink": True}},
            "footnotes",
            "meta",
        ],
        "extra_css": ["stylesheets/extra.css"],
        "plugins": ["search", "awesome-pages"],
        "nav": [{'홈': 'index.md'}] # '홈'은 명시적으로 유지하여 명확성을 높입니다.
    }

    # '홈' 링크를 맨 앞에 추가합니다. 사이트 제목과 별개로 명확한 '홈' 버튼을 제공합니다.
    nav_structure = [{'홈': 'index.md'}]

    if '기사' in sections:
        nav_structure.append({'기사': sections['기사']})

    if '키워드' in sections:
        nav_structure.append({'키워드': sections['키워드']})

    config['nav'] = nav_structure

    output_path = PROJECT_ROOT / "mkdocs.yml"
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

    print(f"✅ '{output_path}' 파일이 성공적으로 생성/업데이트되었습니다.")

def main():
    print("🔍 'docs' 폴더를 스캔하여 내비게이션 구조를 생성합니다...")
    sections = collect_markdown_files()
    write_mkdocs_yml(sections)

if __name__ == "__main__":
    main()