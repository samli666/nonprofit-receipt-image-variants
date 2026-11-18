from src.nonprofit_media import CampaignReport, campaign_status


def test_campaign_waits_for_a_reminder_for_each_received_receipt() -> None:
    report = CampaignReport(campaign="winter-kits", receipts_received=3, volunteer_reminders=2)

    assert campaign_status(report) == "needs_receipts"
