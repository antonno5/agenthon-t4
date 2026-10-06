import unittest
from types import SimpleNamespace
from agent_submit.cli import tables, forecast, allowed_docs, quote, latest_eps


class SubmissionTests(unittest.TestCase):
    def test_table_rejects_future_rows(self):
        text = 'date | value\n2020-01-01 | 1\n2030-01-01 | 999\n'
        self.assertEqual(list(tables(text, '2020-02-01'))[0][1], [['2020-01-01', '1']])

    def test_manifest_and_cutoff_control_citations(self):
        corpus = SimpleNamespace(doc_meta={'a': {}, 'b': {}, 'future': {}},
                                 doc_dates={'a': '2020-01-01', 'b': '2020-01-01', 'future': '2030-01-01'})
        bindings = {'a': {'entity_ids': ['X']}, 'b': {'entity_ids': ['Y']}, 'future': {'shared': True}}
        self.assertEqual(allowed_docs({'cutoff_date': '2021-01-01'}, {'entity_id': 'X'}, corpus, bindings), ['a'])

    def test_revision_output_uses_level_not_direction_code(self):
        corpus = SimpleNamespace(doc_texts={'d': 'reference_month | as_of_2020-01-01 | as_of_2020-02-01\n2019-10 | 100 | 103\n2019-11 | 200 | 205\n'})
        task = {'target': {'name': 'next_estimate_revision_direction', 'labels': ['up','down']}, 'cutoff_date': '2020-03-01'}
        prediction, _, _, _ = forecast(task, {'latest_precutoff_estimate': 1000}, corpus, ['d'])
        self.assertEqual(prediction['point_forecast'], 1004)
        self.assertEqual(prediction['label'], 'up')

    def test_negated_distress_does_not_trigger_credit_event(self):
        corpus = SimpleNamespace(doc_texts={'d': 'There is no substantial doubt about our ability to continue.'})
        task = {'target': {'name': 'credit_event_12m', 'labels': ['credit_event','no_event']}, 'cutoff_date': '2020-01-01'}
        prediction, _, _, _ = forecast(task, {}, corpus, ['d'])
        self.assertEqual(prediction['label'], 'no_event')

    def test_eps_guidance_is_not_treated_as_reported_earnings(self):
        corpus = SimpleNamespace(doc_texts={'d': 'We expect diluted earnings per share of $2.50.'})
        self.assertIsNone(latest_eps(corpus, ['d']))

    def test_quote_keeps_original_offsets(self):
        text = 'prefix  actual evidence  suffix'
        claim = quote('d', text, 6, 24)
        self.assertEqual(text[claim['span_start']:claim['span_end']], claim['claim'])


if __name__ == '__main__':
    unittest.main()
