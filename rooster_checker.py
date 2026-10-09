import urllib.request
import smtplib
import os
import json
from datetime import datetime, timezone
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

ICAL_URL = os.environ.get("ICAL_URL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")
SENDER_EMAIL = RECEIVER_EMAIL

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
STATE_FILE = "state.json"
AMS = ZoneInfo("Europe/Amsterdam")
DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def haal_rooster_op():
    try:
        req = urllib.request.Request(ICAL_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8")
    except Exception as e:
        print(f"Fout bij ophalen rooster: {e}")
        return None


def ontsnap(tekst):
    return (tekst.replace("\\n", " ").replace("\\N", " ")
                 .replace("\\,", ",").replace("\\;", ";").strip())


def parse_tijd(regel):
    waarde = regel.split(":", 1)[1].strip()
    try:
        if waarde.endswith("Z"):
            dt = datetime.strptime(waarde, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return dt.astimezone(AMS)
        if "T" in waarde:
            return datetime.strptime(waarde, "%Y%m%dT%H%M%S").replace(tzinfo=AMS)
        return datetime.strptime(waarde, "%Y%m%d").replace(tzinfo=AMS)
    except ValueError:
        return None


def is_vervallen(les):
    summary = les.get("summary", "").lower()
    desc = les.get("description", "").lower()
    return (
        summary.startswith("[x]")
        or "vervalt" in desc
        or "vervallen" in desc
        or les.get("status", "").upper() == "CANCELLED"
    )


def parse_uitval(data):
    data = data.replace("\r\n ", "").replace("\r\n\t", "").replace("\n ", "").replace("\n\t", "")
    nu = datetime.now(AMS)
    uitval = []
    les = {}

    for regel in data.splitlines():
        regel = regel.strip()
        if regel.startswith("BEGIN:VEVENT"):
            les = {}
        elif regel.startswith("SUMMARY"):
            les["summary"] = ontsnap(regel.split(":", 1)[1])
        elif regel.startswith("DESCRIPTION"):
            les["description"] = ontsnap(regel.split(":", 1)[1])
        elif regel.startswith("STATUS"):
            les["status"] = regel.split(":", 1)[1].strip()
        elif regel.startswith("DTSTART"):
            les["start"] = parse_tijd(regel)
        elif regel.startswith("END:VEVENT"):
            start = les.get("start")
            if not start or not is_vervallen(les):
                continue
            if start.date() < nu.date():
                continue
            naam = les.get("summary", "Onbekende les").removeprefix("[x]").strip()
            tijd = f"{DAGEN[start.weekday()]} {start.strftime('%d-%m %H:%M')}"
            uitval.append(f"{tijd} - {naam}")

    return sorted(set(uitval))


def laad_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def sla_state_op(uitval):
    with open(STATE_FILE, "w") as f:
        json.dump(uitval, f, indent=2)


def stuur_mail(lessen):
    inhoud = "Er is nieuwe uitval in je Zermelo-rooster:\n\n" + "\n".join(f"• {l}" for l in lessen)
    msg = MIMEText(inhoud)
    msg["Subject"] = "ZERMELO: Lesuitval gedetecteerd!"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, [RECEIVER_EMAIL], msg.as_string())
    print("E-mail verzonden!")


if __name__ == "__main__":
    data = haal_rooster_op()
    if data:
        uitval = parse_uitval(data)
        print(f"Huidige uitval: {uitval}")
        oud = laad_state()
        nieuw = [u for u in uitval if u not in oud]

        if nieuw:
            try:
                stuur_mail(nieuw)
                sla_state_op(uitval)
            except Exception as e:
                print(f"Fout bij verzenden mail: {e}")
        elif uitval != oud:
            sla_state_op(uitval)
            print("State bijgewerkt, geen nieuwe uitval.")
        else:
            print("Geen nieuwe uitval.")
