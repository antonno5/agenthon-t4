import unittest
from unittest.mock import patch
from agent_submit_v8.cli import predict

class SelectionCutoff(unittest.TestCase):
    def test_earlier_or_invalid_cutoff_keeps_fallback(self):
        fallback=({},'fallback',0,None,{})
        for cutoff in ['2021-12-31','2014-01-01','',None,'invalid']:
            with self.subTest(cutoff=cutoff),patch('agent_submit_v8.cli.v7.predict',return_value=fallback),patch('agent_submit_v8.cli.latest_pair') as pair:
                self.assertEqual(predict({'target':{'name':'eps_growth'},'cutoff_date':cutoff},{},None,[]),fallback)
                pair.assert_not_called()
    def test_eligible_cutoff_reaches_corpus_extraction(self):
        fallback=({},'fallback',0,None,{})
        for cutoff in ['2022-01-01','2024-10-10T00:00:00Z']:
            with self.subTest(cutoff=cutoff),patch('agent_submit_v8.cli.v7.predict',return_value=fallback),patch('agent_submit_v8.cli.latest_pair',return_value=None) as pair:
                predict({'target':{'name':'eps_growth'},'cutoff_date':cutoff},{},None,[])
                pair.assert_called_once()

if __name__=='__main__':unittest.main()
