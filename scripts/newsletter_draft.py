"""Create a Brevo campaign draft for one published edition. Never sends email."""
import argparse
import html
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def payload(publication, date):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("Use YYYY-MM-DD")
    edition = ROOT / "CapitalSignal" / publication / date / "index.html"
    source = edition.read_text()
    if re.search(r"sample edition|founding sample|historical morning-format test", source, re.I):
        raise ValueError("Edition is labeled as a sample/test; review before email distribution")
    title = {"daily": "Daily Market Brief", "weekly": "Week in Review"}[publication]
    list_id = int(os.environ["BREVO_" + publication.upper() + "_LIST_ID"])
    address = os.environ["NEWSLETTER_POSTAL_ADDRESS"].strip()
    sender = os.environ["NEWSLETTER_SENDER_EMAIL"].strip()
    if not address or "@" not in sender or list_id <= 0:
        raise ValueError("Configure sender, postal address, and a valid list ID")
    url = f"https://ainvestmentbank.ai/CapitalSignal/{publication}/{date}/"
    body = f"""<!doctype html><html><body style="font-family:Arial;color:#172b4d">
<div style="background:#102747;color:white;padding:24px">AIBANK<br>CAPITAL SIGNAL INTELLIGENCE</div>
<h1>{title}</h1><p>{date}</p><p>Your latest edition is ready.</p>
<p><a href="{url}">Read the {title}</a></p>
<hr><p>Capital Signal Intelligence · {html.escape(address)}</p>
<p>You received this because you subscribed to {title}.</p>
<p><a href="{{{{ unsubscribe }}}}">Unsubscribe</a></p></body></html>"""
    return {"name": f"CSI {publication} {date}", "subject": f"{title} | {date}",
            "sender": {"name": "Capital Signal Intelligence", "email": sender},
            "type": "classic", "htmlContent": body, "recipients": {"listIds": [list_id]}}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("publication", choices=["daily", "weekly"])
    p.add_argument("date")
    p.add_argument("--create-draft", action="store_true")
    args = p.parse_args()
    data = payload(args.publication, args.date)
    if not args.create_draft:
        print(json.dumps(data, indent=2))
        return
    # No scheduledAt and no sendNow call: first editions require review in Brevo.
    request = urllib.request.Request("https://api.brevo.com/v3/emailCampaigns",
        data=json.dumps(data).encode(), method="POST",
        headers={"api-key": os.environ["BREVO_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    print("Created campaign draft:", result["id"])

if __name__ == "__main__":
    main()
