"""Authenticate using an authorized private file; never print credentials or cookies."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

class LoginForm(HTMLParser):
    csrf=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='input' and attrs.get('name')=='csrfmiddlewaretoken':self.csrf=attrs.get('value')

def main():
    p=argparse.ArgumentParser();p.add_argument('--credentials',type=Path,required=True);p.add_argument('--cookies',type=Path,required=True);a=p.parse_args()
    fields={}
    for line in a.credentials.read_text().splitlines():
        m=re.match(r'^[-*\s]*([^:`]{1,70}):\s*(.*)$',line)
        if m:fields[m[1].strip().strip('*')]=m[2].strip().strip('`').strip()
    username=fields['Логин или email назначенного аккаунта команды'];password=fields['Пароль']
    origin='https://www.codabench.org';url=origin+'/accounts/login/'
    jar=http.cookiejar.MozillaCookieJar(str(a.cookies));opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    with opener.open(url,timeout=45) as r:form=LoginForm();form.feed(r.read().decode())
    assert form.csrf
    data=urllib.parse.urlencode(dict(username=username,password=password,csrfmiddlewaretoken=form.csrf)).encode()
    req=urllib.request.Request(url,data=data,headers={'Referer':url,'Origin':origin})
    with opener.open(req,timeout=45) as r:r.read()
    with opener.open(origin+'/api/my_profile/',timeout=45) as r:profile=json.load(r)
    assert profile.get('username')=='imak_ai_lab','Wrong designated account'
    a.cookies.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(a.cookies,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600);os.close(fd);os.chmod(a.cookies,0o600)
    jar.save(ignore_discard=True,ignore_expires=True)
    print(json.dumps(dict(authenticated=True,account=profile['username'])))

if __name__=='__main__':
    try:main()
    except Exception as e:
        print(json.dumps(dict(error=type(e).__name__,status=getattr(e,'code',None))))
        raise SystemExit(1) from None
