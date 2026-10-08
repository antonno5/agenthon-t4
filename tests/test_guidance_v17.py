import copy,unittest
from agent_submit_v17.guidance_rules import candidates,validate,eligible
class GuidanceTests(unittest.TestCase):
 def row(self,t='TXN'):return dict(ticker=t,target_year=2015,target_quarter=2,cutoff='2015-07-07',recent_period='2015-03-31',source={'status':'ok','publication':{'date':'2015-04-22'}})
 def extract(self,s,r=None):
  r=r or self.row();text,c=candidates(s,r);r['candidates']=c
  for x in c:self.assertEqual(text[slice(*x['span'])],x['literal'])
  return r,c
 def choose(self,r,c):return validate(dict(candidate_id=c['candidate_id'],basis='gaap',period='next_quarter'),r)
 def test_cents_wrapped(self):
  r,c=self.extract('TI second\nquarter outlook is for earnings per\nshare between 60 and 70 cents.')
  self.assertAlmostEqual(self.choose(r,c[0])['midpoint'],.65)
 def test_unknown_units(self):self.assertEqual(self.extract('TI second-quarter outlook is for EPS between 60 and 70.')[1],[])
 def test_wrong_quarter(self):
  r,c=self.extract('TI third-quarter outlook is for EPS between $1.0 and $1.2.')
  with self.assertRaises(ValueError):self.choose(r,c[0])
 def test_wrong_year(self):
  r,c=self.extract('TI second quarter of 2014 outlook is for EPS between $1.0 and $1.2.')
  with self.assertRaises(ValueError):self.choose(r,c[0])
 def test_annual_only(self):
  r,c=self.extract('TI annual outlook is for EPS between $3.0 and $3.2.')
  self.assertFalse(any(eligible(x,r) for x in c))
 def test_non_gaap(self):
  r,c=self.extract('TI second-quarter outlook is for adjusted EPS between $1.0 and $1.2.')
  with self.assertRaises(ValueError):self.choose(r,c[0])
 def test_explicit_fiscal_table(self):
  r=self.row('QCOM');s='Current Guidance Q2 FY15 Estimates\nNon-GAAP diluted EPS $1.28 - $1.40\nGAAP diluted EPS $1.08 - $1.20\nFISCAL YEAR\nGAAP EPS $4.0 - $5.0'
  r,c=self.extract(s,r);self.assertEqual(len(c),2);self.assertAlmostEqual(self.choose(r,c[1])['midpoint'],1.14)
  with self.assertRaises(ValueError):self.choose(r,c[0])
 def test_conflict(self):
  r,c=self.extract('TI second-quarter outlook for EPS between $1.0 and $1.2.\nTI second-quarter outlook for EPS between $2.0 and $2.2.')
  with self.assertRaises(ValueError):self.choose(r,c[0])
 def test_future_source(self):
  r,c=self.extract('TI second-quarter outlook is for EPS between $1.0 and $1.2.');r['source']['publication']['date']='2015-08-01'
  with self.assertRaises(ValueError):self.choose(r,c[0])
 def test_no_model_numbers(self):
  r,c=self.extract('TI second-quarter outlook is for EPS between $1.0 and $1.2.')
  with self.assertRaises(ValueError):validate(dict(candidate_id='C000',basis='gaap',period='next_quarter',midpoint=5),r)
 def test_intel_columns(self):
  r=self.row('INTC');r,c=self.extract('Business Outlook\nQ2 2015 GAAP Non-GAAP Range\nEarnings per share $0.53 $0.68 +/- 5 cents\nFull-Year 2015 GAAP Non-GAAP\nEarnings per share $2.56 $2.85 +/- 5%',r)
  self.assertEqual(len(c),2);self.assertEqual(self.choose(r,c[0])['midpoint'],.53)
  with self.assertRaises(ValueError):self.choose(r,c[1])
 def test_actual_table_excluded(self):
  r,c=self.extract('Financial results\nQ2 2015 GAAP Non-GAAP\nEarnings per share $0.53 $0.68',self.row('INTC'));self.assertEqual(c,[])
if __name__=='__main__':unittest.main()
