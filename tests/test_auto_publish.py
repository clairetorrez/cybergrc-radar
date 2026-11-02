"""Offline checks for automatic publication and rejection safeguards."""
import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from discover import TODAY
from auto_publish import parse_offer

SOURCE={"title":"AI Security Certification","url":"https://www.isc2.org/new-ai-certification","source":"ISC2 AI Pilot","group":"AI governance","score":80,"publishedAt":None}

def page(title,description):
    return ("<html><head><meta name='description' content='An upcoming professional exam opportunity'></head>"
            "<body><h1>"+title+"</h1><p>"+description+"</p></body></html>")

class AutoPublishingTests(unittest.TestCase):
    def test_explicit_free_pilot_exam_with_deadline(self):
        cutoff=(TODAY+dt.timedelta(days=2)).strftime("%B %d, %Y")
        text=("Candidates with relevant professional experience can volunteer for the pilot by completing the form before "+cutoff+". "
              "There is no charge to participate in the pilot exam. Candidates must register and meet the applicable eligibility criteria. "
              "The offer relates to a three hour artificial intelligence security certification pilot.")
        offer,reason=parse_offer(SOURCE,page("AI Security Certification",text))
        self.assertIsNone(reason)
        self.assertEqual(offer["kind"],"Free exam")
        self.assertEqual(offer["deadline"],(TODAY+dt.timedelta(days=2)).isoformat())
        self.assertTrue(offer["autoApproved"])
        self.assertEqual(offer["publicationStatus"],"active")

    def test_pilot_without_free_or_deadline_is_not_approved(self):
        raw=page("AI Security Certification","We are building an examination in artificial intelligence security. The program is currently in development and candidates can learn more.")
        offer,reason=parse_offer(SOURCE,raw)
        self.assertIsNone(offer)
        self.assertIn(reason,("insufficient_offer_evidence","deadline_not_confirmed"))

    def test_closed_campaign_is_not_approved(self):
        cutoff=(TODAY+dt.timedelta(days=2)).strftime("%B %d, %Y")
        raw=page("AI Security Certification",
                "The pilot exam volunteer application period is now closed. Before "+cutoff+" candidates could register. There is no charge to participate in the pilot exam.")
        offer,reason=parse_offer(SOURCE,raw)
        self.assertIsNone(offer)
        self.assertEqual(reason,"offer_closed")

    def test_old_deadline_is_not_published(self):
        cutoff=(TODAY-dt.timedelta(days=1)).strftime("%B %d, %Y")
        raw=page("AI Security Certification",
                 "Please apply before "+cutoff+". There is no charge to participate in the pilot exam. Relevant professional cybersecurity experience is needed.")
        offer,reason=parse_offer(SOURCE,raw)
        self.assertIsNone(offer)
        self.assertEqual(reason,"deadline_passed")

if __name__=="__main__":
    unittest.main()
