import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from point_in_time import available_by, chronology, select_versions


def version(accession, day, value, form='13F-HR', amendment=''):
    return dict(accession=accession,filing_date=day,report_date='2025-09-30',form=form,amendment_type=amendment,holdings=[{'value_usd':value}])


class TemporalTests(unittest.TestCase):
    def test_restatement_replaces_prior_additions(self):
        records=[version('a','2025-10-01',1),version('b','2025-10-02',2,'13F-HR/A','NEW HOLDINGS'),version('c','2025-10-03',5,'13F-HR/A','RESTATEMENT'),version('d','2025-10-04',7,'13F-HR/A','NEW HOLDINGS')]
        old=select_versions(records,'2025-10-02');new=select_versions(records)
        self.assertEqual(old['selected_accessions'],['a','b']);self.assertEqual(new['selected_accessions'],['c','d'])
        self.assertEqual(sum(h['value_usd'] for h in new['holdings']),12)
    def test_no_lookahead_or_invented_timestamps(self):
        r=version('a','2025-10-02',1)
        self.assertFalse(available_by(r,'2025-10-01'))
        self.assertFalse(available_by(r,'2025-10-02T12:00:00+00:00'))
        self.assertTrue(available_by(r,'2025-10-02'))
        self.assertIsNone(chronology(r)['ingested_at'])
    def test_nport_needs_publication_evidence(self):
        r=version('a','2025-10-02',1,'NPORT-P')
        self.assertFalse(available_by(r,'2026-01-01'))
        r['public_available_at']='2025-12-01T12:00:00Z'
        self.assertFalse(available_by(r,'2025-11-01'));self.assertTrue(available_by(r,'2025-12-02'))
    def test_unknown_amendment_and_missing_base(self):
        self.assertEqual(select_versions([version('a','2025-10-02',1,'13F-HR/A')])['status'],'blocked_unknown_amendment')
        self.assertEqual(select_versions([version('a','2025-10-02',1,'13F-HR/A','NEW HOLDINGS')])['status'],'blocked_missing_base')
    def test_same_day_order_is_not_accession_order(self):
        records=[version('a','2025-10-02',1),version('b','2025-10-02',2,'13F-HR/A','RESTATEMENT')]
        self.assertEqual(select_versions(records)['status'],'blocked_same_day_order')
    def test_conflicting_accession_fails_closed(self):
        records=[version('a','2025-10-01',1),version('a','2025-10-01',2)]
        self.assertEqual(select_versions(records)['status'],'blocked_conflicting_accession')

    def test_invalid_temporal_evidence_is_quarantined(self):
        for value in ('not-a-date', '2025-10-02T12:00:00', 123):
            r=version('a','2025-10-02',1);r['public_available_at']=value
            self.assertFalse(available_by(r,'2025-12-01'))
            self.assertEqual(select_versions([r])['status'],'blocked_invalid_temporal_evidence')
    def test_null_timestamps_and_filed_date_alias(self):
        r=version('a','2025-10-02',1);r['accepted_at']=None;r['filed_date']=r.pop('filing_date')
        self.assertEqual(chronology(r)['date_precision'],'day')
        self.assertEqual(select_versions([r])['status'],'selected')
        self.assertTrue(available_by(r,'2025-10-03'))

    def test_public_download_observation_is_conservative_availability_bound(self):
        r=version('a','2025-10-02',1,'NPORT-P')
        r['public_observed_at']='2026-01-02T12:00:00Z'
        self.assertFalse(available_by(r,'2025-12-31'))
        self.assertTrue(available_by(r,'2026-01-03'))
        self.assertIsNone(chronology(r)['public_available_at'])
