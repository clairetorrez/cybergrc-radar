"""Offline tests for opportunity discovery, scoring, safety and expiry."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import discover

class DiscoveryTests(unittest.TestCase):
    def test_targeted_pilot_without_beta_in_heading(self):
        source={"name":"ISC2 AI Security Pilot","group":"AI governance","mode":"watch"}
        page="""<html><head><meta name="description" content="ISC2 invites qualified volunteers to participate in a pilot exam for AI security"></head>
        <body><h1>AI Security Certification</h1><p>Complete the volunteer form before November 4, 2026 to enter the pilot program.</p></body></html>"""
        item=discover.process_page(source,"https://www.isc2.org/new-ai-certification","",page)
        self.assertIsNotNone(item)
        self.assertGreaterEqual(item["score"],45)
        self.assertIn("AI",item["group"])
        self.assertEqual(item["deadlineHint"],"2026-11-04")
        self.assertFalse(item["verified"])

    def test_expired_pe_cb_offer_not_published_as_active(self):
        source={"name":"PECB Free Beta Announcement","group":"GRC and ISO","mode":"watch"}
        page="""<html><body><h1>PECB Launches free Skills Beta Exams</h1><p>The campaign will remain available until October 30, 2026.</p></body></html>"""
        entry=discover.process_page(source,"https://pecb.com/en/newsReleases/test","",page)
        self.assertTrue(entry is None or entry["status"]=="expired")

    def test_closed_beta_announcement_is_rejected(self):
        src={"name":"ISACA Offers","group":"GRC","mode":"listing"}
        page="""<html><body><h1>The AAIG Beta Application Period Is Now Closed</h1><p>Application closed for this beta program.</p></body></html>"""
        self.assertIsNone(discover.process_page(src,"https://www.isaca.org/credentialing/aaig","",page))

    def test_generic_navigation_is_not_a_lead(self):
        src={"name":"Linux Foundation","group":"Cloud security","mode":"listing"}
        page="""<html><body><h1>Free Courses</h1><p>Free training courses for everyone.</p></body></html>"""
        self.assertIsNone(discover.process_page(src,"https://training.linuxfoundation.org/free","",page))

    def test_host_approved(self):
        allowed={"isaca.org","isc2.org"}
        self.assertTrue(discover.allowed("https://www.isaca.org/credentialing",allowed))
        self.assertFalse(discover.allowed("https://isaca.org.attacker.example/sale",allowed))
        self.assertFalse(discover.allowed("http://www.isaca.org/page",allowed))
        self.assertIsNone(discover.normalize("https://evil.example/","https://www.isaca.org",allowed))

    def test_deadline_is_explicit_only(self):
        self.assertEqual(discover.deadline_from_text("Apply by November 4, 2026"),"2026-11-04")
        self.assertEqual(discover.deadline_from_text("Offer available until October 30, 2026"),"2026-10-30")
        self.assertIsNone(discover.deadline_from_text("Updated November 4, 2026"))
        self.assertEqual(discover.deadline_from_text("Applications Due: 11:59 pm US CT, 30 November 2026"),"2026-11-30")
        self.assertEqual(discover.deadline_from_text("Application Deadline: November 3, 2026"),"2026-11-03")

if __name__=="__main__":unittest.main()
