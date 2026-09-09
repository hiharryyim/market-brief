#!/usr/bin/env python3
"""
MarketDashboard Email Sender
Sends HTML email via Gmail SMTP using App Password.

Usage:
    python3 send_email.py --subject "Market Brief" --html "<h1>Hello</h1>" [--to user@example.com]
    python3 send_email.py --subject "Market Brief" --html-file /path/to/brief.html
    echo "<h1>Hello</h1>" | python3 send_email.py --subject "Market Brief" --stdin

Environment variables:
    GMAIL_USER       - Gmail address (default: hiharryyim@gmail.com)
    GMAIL_APP_PASS   - Google App Password (required)
    BRIEF_RECIPIENTS - Comma-separated recipient emails (default: GMAIL_USER)
"""

import smtplib
import os
import sys
import argparse
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit


CONFIG_PATH = os.path.expanduser("~/Desktop/MarketDashboard/config/email.conf")
RECIPIENTS_PATH = os.path.expanduser("~/Desktop/MarketDashboard/config/recipients.txt")
RECIPIENTS_TEST_PATH = os.path.expanduser("~/Desktop/MarketDashboard/config/recipients_test.txt")
NEWS_HISTORY_PATH = os.path.expanduser("~/Desktop/MarketDashboard/cache/sent_news_history.json")
EXTERNAL_NEWS_HISTORY_PATH = os.path.expanduser(
    "~/Desktop/MarketDashboard/cache/sent_external_news_history.json"
)


def load_config() -> dict:
    """Load email config from file, falling back to env vars."""
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip()
    return config


def load_recipients(test_mode: bool = False) -> list[str]:
    """Load recipient list. test_mode=True 用 recipients_test.txt（仅你自己的邮箱）"""
    path = RECIPIENTS_TEST_PATH if test_mode else RECIPIENTS_PATH
    recipients = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "@" in line:
                    if "#" in line:
                        line = line.split("#", 1)[0].strip()
                    if line:
                        recipients.append(line)
    return recipients


def append_history_entries(path: str, entries: list[str], max_days: int = 7):
    """Append entries to a dated rolling history file."""
    if not entries:
        return
    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')

    history = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                history = json.load(f)
        except:
            history = {}

    existing = set(history.get(today, []))
    existing.update(entries)
    history[today] = sorted(existing)

    # 只保留最近 max_days 天
    cutoff = (datetime.now() - timedelta(days=max_days)).strftime('%Y-%m-%d')
    history = {k: v for k, v in history.items() if k >= cutoff}

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def append_news_history(news_ids: list[str], max_days: int = 7):
    """Persist Futu news IDs for fetch_data.py deduplication."""
    append_history_entries(NEWS_HISTORY_PATH, news_ids, max_days=max_days)


def canonicalize_external_url(url: str) -> str:
    """Remove tracking query strings and fragments before external-news dedupe."""
    if not isinstance(url, str):
        return ""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))


def append_external_news_history(urls: list[str], max_days: int = 7):
    """Persist canonical subscriber-media URLs for cross-routine deduplication."""
    canonical_urls = sorted({canonicalize_external_url(url) for url in urls})
    canonical_urls = [url for url in canonical_urls if url]
    append_history_entries(
        EXTERNAL_NEWS_HISTORY_PATH,
        canonical_urls,
        max_days=max_days,
    )


def send_email(subject: str, html_body: str, recipients: list[str] = None, test_mode: bool = False):
    """Send HTML email via Gmail SMTP. test_mode=True 用测试收件人列表。"""

    config = load_config()
    gmail_user = os.environ.get("GMAIL_USER") or config.get("GMAIL_USER", "hiharryyim@gmail.com")
    gmail_pass = os.environ.get("GMAIL_APP_PASS") or config.get("GMAIL_APP_PASS", "")

    if not gmail_pass:
        print("ERROR: GMAIL_APP_PASS not found in env or config file.")
        print(f"Set it in {CONFIG_PATH} or as an environment variable.")
        sys.exit(1)

    if recipients is None:
        # test 模式优先用 recipients_test.txt
        recipients = load_recipients(test_mode=test_mode)
        if not recipients:
            # 降级到环境变量或 email.conf
            env_recipients = os.environ.get("BRIEF_RECIPIENTS") or config.get("BRIEF_RECIPIENTS", gmail_user)
            recipients = [r.strip() for r in env_recipients.split(",")]

    # Build email — 使用 BCC 密送，收件人互不可见
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = gmail_user  # To 只显示发件人自己
    # recipients 通过 sendmail 的 envelope 发送，不写入 header，实现密送

    # Plain text fallback (strip HTML tags roughly)
    import re
    plain_text = re.sub(r'<[^>]+>', '', html_body)
    plain_text = re.sub(r'\n\s*\n', '\n\n', plain_text)

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Send
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, recipients, msg.as_string())
        print(f"OK: Email sent to {', '.join(recipients)}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("ERROR: Gmail authentication failed. Check GMAIL_APP_PASS.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


def markdown_to_html(md_text: str) -> str:
    """Convert markdown to mobile-first responsive HTML email."""
    import re

    # --- Pre-process markdown ---

    # Convert markdown elements BEFORE wrapping in HTML
    content = md_text

    # Headers
    content = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', content, flags=re.MULTILINE)
    content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', content, flags=re.MULTILINE)
    content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', content, flags=re.MULTILINE)
    content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', content, flags=re.MULTILINE)

    # Bold
    content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)

    # Links - make them tappable with padding
    content = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" style="color:#1565c0;text-decoration:underline;">\1</a>',
        content
    )

    # Blockquotes (> lines)
    content = re.sub(
        r'^> (.+)$',
        r'<blockquote>\1</blockquote>',
        content, flags=re.MULTILINE
    )

    # Horizontal rules
    content = re.sub(r'^---+$', r'<hr>', content, flags=re.MULTILINE)

    # Bullet points + news source detection
    lines = content.split('\n')
    result_lines = []
    in_list = False
    # 匹配 [富途|Bloomberg|Reuters|WSJ|FT|NYT|...] | MM-DD 格式的来源行
    news_source_re = re.compile(r'<a\s+href="[^"]*"[^>]*>(富途|Bloomberg|Reuters|WSJ|FT|NYT|Washington Post|CNBC|The Economist|Barron\'s|SCMP|Financial Times|Wall Street Journal|The New York Times)</a>\s*\|\s*\d{2}-\d{2}')

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('- '):
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            item_content = stripped[2:]
            result_lines.append(f'<li>{item_content}</li>')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            # Detect news source lines (e.g. "富途 | 05-04") and wrap with separator
            if news_source_re.search(stripped):
                result_lines.append(f'<div class="news-source">{stripped}</div>')
            elif stripped and not stripped.startswith('<') and not stripped.startswith('|'):
                result_lines.append(f'<p>{stripped}</p>')
            elif stripped:
                result_lines.append(stripped)
            else:
                result_lines.append('')
    if in_list:
        result_lines.append('</ul>')

    content = '\n'.join(result_lines)

    # Highlight percentages with color. Prefer signed values, but also support
    # natural Chinese phrasing such as "涨 1.5%" emitted by generated briefs.
    content = re.sub(r'(\+\d+(?:\.\d+)?%)', r'<span class="pos">\1</span>', content)
    content = re.sub(r'(-\d+(?:\.\d+)?%)', r'<span class="neg">\1</span>', content)
    content = re.sub(
        r'((?:上涨|涨|下跌|跌)(?:幅)?\s*\d+(?:\.\d+)?%)',
        lambda match: (
            f'<span class="neg">{match.group(1)}</span>'
            if match.group(1).startswith(('下跌', '跌'))
            else f'<span class="pos">{match.group(1)}</span>'
        ),
        content,
    )

    # --- Wrap in responsive HTML ---
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  /* Reset */
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    max-width: 680px;
    margin: 0 auto;
    padding: 16px;
    color: #1a1a1a;
    line-height: 1.75;
    font-size: 15px;
    background: #ffffff;
  }}

  /* Headers */
  h1 {{
    font-size: 22px;
    color: #0d47a1;
    border-bottom: 3px solid #0d47a1;
    padding-bottom: 10px;
    margin: 8px 0 16px 0;
  }}
  h2 {{
    font-size: 19px;
    color: #0d47a1;
    border-bottom: 2px solid #e3f2fd;
    padding-bottom: 8px;
    margin: 28px 0 12px 0;
  }}
  h3 {{
    font-size: 17px;
    color: #1565c0;
    margin: 20px 0 8px 0;
    padding-left: 10px;
    border-left: 3px solid #1565c0;
  }}
  h4 {{
    font-size: 15px;
    color: #1976d2;
    margin: 16px 0 6px 0;
  }}

  /* Paragraphs - KEY for mobile readability */
  p {{
    margin: 10px 0;
    line-height: 1.8;
  }}

  /* Bold - subtle, not blue */
  strong {{ color: #1a1a1a; font-weight: 700; }}

  /* Links - must be obvious and tappable */
  a {{
    color: #1565c0;
    text-decoration: underline;
    text-underline-offset: 2px;
  }}

  /* Percentage highlights — 涨红跌绿（中国市场惯例） */
  .pos {{ color: #c62828; font-weight: 700; }}
  .neg {{ color: #2e7d32; font-weight: 700; }}

  /* Lists */
  ul {{
    margin: 8px 0;
    padding-left: 0;
    list-style: none;
  }}
  li {{
    padding: 8px 12px;
    margin: 6px 0;
    background: #f8f9fa;
    border-left: 3px solid #e0e0e0;
    border-radius: 0 6px 6px 0;
    line-height: 1.7;
    font-size: 14px;
  }}

  /* Blockquote - for time/context info */
  blockquote {{
    border-left: 3px solid #90caf9;
    margin: 12px 0;
    padding: 10px 14px;
    background: #e3f2fd;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
    color: #424242;
  }}

  /* Horizontal rule */
  hr {{
    border: none;
    border-top: 1px solid #e0e0e0;
    margin: 20px 0;
  }}

  /* Tables - responsive */
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 13px;
    overflow-x: auto;
    display: block;
  }}
  th, td {{
    border: 1px solid #e0e0e0;
    padding: 6px 10px;
    text-align: left;
    white-space: nowrap;
  }}
  th {{ background: #f5f5f5; font-weight: 600; }}

  /* Signature */
  .sig {{
    margin-top: 36px;
    padding-top: 16px;
    border-top: 2px solid #0d47a1;
    text-align: center;
  }}
  .sig-name {{ font-weight: 700; color: #0d47a1; font-size: 16px; }}
  .sig-tag {{ color: #757575; font-style: italic; font-size: 13px; margin-top: 2px; }}
  .sig-data {{ font-size: 11px; color: #9e9e9e; margin-top: 6px; }}

  /* News source link — clear separator between news items */
  .news-source {{
    font-size: 12px;
    color: #9e9e9e;
    margin: 4px 0 20px 0;
    padding-bottom: 16px;
    border-bottom: 1px dashed #e0e0e0;
  }}

  /* Disclaimer */
  .disclaimer {{
    margin-top: 20px;
    font-size: 11px;
    color: #9e9e9e;
    text-align: center;
    font-style: italic;
  }}

  /* Mobile tweaks */
  @media (max-width: 480px) {{
    body {{ padding: 12px; font-size: 15px; }}
    h1 {{ font-size: 20px; }}
    h2 {{ font-size: 17px; }}
    h3 {{ font-size: 16px; }}
    li {{ padding: 8px 10px; font-size: 14px; }}
    table {{ font-size: 12px; }}
    th, td {{ padding: 5px 8px; }}
  }}
</style>
</head>
<body>

{content}

<div class="sig">
  <div class="sig-name">哈利每日 Market Brief</div>
  <div class="sig-tag">Daily market intelligence, powered by AI</div>
  <div class="sig-data">Data: Futu &middot; LSEG &middot; yfinance &middot; Futu News</div>
</div>

</body>
</html>"""

    return html


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Market Brief email")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--html", help="HTML body as string")
    parser.add_argument("--html-file", help="Path to HTML file")
    parser.add_argument("--markdown", help="Markdown text to convert to HTML")
    parser.add_argument("--markdown-file", help="Path to markdown file to convert")
    parser.add_argument("--stdin", action="store_true", help="Read markdown from stdin")
    parser.add_argument("--to", help="Comma-separated recipient emails (overrides BRIEF_RECIPIENTS)")
    parser.add_argument("--test", action="store_true", help="使用 recipients_test.txt（仅自己的邮箱）")
    parser.add_argument("--news-ids-file", help="JSON 文件路径，包含本次使用的 news_id 列表（用于历史去重）")
    parser.add_argument(
        "--external-urls-file",
        help="JSON 文件路径，包含本次使用的外媒文章 URL（用于跨 routine 历史去重）",
    )

    args = parser.parse_args()

    # Determine HTML body
    if args.html:
        body = args.html
    elif args.html_file:
        with open(args.html_file) as f:
            body = f.read()
    elif args.markdown:
        body = markdown_to_html(args.markdown)
    elif args.markdown_file:
        with open(args.markdown_file) as f:
            body = markdown_to_html(f.read())
    elif args.stdin:
        body = markdown_to_html(sys.stdin.read())
    else:
        print("ERROR: Provide --html, --html-file, --markdown, --markdown-file, or --stdin")
        sys.exit(1)

    # Determine recipients
    recipients = None
    if args.to:
        recipients = [r.strip() for r in args.to.split(",")]

    send_email(args.subject, body, recipients, test_mode=args.test)

    # 发送成功后，把本次使用的 news_id 写入历史 cache（供 fetch_data.py 去重）
    if args.news_ids_file and os.path.exists(args.news_ids_file):
        try:
            with open(args.news_ids_file) as f:
                ids = json.load(f)
            if isinstance(ids, list) and ids:
                append_news_history(ids)
                print(f"OK: {len(ids)} news_ids appended to history cache")
        except Exception as e:
            print(f"WARN: Failed to update news history: {e}")

    # 发送成功后记录订阅外媒 URL；查询参数会被去掉，避免同文不同 tracking 参数漏去重。
    if args.external_urls_file and os.path.exists(args.external_urls_file):
        try:
            with open(args.external_urls_file) as f:
                urls = json.load(f)
            if isinstance(urls, list) and urls:
                append_external_news_history(urls)
                print(f"OK: {len(urls)} external URLs appended to history cache")
        except Exception as e:
            print(f"WARN: Failed to update external news history: {e}")
