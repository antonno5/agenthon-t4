import copy
import unittest
from types import SimpleNamespace

from agent_submit_v7.eps import extract_pair, seasonal_forecast
from agent_submit_v7.cli import predict, eligible_series
from agent_submit_v7.series import choose, positioning_forecast
from lab.v7_eps import asof, facts_by_quarter, validate_truth


META = dict(period_of_report='2020-03-31',doc_date='2020-05-01')


def parse(text, **meta):
    return extract_pair('d',text,dict(META,**meta),'2020-05-15')


class QuarterlyExtractionTests(unittest.TestCase):
    def test_loss_and_unicode_whitespace_keep_exact_quote_offsets(self):
        text='Three Months Ended March 31, 2020 2019\nEarnings per share Basic $ ( 0.09 ) $ .56\nDiluted\u200b $ ( 0.09 )\xa0 $ .56 Shares used in per share calculation Basic 100 100'
        pair=parse(text)
        self.assertEqual((pair.current,pair.previous_year),(-.09,.56))
        self.assertIn('Diluted\u200b',text[pair.start:pair.end])

    def test_annual_only_table_cannot_become_quarterly_eps(self):
        self.assertIsNone(parse('Years ended December 31, 2020 2019 Diluted earnings per share $8 $7'))

    def test_reversed_year_columns_are_rejected(self):
        self.assertIsNone(parse('Three Months Ended March 31, 2019 2020 Diluted earnings per share $1 $2'))

    def test_three_current_quarters_are_not_mistaken_for_yearly_pair(self):
        self.assertIsNone(parse('Quarter ended March 31, 2020 December 31, 2019 March 31, 2019 Diluted earnings per share $1 $2 $3'))

    def test_year_to_date_columns_are_not_added_to_quarter_eps(self):
        pair=parse('Three Months Ended Six Months Ended March 31, 2020 2019 2020 2019 Diluted earnings per share $1.25 $1.10 $2.50 $2.30')
        self.assertEqual((pair.current,pair.previous_year),(1.25,1.1))

    def test_future_and_adjusted_eps_are_rejected(self):
        prefix='Three Months Ended March 31, 2020 2019 '
        for qualifier in ['Adjusted non-GAAP ', 'We expect ', 'Our guidance: ']:
            self.assertIsNone(parse(prefix+qualifier+'Diluted earnings per share $2.00 $1.00'))
        self.assertIsNone(parse(prefix+'Diluted earnings per share $2.00 $1.00',doc_date='2020-06-01'))
        self.assertIsNone(parse(prefix+'Diluted earnings per share $2.00 $1.00',period_of_report='2020-06-30'))

    def test_total_eps_is_used_instead_of_continuing_operations(self):
        pair=parse('Three Months Ended March 31, 2020 2019 Earnings per share of common stock: Assuming dilution: Continuing operations $1.02 $.73 Discontinued operations $(.01) $.08 Total $1.01 $.81 Basic $1.02 $.82')
        self.assertEqual((pair.current,pair.previous_year),(1.01,.81))

    def test_conflicting_equal_support_tables_fail_closed(self):
        self.assertIsNone(parse('Three Months Ended March 31, 2020 2019 Diluted earnings per share $1.00 $2.00 Other table. Three Months Ended March 31, 2020 2019 Diluted earnings per share $3.00 $4.00'))

    def test_weighted_share_counts_are_never_eps(self):
        self.assertIsNone(parse('Three Months Ended March 31, 2020 2019 Earnings per share calculations. Shares used in calculation Diluted 105 100'))

    def test_seasonality_uses_matching_quarter_comparator(self):
        pair=parse('Three Months Ended March 31, 2020 2019 Diluted earnings per share $1.5 $1.0')
        self.assertEqual(seasonal_forecast(2.,pair),2.25)


class PipelineTests(unittest.TestCase):
    def test_prediction_is_invariant_to_task_and_entity_identity(self):
        text='Three Months Ended March 31, 2020 2019 Diluted earnings per share $1.5 $1.0'
        corpus=SimpleNamespace(doc_texts={'d':text},doc_meta={'d':META},doc_dates={'d':'2020-05-01'})
        task=dict(task_id='a',cutoff_date='2020-07-10',target=dict(name='eps_yoy_direction',labels=['up','down']))
        entity=dict(entity_id='ORIGINAL',prior_year_q_eps=2.,quarter_reported='three months ended 2020-06-30')
        original=predict(task,entity,corpus,['d'])
        renamed=predict(dict(task,task_id='unseen'),dict(entity,entity_id='RENAMED'),corpus,['d'])
        self.assertEqual(original,renamed)
        self.assertEqual(original[0]['point_forecast'],2.25)
        self.assertEqual(original[0]['label'],'up')

    def test_missing_parser_evidence_retains_baseline(self):
        corpus=SimpleNamespace(doc_texts={'d':'Unrecognized financial layout.'},doc_meta={'d':META},doc_dates={'d':'2020-05-01'})
        task=dict(cutoff_date='2020-07-10',target=dict(name='eps_yoy_direction',labels=['up','down']))
        p,route,*_=predict(task,dict(prior_year_q_eps=2.),corpus,['d'])
        self.assertEqual(p['point_forecast'],2.)
        self.assertEqual(route,'eps-prior-or-consensus')

    def test_future_rows_are_absent_from_runtime_selection(self):
        c=SimpleNamespace(doc_texts={'d':'date | bid_to_cover\n2020-01-01 | 2\n2030-01-01 | 999\n'})
        t=dict(cutoff_date='2020-02-01',target=dict(name='bid_to_cover_ratio'))
        self.assertEqual(eligible_series(t,{},c,['d'])[0],[2.])

    def test_sparse_history_cannot_change_the_baseline(self):
        self.assertEqual(choose({'base':[9.,8.], 'lucky':[0.,0.]},'base')[0],'base')
        result,trace=positioning_forecast(list(range(25)),[100.]*25,5)
        self.assertIsNone(result)
        self.assertLess(trace['origins'],4)

    def test_tied_or_noisy_historical_results_retain_baseline(self):
        self.assertEqual(choose({'base':[1.]*5,'tie':[1.]*5},'base')[0],'base')
        self.assertEqual(choose({'base':[2.]*5,'strong':[.2]*5},'base')[0],'strong')


class PointInTimeDataTests(unittest.TestCase):
    def test_reference_requires_the_official_label_field(self):
        task=dict(entities=[dict(entity_id='x')],target=dict(type='classification',labels=['up','down']))
        with self.assertRaises(ValueError):
            validate_truth(task,dict(outcomes=[dict(entity_id='x',y=1.,label='up')]))
        validate_truth(task,dict(outcomes=[dict(entity_id='x',y=1.,true_label='up')]))

    def test_later_restatement_never_replaces_first_reported_target(self):
        rows=[dict(filed='2019-05-01',accn='a',start='2019-01-01',end='2019-03-31',val=1.),
              dict(filed='2020-05-01',accn='b',start='2019-01-01',end='2019-03-31',val=99.)]
        self.assertEqual(asof(rows,'2021-01-01',first=True)['val'],1.)
        self.assertEqual(asof(rows,'2019-06-01')['val'],1.)

    def test_annual_and_late_filed_facts_are_excluded(self):
        rows=[dict(start='2020-01-01',end='2020-03-31',filed='2020-05-01',val=1.,accn='a',form='10-Q'),
              dict(start='2020-01-01',end='2020-12-31',filed='2021-02-01',val=4.,accn='b',form='10-K'),
              dict(start='2020-01-01',end='2020-03-31',filed='2022-05-01',val=99.,accn='c',form='10-Q')]
        data=dict(facts={'us-gaap':{'EarningsPerShareDiluted':{'units':{'USD/shares':rows}}}})
        result=facts_by_quarter(data)
        self.assertEqual([r['val'] for v in result.values() for r in v],[1.])


if __name__=='__main__': unittest.main()
