import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts' / 'update_black_friday.py'
spec = importlib.util.spec_from_file_location('update_black_friday', path)
seasonal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seasonal)


class BlackFridayImportTest(unittest.TestCase):
    def make_row(self, **updates):
        return {
            'vendor': 'Example',
            'category': 'training',
            'offer': 'Security course',
            'discount': '25% off',
            'source': 'vendor',
            'last_checked': '2026-11-18',
            'status': '✅ Live',
            'url': 'https://example.com/sale/',
            **updates,
        }

    def test_separates_reported_and_watchlist(self):
        result = seasonal.build([
            self.make_row(),
            self.make_row(vendor='Reported', source='third-party', url='https://reported.example/sale'),
            self.make_row(vendor='Watch', status='👀 Not announced', url='https://watch.example', offer='', discount=''),
        ])
        self.assertEqual([d['verification'] for d in result['offers']], ['vendor', 'reported'])
        self.assertEqual([d['provider'] for d in result['watchlist']], ['Watch'])
        self.assertIsNone(result['offers'][0]['deadline'])

    def test_dated_terms_preserve_the_vendor_time_zone(self):
        result = seasonal.build([self.make_row(url='https://onlysecurity.com/black-friday/', starts='2026-11-23', ends='2026-11-30')])
        self.assertEqual(result['offers'][0]['startAt'], '2026-11-23T00:00:00Z')
        self.assertEqual(result['offers'][0]['endAt'], '2026-12-01T00:00:00Z')

    def test_stable_id_and_duplicate_rejection(self):
        first = self.make_row()
        equivalent_url = self.make_row(url='https://www.example.com/sale?ref=list')
        self.assertEqual(seasonal.build([first])['offers'][0]['id'], seasonal.build([equivalent_url])['offers'][0]['id'])
        with self.assertRaisesRegex(ValueError, 'Duplicate provider URL'):
            seasonal.build([first, equivalent_url])

    def test_rejects_unsafe_urls_and_bad_deadlines(self):
        with self.assertRaisesRegex(ValueError, 'Invalid HTTPS'):
            seasonal.build([self.make_row(source_url='javascript:alert(1)')])
        with self.assertRaises(ValueError):
            seasonal.build([self.make_row(starts='2026-11-30', ends='2026-11-23')])
