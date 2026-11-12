import copy
import pathlib
import sys
import unittest
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from market_inputs import calculate_security, split_factor, validate_price, fetch_stooq_response, acquire


class MarketInputsTests(unittest.TestCase):
    def bundle(self):
        common = {'security_id': 'cusip:123456789', 'available_at': '2026-10-05T22:00:00Z', 'source_url': 'https://example.test/source'}
        return {'prices': [dict(common, date='2026-10-01', close=100, volume=100, currency='USD', price_basis='unadjusted_close', volume_basis='unadjusted_shares'), dict(common, date='2026-10-05', close=50, volume=200, currency='USD', price_basis='unadjusted_close', volume_basis='unadjusted_shares')],
            'denominators': [dict(common, date='2026-10-01', kind='outstanding', scope='share_class', unit='shares', value=1000), dict(common, date='2026-10-05', kind='float', scope='share_class', unit='shares', value=1200)],
            'actions': [dict(common, date='2026-10-05', type='split', new_shares=2, old_shares=1)],
            'action_coverage': [dict(common, date='2026-10-05', start='2026-10-01', complete=True)]}

    def calculate(self, bundle=None):
        return calculate_security('cusip:123456789', self.bundle() if bundle is None else bundle, '2026-10-05', position_shares=100, window=2)

    def test_split_adjusts_shares_marketcap_and_volume_consistently(self):
        result = self.calculate()
        self.assertEqual(result['market_cap_usd'], 100000)
        self.assertEqual(result['ownership_pct_outstanding'], 5)
        self.assertAlmostEqual(result['ownership_pct_float'], 100/12)
        self.assertEqual(result['liquidity']['average_daily_volume_shares_latest_basis'], 200)
        self.assertEqual(result['liquidity']['average_daily_dollar_volume_usd'], 10000)
        self.assertEqual(result['liquidity']['days_to_trade_estimate'], 5)

    def test_unknown_price_basis_rejected(self):
        bundle = self.bundle()
        for row in bundle['prices']: row['price_basis'] = 'provider_unspecified'
        self.assertIsNone(self.calculate(bundle)['market_cap_usd'])

    def test_future_available_price_is_rejected(self):
        row = self.bundle()['prices'][0]
        row['available_at'] = '2026-10-06'
        self.assertFalse(validate_price(row, '2026-10-05'))

    def test_issuer_shares_not_used_as_class_shares(self):
        bundle = self.bundle()
        bundle['denominators'][0]['scope'] = 'issuer'
        self.assertIsNone(self.calculate(bundle)['market_cap_usd'])

    def test_unproven_actions_block_stale_denominator_and_liquidity(self):
        bundle = self.bundle()
        bundle['action_coverage'] = []
        result = self.calculate(bundle)
        self.assertIsNone(result['market_cap_usd'])
        self.assertIsNone(result['liquidity'])
        self.assertIn('unverified_actions_since_outstanding_date', result['blockers'])

    def test_conflicting_provider_rows_quarantined(self):
        bundle = self.bundle()
        bundle['prices'].append(dict(bundle['prices'][-1], close=99))
        self.assertIn('conflicting_price_observations', self.calculate(bundle)['blockers'])

    def test_unsupported_merger_never_treated_as_split(self):
        bundle = self.bundle()
        bundle['actions'][0]['type'] = 'merger'
        self.assertIsNone(self.calculate(bundle)['market_cap_usd'])

    def test_old_denominator_rejected(self):
        bundle = self.bundle()
        bundle['denominators'][0]['date'] = '2026-01-01'
        self.assertIsNone(self.calculate(bundle)['market_cap_usd'])

    def test_invalid_units_currency_and_nonfinite_values_rejected(self):
        row = self.bundle()['prices'][0]
        for changes in [{'volume': float('nan')}, {'close': True}, {'currency': 'EUR'}, {'close': 0}]:
            self.assertFalse(validate_price(dict(row, **changes), '2026-10-05'))

    def test_invalid_participation_rejected(self):
        with self.assertRaises(ValueError):
            calculate_security('x', {}, '2026-10-05', participation=1.1)

    def test_http_200_browser_challenge_is_not_a_price_success(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'<html>Please enable JavaScript to verify your browser.</html>'
        with patch('market_inputs.urllib.request.urlopen', return_value=Response()):
            rows, evidence = fetch_stooq_response('aapl.us', 'cusip:037833100', 'USD', 'https://example.test/listing')
        self.assertEqual(rows, [])
        self.assertTrue(evidence['browser_challenge'])
        self.assertEqual(evidence['http_status'], 200)
        self.assertEqual(len(evidence['response_sha256']), 64)

    def test_acquisition_stops_batch_and_persists_source_challenge_cooldown(self):
        universe = {'source_url': 'https://example.test/universe', 'as_of': '2026-10-05',
            'securities': [{'cusip': '123456789', 'ticker': 'AAA', 'currency': 'USD'},
                           {'cusip': '987654321', 'ticker': 'BBB', 'currency': 'USD'}]}
        evidence = {'browser_challenge': True, 'http_status': 200, 'retrieved_at': '2026-10-05T00:00:00+00:00'}
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            with patch('market_inputs.OUT', base), patch('market_inputs.ROOT', base.parent), patch('market_inputs.urllib.request.urlopen', side_effect=RuntimeError('source unavailable')), patch('market_inputs.fetch_stooq_response', return_value=([], evidence)) as fetch:
                first = acquire(universe, limit=5)
                second = acquire(universe, limit=5)
        self.assertEqual(first['attempted_this_run'], 1)
        self.assertEqual(second['status'], 'provider_challenge_cooldown')
        self.assertEqual(fetch.call_count, 1)

    def test_missing_market_data_stays_missing(self):
        result = self.calculate({})
        self.assertIsNone(result['market_cap_usd'])
        self.assertIsNone(result['ownership_pct_float'])
        self.assertIsNone(result['liquidity'])


if __name__ == '__main__':
    unittest.main()
