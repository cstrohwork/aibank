import copy
import pathlib
import sys
import unittest
import json
import io
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from investor_intelligence import classify_portfolio, evidence, score_target, rollup_orientation, discover_mandate_sources

DAY = '2025-09-30'
MANDATE = {'source_url': 'https://example.test/prospectus', 'evidence_excerpt': 'Active US equity strategy',
           'available_date': '2025-01-01', 'effective_from': '2025-01-01', 'orientation': 'active'}


class ClassificationTest(unittest.TestCase):
    def metrics(self):
        return {'as_of': DAY, 'benchmark_as_of': DAY, 'source_urls': ['https://example.test/factors'],
                'value_score': 80, 'growth_score': 40, 'both_dimensions_coverage_pct': 70, 'value_factor_count': 2, 'growth_factor_count': 2}

    def test_missing_evidence_stays_unknown_and_editorial_preserved(self):
        r = classify_portfolio({'editorial_style': 'Value', 'as_of': DAY}, {'orientation': 'passive'}, DAY)
        self.assertEqual(r['orientation'], 'unknown')
        self.assertEqual(r['editorial_style'], 'Value')
        self.assertIsNone(r['primary_style'])

    def test_no_future_or_expired_mandate(self):
        for delta in ({'available_date': '2025-10-01'}, {'effective_to': DAY}):
            self.assertFalse(evidence(dict(MANDATE, **delta), DAY))

    def test_coverage_and_same_date_gate(self):
        m = self.metrics()
        self.assertEqual(classify_portfolio(m, as_of=DAY)['primary_style'], 'Value')
        for delta in ({'both_dimensions_coverage_pct': 69.99}, {'benchmark_as_of': '2025-08-31'}, {'value_score': float('nan')}):
            self.assertIsNone(classify_portfolio(dict(m, **delta), as_of=DAY)['primary_style'])

    def test_sector_strict_threshold(self):
        m = dict(self.metrics(), sector_coverage_pct=90, largest_sector='Technology', largest_sector_pct=75)
        self.assertIsNone(classify_portfolio(m)['axes']['concentration'])
        self.assertEqual(classify_portfolio(dict(m, largest_sector_pct=75.1))['primary_style'], 'Sector')

    def test_overlap_does_not_prove_index(self):
        m = dict(self.metrics(), index_overlap_pct=100, active_share_pct=0, index_comparison_coverage_pct=100)
        self.assertIsNone(classify_portfolio(m)['axes']['implementation'])
        self.assertEqual(classify_portfolio(m, dict(MANDATE, implementation='index'))['primary_style'], 'Index')

    def test_garp_positive_forward_growth_required(self):
        m = dict(self.metrics(), forward_coverage_pct=80, forward_pe=10, benchmark_forward_pe=20,
                 forward_eps_growth_pct=20, benchmark_forward_eps_growth_pct=10)
        self.assertEqual(classify_portfolio(m)['primary_style'], 'GARP')
        self.assertFalse(classify_portfolio(dict(m, forward_eps_growth_pct=-20)).get('garp', False))

    def test_special_dividends_do_not_establish_yield(self):
        m = dict(self.metrics(), yield_coverage_pct=90, dividend_yield=.08, benchmark_dividend_yield=.02, yield_basis='special_distribution')
        self.assertIsNone(classify_portfolio(m)['axes']['income'])
        self.assertEqual(classify_portfolio(dict(m, yield_basis='regular_indicated_forward'))['axes']['income'], 'yield')

    def test_at_least_two_factors_per_dimension(self):
        self.assertIsNone(classify_portfolio(dict(self.metrics(), value_factor_count=1))['primary_style'])

    def test_firm_rollup_does_not_renormalize_missing_funds(self):
        f = {'fund_id': 'fund1', 'as_of': DAY, 'verified_equity_assets_usd': 20,
             'manager_mapping': MANDATE, 'asset_evidence': MANDATE, 'mandate': MANDATE}
        r = rollup_orientation([f], 100, DAY)
        self.assertEqual(r['orientation'], 'unknown')
        self.assertEqual(r['active_pct'], 20)
        self.assertEqual(rollup_orientation([dict(f, verified_equity_assets_usd=80)], 100, DAY)['orientation'], 'active')
        self.assertEqual(rollup_orientation([f, f], 100, DAY)['orientation'], 'unknown')
        self.assertIsNone(rollup_orientation([dict(f, verified_equity_assets_usd=120)], 100, DAY)['active_pct'])

    def test_input_not_mutated(self):
        m = self.metrics()
        before = copy.deepcopy(m)
        classify_portfolio(m, MANDATE)
        self.assertEqual(m, before)


class DiscoveryTest(unittest.TestCase):
    def test_dated_prospectus_sources_remain_unverified(self):
        entries = [{'registrant_cik': '123', 'fund_id': 'S1', 'fund_name': 'Fund'}]
        payload = {'filings': {'recent': {'form': ['497K'], 'accessionNumber': ['000123-25-000001'],
                   'primaryDocument': ['prospectus.htm'], 'filingDate': ['2025-01-01']}}}
        with patch('investor_intelligence.time.sleep'), patch('investor_intelligence.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
            result = discover_mandate_sources(entries, 1)
        r = result['registrants'][0]
        self.assertEqual(r['status'], 'prospectus_candidates_found')
        self.assertEqual(r['prospectus_candidates'][0]['available_date'], '2025-01-01')
        self.assertEqual(r['prospectus_candidates'][0]['fund_attribution'], 'unverified')
        self.assertIsNone(r['prospectus_candidates'][0]['effective_from'])
        with patch('investor_intelligence.urllib.request.urlopen') as fetch:
            resumed = discover_mandate_sources(entries, 1, previous=result)
        fetch.assert_not_called()
        self.assertEqual(resumed['registrants'][0]['prospectus_candidates'], r['prospectus_candidates'])


class TargetTest(unittest.TestCase):
    def inputs(self):
        return ({'investor_id': 'fund1', 'as_of': DAY, 'mandate': MANDATE, 'fundamental_coverage_pct': 90,
                 'peer_fit_score': 80, 'peer_fit_score_evidence': ['peer1'], 'mandate_fit_score': 90,
                 'mandate_fit_score_evidence': ['US equity'], 'verified_equity_assets_usd': 100000000,
                 'max_position_pct': 5, 'existing_position_usd': 0, 'proposed_position_usd': 1000000, 'source_urls': ['https://example.test/fund']},
                {'issuer_id': 'issuer1', 'as_of': DAY, 'average_daily_dollar_volume_usd': 10000000,
                 'max_participation_pct': 10, 'max_days_to_build': 10, 'source_urls': ['https://example.test/market']})

    def test_explained_score_and_capacity(self):
        c, i = self.inputs()
        r = score_target(c, i)
        self.assertEqual(r['status'], 'eligible')
        self.assertEqual(r['days_to_build'], 1)
        self.assertEqual(r['score'], 84.5)
        self.assertEqual(set(r['components']), {'peer_fit', 'mandate_fit', 'capacity', 'liquidity'})

    def test_capacity_and_liquidity_gate(self):
        c, i = self.inputs()
        r = score_target(dict(c, proposed_position_usd=20000000), i)
        self.assertIsNone(r['score'])
        self.assertIn('proposed_position_exceeds_mandate_capacity', r['reasons'])
        self.assertIn('proposed_position_exceeds_liquidity_limit', r['reasons'])

    def test_missing_and_invalid_inputs_never_score(self):
        c, i = self.inputs()
        for delta in ({'mandate': {}}, {'fundamental_coverage_pct': 20}, {'peer_fit_score': 101}, {'max_position_pct': 110}, {'proposed_position_usd': float('inf')}):
            self.assertIsNone(score_target(dict(c, **delta), i)['score'])
        self.assertIsNone(score_target(dict(c, existing_position_usd=5000000), i)['score'])
        self.assertIsNone(score_target(dict(c, existing_position_usd=None), i)['score'])
        self.assertIsNone(score_target(c, dict(i, average_daily_dollar_volume_usd=0))['score'])
        self.assertIsNone(score_target(c, dict(i, as_of='2025-10-01'))['score'])


if __name__ == '__main__':
    unittest.main()
