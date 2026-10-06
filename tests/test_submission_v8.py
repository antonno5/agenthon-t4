import json
import unittest
from agent_submit_v8.analyst import validate_decisions
from agent_submit_v8.numeric import indicators,candidates,needs_agent,packet

class AnalystBoundaries(unittest.TestCase):
    def setUp(self):
        self.packet={'id':'X','choices':{'v6':0,'core':.2}}
        self.good=dict(id='X',selector='core',quality='v6',guard='core',reason='Operating signal is positive.')
    def test_valid(self):
        self.assertEqual(validate_decisions(json.dumps(self.good),[self.packet])['X'],self.good)
    def test_rejects_invented_number(self):
        bad=dict(self.good,selector=3.2)
        with self.assertRaises(ValueError):validate_decisions(json.dumps(bad),[self.packet])
    def test_rejects_partial_duplicate_unknown_and_extra(self):
        bads=['',json.dumps(self.good)+'\n'+json.dumps(self.good),json.dumps(dict(self.good,id='Y')),json.dumps(dict(self.good,future_label='up'))]
        for bad in bads:
            with self.subTest(bad=bad),self.assertRaises(ValueError):validate_decisions(bad,[self.packet])
    def test_missing_operating_is_not_zero(self):
        row=dict(id='A',eps=[-.5,None,None,-1.,-1.,None,None,None],prior=-1.,scale=1.,metrics={},split_warning=False)
        f=indicators(row)
        self.assertIsNone(f['operating_eps_delta'])
        self.assertEqual(f['eps_delta'],.5)
        self.assertEqual(candidates(row)['core'],candidates(row)['robust'])
        self.assertFalse(needs_agent(row))
    def test_packet_excludes_labels_identity_and_absolute_eps(self):
        row=dict(id='A',eps=[1.]*8,prior=1.,scale=1.,metrics={},split_warning=False,ticker='SECRET',cutoff='2020-01-01',y=9.)
        p=packet(row,candidates(row))
        s=json.dumps(p)
        self.assertEqual(set(p),{'id','signals','choices'})
        for value in ['SECRET','2020-01-01','"y"']:self.assertNotIn(value,s)

if __name__=='__main__':unittest.main()
