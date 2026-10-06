"""One authorized Development upload. Session secrets stay in a private cookie jar."""
import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ORIGIN = 'https://www.codabench.org'
PHASE = 29649
COMPETITION = 17768


def safe_submission(data):
    return {key: data.get(key) for key in ['id', 'phase', 'status', 'status_details', 'created_when', 'owner', 'filename', 'scores']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['preflight', 'upload', 'status'])
    parser.add_argument('--cookies', type=Path, required=True)
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    jar = http.cookiejar.MozillaCookieJar(str(args.cookies))
    jar.load(ignore_discard=True, ignore_expires=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    csrf = next(cookie.value for cookie in jar if cookie.name == 'csrftoken' and cookie.domain.lstrip('.') in ['www.codabench.org', 'codabench.org'])
    def api(path, payload=None, method='GET'):
        data = None if payload is None else json.dumps(payload).encode()
        headers = {'Referer': ORIGIN + f'/competitions/{COMPETITION}/', 'Origin': ORIGIN,
                   'Content-Type': 'application/json', 'Accept': 'application/json',
                   'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf}
        req = urllib.request.Request(ORIGIN + '/api/' + path.lstrip('/'), data=data, headers=headers, method=method)
        with opener.open(req, timeout=60) as response:
            body = response.read()
            return json.loads(body) if body else {}
    if args.action == 'status' or args.action == 'upload' and args.receipt.exists():
        receipt = json.loads(args.receipt.read_text())
        if not receipt.get('submission_id'):
            raise RuntimeError('An upload was already started. Reconcile its status before any retry.')
        data = safe_submission(api(f'submissions/{receipt["submission_id"]}/'))
        print(json.dumps(data))
        args.receipt.with_name('latest-status.json').write_text(json.dumps(data, indent=2) + '\n')
        return
    phase = api(f'phases/{PHASE}/')
    assert phase['id'] == PHASE and phase['name'] == 'Development' and phase['status'] == 'Current'
    permission = api(f'can_make_submission/{PHASE}/')
    assert permission.get('can') is True, 'Platform does not currently allow a submission'
    profile = api('my_profile/')
    assert profile.get('username') == 'imak_ai_lab', 'Wrong designated account'
    if args.action == 'preflight':
        print(json.dumps(dict(competition=COMPETITION, phase=PHASE, account=profile['username'], allowed=True)))
        return
    assert args.zip and args.zip.is_file()
    payload = args.zip.read_bytes()
    receipt = dict(competition=COMPETITION, phase=PHASE, account=profile['username'], filename=args.zip.name,
                   zip_sha256=hashlib.sha256(payload).hexdigest(), started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                   state='upload_started', submission_id=None)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive ledger prevents a second POST when a network response is lost.
    with args.receipt.open('x') as handle:
        json.dump(receipt, handle, indent=2)
    # Match the current first-party web uploader, including the competition relation.
    dataset = api('datasets/', dict(type='submission', competition=COMPETITION,
                                   request_sassy_file_name=args.zip.name, file_name=args.zip.name,
                                   file_size=len(payload)), 'POST')
    receipt.update(dataset_key=dataset['key'], state='dataset_created')
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    destination = urllib.parse.urlparse(dataset['sassy_url'])
    assert destination.scheme == 'https', 'Upload target must be HTTPS'
    # No CodaBench cookies, CSRF header or team key go to the storage service.
    request = urllib.request.Request(dataset['sassy_url'], data=payload, method='PUT', headers={'Content-Type': 'application/zip'})
    with urllib.request.urlopen(request, timeout=90) as response:
        assert 200 <= response.status < 300
    api(f'datasets/completed/{dataset["key"]}/', method='PUT')
    receipt.update(state='submission_post_started')
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    submission = api('submissions/', dict(data=dataset['key'], phase=PHASE), 'POST')
    receipt.update(submission_id=submission['id'], state='submitted',
                   competition_url=ORIGIN + f'/competitions/{COMPETITION}/#participate-submit_results')
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(submission_id=submission['id'], status=submission.get('status'), phase=PHASE,
                          competition_url=receipt['competition_url'])))


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        print(json.dumps(dict(error='HTTPError', status=error.code)))
        raise SystemExit(1) from None
