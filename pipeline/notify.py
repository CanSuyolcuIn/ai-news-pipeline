"""
Mail gönderme scripti.
bulletin.md'yi okur, Gmail SMTP ile gönderir.

Kullanim:
    python notify.py

Gerekli env:
    GMAIL_USER          (ornek: can@gmail.com)
    GMAIL_APP_PASSWORD  (Google App Password)
"""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


def load_bulletin() -> tuple[str, str]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, date_str, "bulletin.md")
    with open(path, encoding="utf-8") as f:
        return f.read(), date_str


def md_to_html(md: str) -> str:
    """Minimal Markdown → HTML dönüşümü (harici kütüphane gerektirmez)."""
    import re
    lines = md.splitlines()
    html_lines = []
    for line in lines:
        # Başlıklar
        if line.startswith("### "):
            line = re.sub(r"^### \[(.+?)\]\((.+?)\)", r'<h3><a href="\2">\1</a></h3>', line)
            if not line.startswith("<h3"):
                line = f"<h3>{line[4:]}</h3>"
        elif line.startswith("## "):
            line = f"<h2>{line[3:]}</h2>"
        elif line.startswith("# "):
            line = f"<h1>{line[2:]}</h1>"
        # İtalik
        elif line.startswith("*") and line.endswith("*"):
            line = f"<p><em>{line[1:-1]}</em></p>"
        # Yatay çizgi
        elif line.strip() == "---":
            line = "<hr>"
        # Boş satır
        elif line.strip() == "":
            line = ""
        # Normal paragraf
        else:
            line = f"<p>{line}</p>"
        html_lines.append(line)

    body = "\n".join(html_lines)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; max-width: 700px;
         margin: 40px auto; color: #222; line-height: 1.6; }}
  h1 {{ color: #111; border-bottom: 2px solid #eee; padding-bottom: 8px; }}
  h2 {{ color: #333; margin-top: 32px; }}
  h3 {{ margin-bottom: 2px; }}
  h3 a {{ color: #1a73e8; text-decoration: none; }}
  h3 a:hover {{ text-decoration: underline; }}
  em {{ color: #666; font-size: 0.9em; }}
  hr {{ border: none; border-top: 1px solid #eee; margin: 24px 0; }}
  p {{ margin: 4px 0 12px; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def send_mail(subject: str, html: str, plain: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    recipients = [GMAIL_USER, "can.suyolcu@inteley.com.tr"]

    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, recipients, msg.as_string())


def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("GMAIL_USER veya GMAIL_APP_PASSWORD eksik. .env dosyasini kontrol et.")
        return

    print("\n=== Mail gonderimi basladi ===\n")

    bulletin, date_str = load_bulletin()
    subject = f"AI Haber Bülteni — {date_str}"

    html = md_to_html(bulletin)
    send_mail(subject, html, bulletin)

    print(f"  -> Mail gönderildi: {GMAIL_USER}, can.suyolcu@inteley.com.tr")
    print(f"  Konu: {subject}")


if __name__ == "__main__":
    main()
