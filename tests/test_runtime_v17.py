import copy,datetime as dt,json,unittest
from types import SimpleNamespace
from agent_submit_v17.routing import canonicalize
from agent_submit_v17.guidance import forecast,mapped_text,claims
from agent_submit_v17.guidance_rules import canonical,candidates
from agent_submit_v17.numeric import predict,MODEL_PATH
class RuntimeTests(unittest.TestCase):
 def fixture(self):
  task={'cutoff_date':'2023-07-07'};entity={'entity_id':'TXN','cik':'0000097476','quarter_reported':'three months ended 2023-06-30'}
  text='April 20, 2023\nTI first-quarter results.\n“TI’s second quarter outlook is for earnings per\n share between $1.20 and $1.40.”'
  corpus=SimpleNamespace(doc_texts={'A':text},doc_dates={'A':'2023-04-20'});return task,entity,corpus
 def test_original_offset_quotes(self):
  t,e,c=self.fixture();f=forecast(t,e,c,['A']);self.assertAlmostEqual(f['value'],1.3)
  for claim in f['claims']:self.assertEqual(c.doc_texts['A'][claim['span_start']:claim['span_end']],claim['claim'])
 def test_future_or_unbound_source_never_used(self):
  t,e,c=self.fixture();self.assertIsNone(forecast(t,e,c,[]));c.doc_dates['A']='2023-07-08';self.assertIsNone(forecast(t,e,c,['A']))
 def test_source_before_relevant_quarter_rejected(self):
  t,e,c=self.fixture();c.doc_dates['A']='2022-04-20';self.assertIsNone(forecast(t,e,c,['A']))
 def test_training_guard(self):
  r=dict(eps=[2.,None,None,1.,1.5,None,None,None],prior=1.,metrics={},scale=1.,split_warning=False)
  self.assertIsNone(predict(r,{},'2022-12-31'));self.assertIsNotNone(predict(r,{},'2023-01-01'))
 def test_guidance_guard(self):
  t,e,c=self.fixture();t['cutoff_date']='2021-07-07';self.assertIsNone(forecast(t,e,c,['A']))
 def test_conflicting_sources_fail_closed(self):
  t,e,c=self.fixture();c.doc_texts['B']=c.doc_texts['A'].replace('$1.20 and $1.40','$2.20 and $2.40');c.doc_dates['B']=c.doc_dates['A'];self.assertIsNone(forecast(t,e,c,['A','B']))
 def test_withdrawal(self):
  t,e,c=self.fixture();c.doc_texts['B']='The company withdraws its earnings guidance.';c.doc_dates['B']='2023-05-01';self.assertIsNone(forecast(t,e,c,['A','B']))
 def test_previous_quarter_boundary_in_september(self):
  t,e,c=self.fixture();t['cutoff_date']='2023-10-07';e['quarter_reported']='2023-09-30';c.doc_dates['A']='2023-07-21';c.doc_texts['A']=c.doc_texts['A'].replace('second quarter','third quarter');self.assertIsNotNone(forecast(t,e,c,['A']))
 def test_whitespace_mapping(self):
  for s in [' a\t b\r\n \n c\x0c d\n','\n\n 100  to\u00a0200','a\vb\rc\n','']:
   normalized,mapping=mapped_text(s);self.assertEqual(normalized,canonical(s));self.assertEqual(len(normalized),len(mapping))
 def test_typed_alias_and_no_mutation(self):
  t={'family':'eps_yoy_direction','target':{'name':'opaque','type':'classification','labels':['up','down']}};old=copy.deepcopy(t);new,route=canonicalize(t);self.assertEqual(new['target']['name'],'eps_yoy_direction');self.assertEqual(t,old)
 def test_incompatible_family_type_or_labels(self):
  for typ,labels in [('regression',[]),('classification',['yes','no'])]:
   t={'family':'eps_yoy_direction','target':{'name':'opaque','type':typ,'labels':labels}};self.assertIs(canonicalize(t)[0],t)
 def test_unsupported_spec_preserved(self):
  t={'family':'unknown','target':{'name':'opaque','type':'regression'},'prompt':'Predict sales.'};self.assertIs(canonicalize(t)[0],t)
if __name__=='__main__':unittest.main()
