"""Current investor intake must complete before June-quarter and older backfill."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from sec_history import investor_intake_window, select_download_queue


class InvestorQuarterPriorityTests(unittest.TestCase):
    def rows(self):
        return [
            dict(accession='current', form='13F-HR', filing_date='2026-11-12'),
            dict(accession='notice', form='13F-NT', filing_date='2026-11-11'),
            dict(accession='other', form='8-K', filing_date='2026-11-12'),
            dict(accession='june', form='13F-HR', filing_date='2026-08-14'),
            dict(accession='old', form='13F-HR', filing_date='2026-05-14')]

    def test_current_investor_capture_precedes_june_and_older(self):
        rows = self.rows()
        queue, plan = select_download_queue(rows, {}, rows, 10)
        self.assertEqual([row['accession'] for row in queue], ['current', 'notice', 'other'])
        self.assertEqual(plan['active_target_report_date'], '2026-09-30')

    def test_june_automatically_follows_completed_current_capture(self):
        rows = self.rows()
        state = {key: {'status': 'archived'} for key in ('current', 'notice')}
        available = [row for row in rows if row['accession'] not in state]
        queue, plan = select_download_queue(rows, state, available, 10)
        self.assertEqual([row['accession'] for row in queue], ['june', 'other'])
        self.assertEqual(plan['active_target_report_date'], '2026-06-30')

    def test_current_failed_or_deferred_source_holds_june_backfill(self):
        rows = self.rows()
        for status in ('failed', 'deferred'):
            with self.subTest(status=status):
                state = {'current': {'status': status}, 'notice': {'status': 'archived'}}
                available = [row for row in rows if row['accession'] not in state]
                queue, plan = select_download_queue(rows, state, available, 10)
                self.assertNotIn('june', [row['accession'] for row in queue])
                self.assertEqual(plan['active_target_report_date'], '2026-09-30')

    def test_new_current_filing_interrupts_june_backfill(self):
        rows = self.rows()
        state = {key: {'status': 'archived'} for key in ('current', 'notice')}
        new = dict(accession='live', form='NPORT-P', filing_date='2026-11-13')
        rows.insert(0, new)
        queue, plan = select_download_queue(rows, state, [new, rows[-2], rows[-1]], 10)
        self.assertEqual([row['accession'] for row in queue], ['live'])
        self.assertEqual(plan['active_target_report_date'], '2026-09-30')

    def test_older_investor_capture_follows_completed_june(self):
        rows = self.rows()
        state = {key: {'status': 'archived'} for key in ('current', 'notice', 'june')}
        queue, plan = select_download_queue(rows, state, [rows[2], rows[4]], 10)
        self.assertEqual([row['accession'] for row in queue], ['old', 'other'])
        self.assertEqual(plan['active_target_report_date'], 'historical')

    def test_intake_window_boundaries(self):
        for day, period in [('2026-09-30', '2026-09-30'), ('2026-09-29', '2026-06-30'),
                            ('2026-07-01', '2026-06-30'), ('2026-06-30', 'historical')]:
            self.assertEqual(investor_intake_window({'filing_date': day}), period)
