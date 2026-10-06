import unittest
from lab.v9_accounting import flow_at,unique_latest
from lab.v9_features import vector

def record(start,end,filed,value,accn='A'):
    return dict(start=start,end=end,filed=filed,val=value,accn=accn,form='10-Q')
def data(rows):
    return {'facts':{'us-gaap':{'NetCashProvidedByUsedInOperatingActivities':{'units':{'USD':rows}}}}}
class QuarterlyAccounting(unittest.TestCase):
    def test_ytd_difference_uses_available_versions_only(self):
        rows=[record('2019-01-01','2019-03-31','2019-05-01',100),record('2019-01-01','2019-06-30','2019-08-01',260),
              record('2019-01-01','2019-03-31','2020-05-01',999,'B')]
        value,used,method=flow_at(data(rows),['NetCashProvidedByUsedInOperatingActivities'],'2019-06-30','2019-09-01')
        self.assertEqual(value,160);self.assertEqual(method,'ytd-difference')
        self.assertTrue(all(r['filed']<='2019-09-01' for r in used))
    def test_cannot_subtract_unrelated_fiscal_years(self):
        rows=[record('2018-01-01','2019-03-31','2019-05-01',100),record('2019-01-01','2019-06-30','2019-08-01',260)]
        value,_,_=flow_at(data(rows),['NetCashProvidedByUsedInOperatingActivities'],'2019-06-30','2019-09-01')
        self.assertIsNone(value)
    def test_direct_quarter_preferred(self):
        rows=[record('2019-04-01','2019-06-30','2019-08-01',160)]
        self.assertEqual(flow_at(data(rows),['NetCashProvidedByUsedInOperatingActivities'],'2019-06-30','2019-09-01')[0],160)
    def test_ambiguous_latest_rejected(self):
        a=record('2019-04-01','2019-06-30','2019-08-01',160)
        self.assertIsNone(unique_latest([a,dict(a,val=161)]))
    def test_identity_and_future_target_not_features(self):
        row=dict(eps=[1.]*8,prior=1.,scale=1.,metrics={},split_warning=False)
        self.assertEqual(vector(row),vector(dict(row,cik='PRIVATE',cutoff='2099-01-01',y=999)))
    def test_compact_never_uses_accounting(self):
        row=dict(eps=[1.]*8,prior=1.,scale=1.,metrics={},split_warning=False)
        self.assertEqual(vector(row,'compact'),vector(dict(row,accounting={'operating':[1e9]*8,'shares':[1.]*8}),'compact'))

if __name__=='__main__':unittest.main()
