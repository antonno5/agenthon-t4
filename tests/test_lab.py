import copy
import json
import unittest
from pathlib import Path

from agent_v6.pipeline import accept_locator_response, parse_document, causal_example


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.doc = dict(doc_id='known', doc_date='2019-01-02', entity_ids=['X'],
                        text='Historical observations for X.\nDate 2019-01-01; available 2019-01-02; value 2.5; tenor 2; offering 0; reopening 0.')

    def test_post_cutoff_observation_rejected_even_with_false_document_date(self):
        doc = copy.deepcopy(self.doc)
        doc['text'] = doc['text'].replace('available 2019-01-02', 'available 2021-01-01')
        with self.assertRaises(ValueError):
            parse_document(doc, '2020-01-01')

    def test_locator_cannot_invent_number_or_document_or_code(self):
        for response in [dict(doc_id='../../truth', quote='2.5'), dict(doc_id='known', quote='value 99'),
                         dict(doc_id='known', quote='2.5', code='print(1)')]:
            with self.assertRaises(ValueError):
                accept_locator_response(response, {'known': self.doc}, '2020-01-01')

    def test_quote_offsets_and_cutoff(self):
        response = dict(doc_id='known', quote='value 2.5')
        claim = accept_locator_response(response, {'known': self.doc}, '2020-01-01')
        self.assertEqual(self.doc['text'][claim['span_start']:claim['span_end']], claim['claim'])
        with self.assertRaises(ValueError):
            accept_locator_response(response, {'known': self.doc}, '2018-01-01')

    def test_equivalent_supported_layouts(self):
        a = parse_document(self.doc, '2020-01-01')
        doc = dict(self.doc, text='Header\ndate,available,value,tenor,offering,reopening\n2019-01-01,2019-01-02,2.5,2,0,0')
        self.assertEqual(a, parse_document(doc, '2020-01-01'))
        doc['text'] = 'Header\nOBS ' + json.dumps(a[0])
        self.assertEqual(a, parse_document(doc, '2020-01-01'))

    def test_unknown_layout_abstains(self):
        with self.assertRaises(ValueError):
            parse_document(dict(self.doc, text='Header\nMaybe 42?'), '2020-01-01')

    def test_published_target_is_not_a_future_training_example(self):
        rows = [{'available': '2014-03-07'}, {'available': '2014-03-07'}]
        self.assertFalse(causal_example(rows, 0, 1))
        rows[1]['available'] = '2014-03-08'
        self.assertTrue(causal_example(rows, 0, 1))

    def test_late_revision_cannot_enter_historical_features(self):
        rows = [{'available': '2014-03-07'}, {'available': '2014-02-01'}, {'available': '2014-03-09'}]
        self.assertFalse(causal_example(rows, 1, 1))


if __name__ == '__main__':
    unittest.main()
