"""
Scenario seeder for test servers.

Pre-populates email, calendar, and CRM test servers with realistic
SalesAE workday data.

Usage:
    python -m tests.servers.seed_scenario [--email-url ...] [--calendar-url ...] [--crm-url ...]

Also importable for use in tests:
    >>> from tests.servers.seed_scenario import seed_all
    >>> await seed_all()
"""

import argparse
import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

DEFAULT_EMAIL_URL = "http://localhost:9100"
DEFAULT_CALENDAR_URL = "http://localhost:9101"
DEFAULT_CRM_URL = "http://localhost:9102"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hours_from_now(hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


async def seed_email(base_url: str = DEFAULT_EMAIL_URL) -> None:
    """Seed test email server with realistic emails."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        # Reset first
        await client.post("/reset")

        emails = [
            {
                "id": "email-001",
                "from_addr": "sarah.chen@acmecorp.com",
                "to_addrs": ["jordan@company.com"],
                "subject": "Urgent: Need demo for our team ASAP",
                "body": (
                    "Hi Jordan,\n\n"
                    "We're evaluating solutions this week and need to see a demo "
                    "by Thursday. Our team of 50 engineers is looking for a platform "
                    "like yours. Can you set something up?\n\n"
                    "Budget is approved for up to $200k/year.\n\n"
                    "Best,\nSarah Chen\nVP Engineering, AcmeCorp"
                ),
                "timestamp": _now_iso(),
                "is_read": False,
                "labels": ["urgent", "demo-request"],
            },
            {
                "id": "email-002",
                "from_addr": "mike.johnson@techstart.io",
                "to_addrs": ["jordan@company.com"],
                "subject": "Re: Follow-up on our conversation",
                "body": (
                    "Jordan,\n\n"
                    "Thanks for the call last week. I've discussed with my team and "
                    "we're interested in moving forward. Can you send over pricing "
                    "for the enterprise tier?\n\n"
                    "Mike"
                ),
                "timestamp": _hours_from_now(-2),
                "is_read": False,
            },
            {
                "id": "email-003",
                "from_addr": "calendar@company.com",
                "to_addrs": ["jordan@company.com"],
                "subject": "Meeting Request: Pipeline Review with Sales Lead",
                "body": (
                    "You have been invited to a pipeline review meeting.\n\n"
                    "When: Tomorrow at 2:00 PM\n"
                    "Where: Zoom\n"
                    "Attendees: Jordan, Alex (Sales Lead)\n\n"
                    "Please prepare your pipeline summary."
                ),
                "timestamp": _hours_from_now(-1),
                "is_read": False,
            },
        ]

        resp = await client.post("/scenario/load", json={"emails": emails})
        logger.info(f"Email seeded: {resp.json()}")


async def seed_calendar(base_url: str = DEFAULT_CALENDAR_URL) -> None:
    """Seed test calendar with upcoming events."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        await client.post("/reset")

        events = [
            {
                "id": "cal-001",
                "title": "Discovery Call with DataFlow Inc",
                "start": _hours_from_now(2),
                "end": _hours_from_now(2.5),
                "attendees": ["jordan@company.com", "cto@dataflow.com"],
            },
            {
                "id": "cal-002",
                "title": "Weekly Pipeline Review",
                "start": _hours_from_now(26),
                "end": _hours_from_now(27),
                "attendees": ["jordan@company.com", "alex@company.com"],
            },
        ]

        resp = await client.post("/scenario/load", json={"events": events})
        logger.info(f"Calendar seeded: {resp.json()}")


async def seed_crm(base_url: str = DEFAULT_CRM_URL) -> None:
    """Seed test CRM with deals and contacts."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        await client.post("/reset")

        data = {
            "deals": [
                {
                    "id": "deal-001",
                    "name": "AcmeCorp Enterprise",
                    "value": 120000.0,
                    "stage": "qualification",
                    "created_at": _hours_from_now(-48),
                    "updated_at": _now_iso(),
                },
                {
                    "id": "deal-002",
                    "name": "TechStart Growth Plan",
                    "value": 45000.0,
                    "stage": "proposal",
                    "created_at": _hours_from_now(-168),
                    "updated_at": _hours_from_now(-24),
                },
                {
                    "id": "deal-003",
                    "name": "DataFlow Platform Deal",
                    "value": 15000.0,
                    "stage": "prospecting",
                    "created_at": _hours_from_now(-24),
                    "updated_at": _now_iso(),
                },
            ],
            "contacts": [
                {
                    "id": "contact-001",
                    "name": "Sarah Chen",
                    "email": "sarah.chen@acmecorp.com",
                    "company": "AcmeCorp",
                },
                {
                    "id": "contact-002",
                    "name": "Mike Johnson",
                    "email": "mike.johnson@techstart.io",
                    "company": "TechStart",
                },
            ],
        }

        resp = await client.post("/scenario/load", json=data)
        logger.info(f"CRM seeded: {resp.json()}")


async def seed_all(
    email_url: str = DEFAULT_EMAIL_URL,
    calendar_url: str = DEFAULT_CALENDAR_URL,
    crm_url: str = DEFAULT_CRM_URL,
) -> None:
    """Seed all test servers with scenario data."""
    await asyncio.gather(
        seed_email(email_url),
        seed_calendar(calendar_url),
        seed_crm(crm_url),
    )
    logger.info("All servers seeded successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed test servers with scenario data")
    parser.add_argument("--email-url", default=DEFAULT_EMAIL_URL)
    parser.add_argument("--calendar-url", default=DEFAULT_CALENDAR_URL)
    parser.add_argument("--crm-url", default=DEFAULT_CRM_URL)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_all(args.email_url, args.calendar_url, args.crm_url))
