"""Guard learned-model availability, exact feature arithmetic and input admission."""
import copy
import json
from pathlib import Path
import unittest
import numpy as np
from agent_submit_v11.cpi import features,forecasts,MODEL_PATH,IDS
from agent_submit_v11.cli import cpi_inputs
from agent_submit import cli as v6
from agent_v2.indexer import build_index

UNIT=Path('test-output/v10/official-track4/units/t4-cpicomp-202410-us11')
if not UNIT.exists():UNIT=Path('test-output/independent-demo/official-track4/units/t4-cpicomp-202410-us11')


class CpiSubmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task=json.loads((UNIT/'task.json').read_text());cls.corpus=build_index(UNIT/'corpus')
        cls.bindings=v6.bindings_for(UNIT/'corpus');cls.model=json.loads(MODEL_PATH.read_text())

    def inputs(self,task=None,corpus=None,bindings=None):
        return cpi_inputs(task or self.task,corpus or self.corpus,bindings or self.bindings,self.model)

    def test_public_source_has_expected_current_gas_and_all_components(self):
        inputs=self.inputs();self.assertIsNotNone(inputs)
        self.assertEqual(set(inputs['history']),set(IDS));self.assertTrue(all(len(v)==9 for v in inputs['history'].values()))
        self.assertAlmostEqual(inputs['gas'][0],100*((3.136+3.171+3.144+3.097)/4/((3.289+3.236+3.180+3.185+3.179)/5)-1),places=10)

    def test_tree_sensitive_features_match_numpy_exactly(self):
        rng=np.random.default_rng(8)
        for k in range(50):
            history={e:(rng.integers(-20,20,9)/10).tolist() for e in IDS}
            if k==0:history['CPI_CORE']=[.2]*9
            for e in IDS:
                v=history[e];x=features(history,e,10,-2.,-4.,-.5)
                wanted=[*v[-3:],np.mean(v[-3:]),np.mean(v[-6:]),np.mean(v),np.median(v),np.std(v),-2.,-4.,-.5,
                        np.mean(history['CPI_CORE'][-3:]),np.mean(history['CPI_ENERGY'][-3:]),*[float(10==j) for j in range(1,13)]]
                self.assertEqual(x,wanted)

    def test_cutoff_roster_and_horizon_fall_back(self):
        for cutoff in ['2016-12-31','2024-10-30','invalid']:
            self.assertIsNone(self.inputs(task=dict(self.task,cutoff_date=cutoff)))
        task=copy.deepcopy(self.task);task['entities'][0]['ref_month']='2024-11';self.assertIsNone(self.inputs(task=task))
        task=copy.deepcopy(self.task);task['entities'][0]['entity_id']='UNKNOWN';self.assertIsNone(self.inputs(task=task))

    def test_unadmitted_or_future_gas_document_is_not_used(self):
        doc='EIA_GASREGW_20241028';corpus=copy.deepcopy(self.corpus);corpus.doc_dates[doc]='2024-11-01'
        self.assertIsNone(self.inputs(corpus=corpus))
        bindings=copy.deepcopy(self.bindings);bindings[doc]['shared']=False;bindings[doc]['entity_ids']=['CPI_GASOLINE']
        self.assertIsNone(self.inputs(bindings=bindings))

    def test_future_week_does_not_change_inputs(self):
        corpus=copy.deepcopy(self.corpus);doc='EIA_GASREGW_20241028'
        corpus.doc_texts[doc]=corpus.doc_texts[doc].replace('2024-10-28 | 3.097','2024-10-28 | 3.097\n2024-11-04 | 1000.000')
        self.assertEqual(self.inputs(),self.inputs(corpus=corpus))

    def test_entity_order_does_not_change_estimates(self):
        original=self.inputs();task=copy.deepcopy(self.task);task['entities'].reverse();changed=self.inputs(task=task)
        self.assertEqual(forecasts(original['history'],original['month'],original['gas']),
                         forecasts(changed['history'],changed['month'],changed['gas']))


if __name__=='__main__':unittest.main()
