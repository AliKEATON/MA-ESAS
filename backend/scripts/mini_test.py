import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawlers.jd_crawler import JDCrawler

url = "https://item.jd.com/100197744867.html"

crawler = JDCrawler(headless=False)

try:
    comments = crawler.crawl(url, max_pages=2)
    print("COUNT:", len(comments))
    print("SAMPLE:", comments[:5])
finally:
    crawler.close()
