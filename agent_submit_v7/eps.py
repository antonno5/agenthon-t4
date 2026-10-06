"""Read GAAP quarterly EPS pairs, preserving offsets into the supplied source.

No company names, task IDs, external facts, or forecast labels occur in these rules.
Ambiguous headers, adjusted earnings and forward guidance are deliberately rejected.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import datetime as dt
import re

NUM = r'(?:\d{1,3}(?:,\d{3})+|\d+|(?=\.\d))(?:\.\d+)?'
CELL = re.compile(r'\s*(?:\$\s*)?(?P<open>\()?\s*(?:\$\s*)?(?P<n>[+\-]?' + NUM + r')\s*(?P<close>\))?\s*(?P<pct>%)?')
QUARTER = re.compile(r'\b(?:three\s*(?:and\s+(?:six|nine)\s*)?months?\s+ended|quarters?\s+ended|(?:first|second|third|fourth)\s+quarter)\b', re.I)
YEAR = re.compile(r'\b(?:19|20)\d{2}\b')
DATE = re.compile(r'\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b', re.I)
MONTHS = {m.lower(): i for i, m in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], 1)}
EPS_ROW = re.compile(
    r'\b(?:diluted\s+(?:earnings|net\s+(?:income|loss))\s+per\s+(?:common\s+)?share'
    r'|earnings(?:\s*\(loss\))?\s+per\s+(?:common\s+)?share(?:\s+of\s+common\s+stock)?\s*[—–-]\s*(?:assuming\s+dilution|diluted)'
    r'|(?:basic\s+and\s+)?diluted(?:\s+EPS)?|assuming\s+dilution)\b', re.I)
BAD = re.compile(r'\b(?:adjusted|non[ -]?GAAP|guidance|forecast|expected|expects?|projected|would\s+have|pro\s+forma)\b', re.I)


@dataclass(frozen=True)
class EPSPair:
    current: float
    previous_year: float
    period: str
    doc_id: str
    start: int
    end: int
    header_start: int
    header_end: int
    method: str


def clean(text: str) -> str:
    # One character in, one character out: exact source offsets remain valid.
    return text.translate(str.maketrans({'\u200b': ' ', '\u200c': ' ', '\ufeff': ' ', '\xa0': ' ', '−': '-'}))


def leading_values(text: str, start: int, limit: int = 10):
    """Only a contiguous numeric row; do not jump over unrelated words."""
    pos = start
    note = re.match(r'\s*\([a-z0-9]{1,2}\)\s*(?=\$|[+\-.\d])', text[pos:], re.I)
    if note:
        pos += note.end()
    values = []
    for _ in range(limit):
        m = CELL.match(text, pos)
        if not m or bool(m['open']) != bool(m['close']):
            break
        raw = m['n']
        value = float(raw.replace(',', '')) * (-1 if m['open'] else 1)
        if m['pct'] or abs(value) >= 1000:
            break
        values.append(value)
        pos = m.end()
    return values, pos


def quarterly_header(text: str, row_start: int, period: str):
    """Require explicit consecutive year columns and a quarterly heading.

    Multi-quarter comparisons with current and previous quarter columns are
    ambiguous unless another unambiguous table exists in the same document.
    """
    lower = max(0, row_start - 18000)
    headers = list(QUARTER.finditer(text, lower, row_start))
    for match in reversed(headers):
        stop = min(row_start, match.end() + 500)
        head = text[match.start():stop]
        # Never reach backwards through a newer annual-only table.
        between = text[match.end():row_start]
        if re.search(r'\b(?:years? ended|twelve months ended)\b', between, re.I):
            return None
        years = list(YEAR.finditer(head))
        if len(years) < 2:
            continue
        y0, y1 = int(years[0][0]), int(years[1][0])
        if y0 != int(period[:4]) or y1 != y0 - 1:
            # Do not try an older header when the nearest usable one disagrees.
            return None
        dates = list(DATE.finditer(head))
        if dates:
            first = dates[0]
            date = f'{int(first[3]):04d}-{MONTHS[first[1][:3].lower()]:02d}-{int(first[2]):02d}'
            if abs((dt.date.fromisoformat(date) - dt.date.fromisoformat(period)).days) > 10:
                return None
            if len(dates) >= 2:
                second = dates[1]
                previous = dt.date(int(second[3]), MONTHS[second[1][:3].lower()], int(second[2]))
                if not 340 <= (dt.date.fromisoformat(date) - previous).days <= 390:
                    return None
        end = match.start() + years[1].end()
        if end - match.start() > 650:
            return None
        return match.start(), end
    return None


def extract_pair(doc_id: str, original: str, metadata: dict, cutoff: str):
    period = metadata.get('period_of_report')
    if not isinstance(period, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', period) or period > cutoff:
        return None
    if metadata.get('doc_date', cutoff) > cutoff:
        return None
    text = clean(original)
    candidates = []
    for match in EPS_ROW.finditer(text):
        context = text[max(0, match.start()-240):match.start()]
        if BAD.search(context[-100:]) or re.search(r'\bweighted.?average\b|\bshares\s+(?:outstanding|used)', context[-85:], re.I):
            continue
        if re.search(r'per\s+share\s+from\s+continuing\s+operations', context[-130:], re.I):
            continue
        direct = re.search(r'per\s+(?:common\s+)?share|\bEPS\b', match[0], re.I)
        if not direct and not re.search(r'earnings|per\s+(?:common\s+)?share|\bEPS\b', context, re.I):
            continue
        row_start = match.end()
        punctuation = re.match(r'\s*:\s*', text[row_start:])
        if punctuation:
            row_start += punctuation.end()
        # Citigroup-like total net-income subsection, and IBM-like total EPS.
        tail = text[row_start:row_start+450]
        if re.match(r'\s*(?:income from continuing operations|continuing operations)', tail, re.I):
            total = re.search(r'\b(?:Net income|Total)\s*(?=\$|[+\-.(\d])', tail, re.I)
            if not total:
                continue
            row_start += total.end()
        elif re.match(r'\s*(?:was|were|of)\b', tail, re.I):
            # Paired table values only. A prose observation without an explicit
            # comparator remains on V6's separate conservative prose route.
            continue
        values, end = leading_values(text, row_start)
        if len(values) < 2:
            continue
        header = quarterly_header(text, match.start(), period)
        if header is None:
            continue
        current, previous = values[:2]
        if max(abs(current), abs(previous)) > 100:
            continue
        # A single ambiguous row must not override repeated agreement in EPS notes.
        pair = EPSPair(current, previous, period, doc_id,
                       max(0, match.start()-100), min(len(original), end+50, match.start()+850),
                       *header, 'quarterly-gaap-table')
        candidates.append(pair)
    if not candidates:
        return None
    counts = Counter((p.current, p.previous_year) for p in candidates)
    ordered = counts.most_common()
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None  # conflicting equal-support GAAP rows: retain the baseline
    winner = ordered[0][0]
    return next(p for p in candidates if (p.current, p.previous_year) == winner)


def latest_pair(task: dict, corpus, allowed: list[str]):
    found = []
    for doc_id in allowed:
        metadata = dict(corpus.doc_meta[doc_id], doc_date=corpus.doc_dates[doc_id])
        result = extract_pair(doc_id, corpus.doc_texts[doc_id], metadata, task['cutoff_date'])
        if result:
            found.append(result)
    if not found:
        return None
    return max(found, key=lambda p: (p.period, corpus.doc_dates[p.doc_id], p.doc_id))


def seasonal_forecast(prior_target: float, pair: EPSPair) -> float:
    """Equal blend of seasonal no-change and the latest seasonal-difference rule."""
    return prior_target + .5 * (pair.current - pair.previous_year)
