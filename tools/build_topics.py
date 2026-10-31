# -*- coding: utf-8 -*-
"""공개 데이터 → 10주제 × 5문항.

**모든 숫자는 raw/ 의 원본에서 계산합니다.** 지어낸 값이 하나도 없어야 합니다.
결과는 앱이 읽는 topics/*.json 과, 사람이 읽는 tools/정답지.md 로 나갑니다.

정답지와 이 스크립트는 .vercelignore 에 들어 있어 **배포되지 않습니다.**
공개 URL 에 정답지가 올라가면 게임이 성립하지 않습니다.

실행 (저장소 최상위에서):
    python tools/build_topics.py
    python tools/build_topics.py --only marriage-30s    # 그 주제만 다시 계산
    python tools/build_topics.py --only ddareungi-commute   # 원본 3.4GB 라 1~2분 걸림
    python tools/build_topics.py --only commute-time
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import sys
import datetime as dt
from collections import Counter
from pathlib import Path
from statistics import mean

# 윈도우 콘솔(cp949)은 이모지 · 기호를 못 찍고 멈춘다. 출력만 UTF-8 로 맞춘다
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE = Path(__file__).resolve().parent          # tools/
APP = HERE.parent                                # 저장소 최상위 = 배포되는 곳
RAW = APP / "data" / "raw"
OUT = APP / "topics"

TOPICS: list[dict] = []
# 앱 첫 화면에서 다른 주제보다 위에 놓을 주제 (이 순서대로)
FIRST = ("marriage-30s", "ddareungi-commute", "commute-time")


def load_json(name):
    return json.load(io.open(RAW / name, encoding="utf-8"))


def load_csv(name):
    return list(csv.DictReader(io.open(RAW / name, encoding="utf-8")))


def wb_countries(rows, year):
    """그 해의 실제 국가 값만 남긴다 (집계치 제외)."""
    return {r["country"]["value"]: r["value"] for r in rows
            if int(r["date"]) == year and r["countryiso3code"] in REAL}


def owid_countries(rows, year, col):
    """OWID 도 마찬가지. code 가 비었거나 OWID_ 로 시작하면 집계치다."""
    return {r["entity"]: float(r[col]) for r in rows
            if int(r["year"]) == year and r["code"]
            and not r["code"].startswith("OWID")}


def topic(tid, emoji, title, blurb, source, source_url, questions, caveat=""):
    """caveat = 이 데이터를 믿을 때의 한계. 앱 화면에도 그대로 나간다.

    출처가 다르면 같은 '서울 기온'도 값이 다르다. 그 사실을 감추지 않는다.
    """
    TOPICS.append({"id": tid, "emoji": emoji, "title": title, "blurb": blurb,
                   "source": source, "source_url": source_url,
                   "caveat": caveat, "questions": questions})


def slider(qid, text, answer, unit, lo, hi, step, basis, why):
    return {"id": qid, "type": "slider", "text": text, "unit": unit,
            "min": lo, "max": hi, "step": step,
            "answer": round(float(answer), 1), "basis": basis, "why": why}


def choice(qid, text, options, answer, basis, why):
    assert answer in options, f"{qid}: 정답이 선택지에 없습니다"
    return {"id": qid, "type": "choice", "text": text, "options": options,
            "answer": answer, "basis": basis, "why": why}


def write(topics: list[dict], only: str | None = None) -> None:
    """topics/*.json · topics.json · 정답지.md 를 쓴다.

    only 를 주면 그 주제의 파일만 쓰고, 목록과 정답지에서는 그 주제 칸만 바꾼다.
    다른 주제는 다시 계산하지도, 고쳐 쓰지도 않는다.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    mine = {}
    for t in topics:
        assert t["questions"], f"{t['id']}: 문항이 없습니다"   # 앱은 문항 수에 상관없이 돈다
        pack = {k: t[k] for k in ("id", "emoji", "title", "blurb",
                                  "source", "source_url", "caveat")}
        pack["questions"] = t["questions"]
        io.open(OUT / f"{t['id']}.json", "w", encoding="utf-8").write(
            json.dumps(pack, ensure_ascii=False, indent=2))
        mine[t["id"]] = {k: t[k] for k in ("id", "emoji", "title", "blurb",
                                           "source")}

    # 제목·부제는 화면을 바꾸며 고친 값을 지킨다 (2장에서 내 제목으로 바꾼다).
    # 다시 계산해도 내 제목이 «감 테스트»로 돌아가지 않게, 있던 값을 읽어 쓴다
    old = {}
    if (APP / "topics.json").exists():
        try:
            old = json.load(io.open(APP / "topics.json", encoding="utf-8"))
        except ValueError:
            old = {}
    # 한 주제만 쓸 때는 있던 목록에서 그 주제만 바꾸고(없으면 끝에 붙이고) 나머지는 그대로 둔다
    index = ([mine.pop(x["id"], x) for x in old.get("topics", [])] + list(mine.values())
             if only else list(mine.values()))
    # 내 주제는 목록 맨 위에 둔다 (FIRST 순서대로). 나머지는 원래 순서 그대로
    index.sort(key=lambda x: FIRST.index(x["id"]) if x["id"] in FIRST else len(FIRST))
    io.open(APP / "topics.json", "w", encoding="utf-8").write(json.dumps({
        "title": old.get("title", "감 테스트"),
        "subtitle": old.get("subtitle", "숫자에 대한 당신의 감은 몇 점입니까"),
        # 등급·문구는 여기서 고칩니다. 코드를 건드릴 일이 아닙니다
        "grades": [
            {"min": 90, "name": "촉이 데이터급", "emoji": "🎯"},
            {"min": 70, "name": "감이 좋은 편", "emoji": "📊"},
            {"min": 50, "name": "보통의 감각", "emoji": "🙂"},
            {"min": 30, "name": "느낌대로 삽니다", "emoji": "🎲"},
            {"min": 0, "name": "감은 접어두시죠", "emoji": "🙈"},
        ],
        "reactions_choice": {"hit": "맞히셨습니다", "miss": "다들 그렇게 찍습니다"},
        "reactions": [
            {"max": 5, "text": "촉이 좋으시네요"},
            {"max": 20, "text": "비슷하게 보셨습니다"},
            {"max": 60, "text": "음…"},
            {"max": 999, "text": "꽤 멀리 가셨습니다"},
        ],
        "topics": index,
    }, ensure_ascii=False, indent=2))

    # 사람이 읽는 정답지 — 주제마다 «## 이모지 제목» 으로 시작하는 칸 하나
    def section(t):
        md = [f"## {t['emoji']} {t['title']}", "",
              f"- 출처: {t['source']} · {t['source_url']}"]
        if t["caveat"]:
            md += [f"- **한계** {t['caveat']}"]
        md += [""]
        for q in t["questions"]:
            a = f"{q['answer']}{q.get('unit', '')}" if q["type"] == "slider" \
                else q["answer"]
            md += [f"**{q['text']}**", "",
                   f"- 정답 **{a}**", f"- 근거 {q['basis']}",
                   f"- 왜 틀리나 {q['why']}", ""]
        return "\n".join(md) + "\n"

    sheet = HERE / "정답지.md"
    if only and sheet.exists():
        parts = re.split(r"(?m)^(?=## )", sheet.read_text(encoding="utf-8"))
        for t in topics:
            new, head = section(t), f"## {t['emoji']} {t['title']}\n"
            at = [i for i, p in enumerate(parts) if p.startswith(head)]
            if at:
                parts[at[0]] = new
            else:
                parts[-1] = parts[-1].rstrip("\n") + "\n\n"
                parts.append(new)
        text = "".join(parts)
    else:
        text = "\n".join(["# 문항 정답지 — 10주제 50문항", "",
                          "> 모든 값은 `data/raw/` 의 원본에서 `tools/build_topics.py` 가 계산합니다.",
                          ""]) + "\n" + "".join(section(t) for t in topics)
    sheet.write_text(text.rstrip("\n") + "\n", encoding="utf-8")

    print(f"주제 {len(topics)}개 · 문항 {sum(len(t['questions']) for t in topics)}개")
    for t in topics:
        print(f"\n{t['emoji']} {t['title']}  ({t['source']})")
        for q in t["questions"]:
            a = f"{q['answer']}{q.get('unit', '')}" if q["type"] == "slider" \
                else q["answer"]
            print(f"    [{q['type'][:6]:<6}] {q['text'][:44]:<44} → {a}")


# ── 30대의 혼인율 ────────────────────────────────────────────────
# KOSIS 화면에서 받은 CSV(CP949). 머리글이 두 줄이다 — 1줄은 연도, 2줄은 남편·아내.
# 이 표에는 혼인율(해당 연령 천 명당 건)만 있고 혼인 건수·인구·다른 연령대는 없다.
# 그래서 30~34세와 35~39세, 남편과 아내를 하나의 «30대»로 합치지 않는다. 인구를
# 모르면 가중평균을 낼 수 없고, 단순평균은 인구가 다른 집단을 같은 무게로 섞는다.
# 숫자는 모두 전국(계) 줄에서 센다
def marriage_30s() -> None:
    rows = list(csv.reader(io.open(RAW / "kosis_marriage_age.csv", encoding="cp949")))
    R = {}                       # (시도, 연령, 남편|아내, 연도) → 천 명당 건
    for place, age, *vals in rows[2:]:
        for y, s, v in zip(rows[0][2:], rows[1][2:], vals):
            if v.strip() not in ("", "-"):
                R[place, age, s[:2], int(y)] = float(v)
    A1, A2 = "30 - 34세", "35 - 39세"
    AGE = {A1: "30~34세", A2: "35~39세"}
    SEX = {"남편": "남성", "아내": "여성"}

    def kr(age, sex, y):
        return R[("계", age, sex, y)]

    # 네 집단(두 연령대 × 남편·아내)의 값이 모두 있는 해만 쓴다. Y 는 그중 가장 최근
    ys = sorted(y for y in {k[3] for k in R}
                if all(("계", a, s, y) in R for a in AGE for s in SEX))
    Y = ys[-1]

    def sex_q(qid, age):
        m, f = kr(age, "남편", Y), kr(age, "아내", Y)
        assert m != f, f"{qid}: 남녀 혼인율이 같아 정답을 정할 수 없습니다"
        f_up = [y for y in ys if kr(age, "아내", y) > kr(age, "남편", y)]
        return m, f, ("남성" if m > f else "여성"), f_up

    m1, f1, ans2a, f_up1 = sex_q("m2a", A1)
    m2, f2, ans2b, f_up2 = sex_q("m2b", A2)

    # 3번: 남녀를 합치지 않고 따로 비교한다. 둘의 답이 다르면 정답을 정할 수 없다
    older = {s: AGE[A1] if kr(A1, s, Y) > kr(A2, s, Y) else AGE[A2] for s in SEX}
    assert len(set(older.values())) == 1, "m3: 남녀에서 혼인율이 높은 연령대가 달라 정답을 정할 수 없습니다"
    ans3 = older["남편"]

    # 4번: 30~34세 남성 혼인율이 가장 낮았던 해 (1번과 같은 집단)
    low = min(ys, key=lambda y: kr(A1, "남편", y))
    high = max(ys, key=lambda y: kr(A1, "남편", y))
    # 보기는 처음 해 · 코로나 첫해(2020) · 마지막 해에 정답을 더해 넷을 채운다.
    # 겹쳐서 넷이 안 되면 앞쪽 해부터 빈자리를 채운다
    opts = {ys[0], 2020, Y, low} & set(ys)
    for y in ys:
        if len(opts) >= 4:
            break
        opts.add(y)

    cur = kr(A1, "남편", Y)

    # 5번: 30~34세 혼인율이 가장 높은 시도. 남녀를 합치지 않고 따로 1위를 찾아,
    # 둘이 같은 곳일 때만 문항으로 쓴다 (다르면 정답을 정할 수 없다)
    places = sorted({k[0] for k in R} - {"계"})
    first = {}
    for s in SEX:
        rank = sorted(places, key=lambda p: R.get((p, A1, s, Y), -1), reverse=True)
        assert R[rank[0], A1, s, Y] != R[rank[1], A1, s, Y], f"m5: {s} 1위가 둘입니다"
        first[s] = rank[0]
    assert first["남편"] == first["아내"], "m5: 남녀의 1위 시도가 달라 정답을 정할 수 없습니다"
    top_place = first["남편"]
    # 보기는 남녀 혼인율을 더한 값이 큰 순서로 넷 (보기를 고르는 데만 쓰고 정답과는 무관)
    by_sum = sorted(places, key=lambda p: R[p, A1, "남편", Y] + R[p, A1, "아내", Y],
                    reverse=True)
    place_opts = sorted(by_sum[:4] if top_place in by_sum[:4] else by_sum[:3] + [top_place])
    runner = {s: sorted(places, key=lambda p: R[p, A1, s, Y], reverse=True)[1] for s in SEX}

    topic(
        "marriage-30s", "💍", "30대의 혼인율",
        f"{ys[0]}~{Y}년, 전국 30대 초·후반 남녀의 혼인율",
        "KOSIS 국가통계포털 (통계청 인구동향조사)",
        "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1B83A15&vw_cd=MT_ZTITLE&list_id=A23_1",
        [
            slider("m1", f"{Y}년, 30대 초반(30~34세) 남성 1,000명을 한 강당에 모았습니다. 그해 혼인신고를 "
                   "한 사람은 몇 명일까요?",
                   cur, "명", 0, 100, 1,
                   f"{Y}년 전국 30~34세 남성의 혼인율(남편 기준, 해당 연령 남성 천 명당 "
                   f"혼인 건수) {cur:.1f}건을 그대로 씀",
                   "혼인율은 그해 새로 혼인한 사람의 비율입니다. 이미 결혼해 있는 사람이 "
                   "얼마나 되는지와는 다른 숫자입니다."),
            choice("m2a", f"{Y}년 30대 초반(30~34세)의 결혼 레이스! 혼인율로 따지면 남성과 여성 중 누가 "
                   "앞섰을까요?",
                   ["남성", "여성"], ans2a,
                   f"{Y}년 전국 30~34세 해당 연령 천 명당 혼인 건수를 남녀 각각 세면 "
                   f"남성 {m1:.1f}건 · 여성 {f1:.1f}건"
                   + (f" (여성이 더 높았던 해: {', '.join(map(str, f_up1))}년)" if f_up1 else ""),
                   "아내가 남편보다 어린 부부가 많아서, 같은 나이대라도 남녀의 혼인율이 "
                   "다르게 나옵니다."),
            choice("m2b", f"그럼 30대 후반(35~39세)에서는요? {Y}년 혼인율이 더 높은 쪽은 남성과 여성 중 "
                   "어디일까요?",
                   ["남성", "여성"], ans2b,
                   f"{Y}년 전국 35~39세 해당 연령 천 명당 혼인 건수를 남녀 각각 세면 "
                   f"남성 {m2:.1f}건 · 여성 {f2:.1f}건"
                   + (f" (여성이 더 높았던 해: {', '.join(map(str, f_up2))}년)" if f_up2 else ""),
                   "30대 초반의 답이 30대 후반에도 그대로 맞는다고 볼 수는 없습니다. "
                   "나이대를 나눠 봐야 보입니다."),
            choice("m3", "요즘 결혼은 늦다던데… 사람들은 주로 언제 결혼할까요? 30대 초중반? 후반?",
                   ["30~34세", "35~39세"], ans3,
                   f"{Y}년 전국 해당 연령 천 명당 혼인 건수를 남녀 따로 비교하면 남성 "
                   f"30~34세 {kr(A1, '남편', Y):.1f}건 · 35~39세 {kr(A2, '남편', Y):.1f}건, "
                   f"여성 30~34세 {kr(A1, '아내', Y):.1f}건 · 35~39세 {kr(A2, '아내', Y):.1f}건으로 "
                   f"남녀 모두 {ans3}가 높음",
                   "'요즘은 결혼이 늦다'는 말만으로는 30대 초반과 후반 중 어디가 더 높은지 "
                   "알 수 없습니다. 나이대별로 세어 봐야 압니다."),
            choice("m4", f"{ys[0]}~{Y}년, 30대 초반(30~34세) 남성의 결혼이 가장 꽁꽁 얼어붙었던(혼인율이 "
                   "가장 낮았던) 해는 언제일까요?",
                   [f"{y}년" for y in sorted(opts)], f"{low}년",
                   f"{ys[0]}~{Y}년 전국 30~34세 남성 혼인율(해당 연령 천 명당 건)을 해마다 "
                   f"비교하면 가장 낮은 해는 {low}년 {kr(A1, '남편', low):.1f}건 "
                   f"(가장 높은 해는 {high}년 {kr(A1, '남편', high):.1f}건)",
                   "코로나로 결혼식을 미룬 해를 떠올리기 쉽지만, 바닥이 언제였는지는 "
                   "해마다 세어 봐야 압니다."),
            choice("m5", f"{Y}년 30대 초반(30~34세) 결혼 열기가 가장 뜨거웠던 시도는 어디일까요? "
                   "(혼인율 남녀 모두 1위)",
                   place_opts, top_place,
                   f"{Y}년 17개 시도의 30~34세 해당 연령 천 명당 혼인 건수를 남녀 따로 세면 "
                   f"남성 1위 {top_place} {R[top_place, A1, '남편', Y]:.1f}건(2위 {runner['남편']} "
                   f"{R[runner['남편'], A1, '남편', Y]:.1f}건) · 여성 1위 {top_place} "
                   f"{R[top_place, A1, '아내', Y]:.1f}건(2위 {runner['아내']} "
                   f"{R[runner['아내'], A1, '아내', Y]:.1f}건)",
                   "사람이 많은 큰 도시를 먼저 떠올리기 쉽지만, 혼인율은 그 나이대 인구로 "
                   "나눈 값이라 인구가 많은 곳이 높다는 보장이 없습니다."),
        ],
        caveat="이 표에는 혼인율(해당 연령 천 명당 혼인 건수)만 있고 혼인 건수·인구는 "
               "없습니다. 그래서 30~34세와 35~39세, 남녀를 합친 '30대 전체' 혼인율은 내지 "
               "않고 집단마다 따로 셌습니다. 시도를 묻는 마지막 문항 말고는 모두 전국 "
               "기준입니다. "
               "다른 곳의 숫자와 다르다면, 여기 혼인은 혼인한 해가 아니라 신고한 해로 세고 "
               "소수 첫째 자리에서 반올림한 집단별 비율이라 30대 전체·남녀 합계 혼인율이나 "
               f"혼인 건수와는 다르며, {Y}년 값은 잠정인지 확정인지 원본에 표시가 없기 "
               "때문입니다.")


# ── 따릉이 출퇴근 시간대 대여소 ──────────────────────────────────
# 서울 열린데이터광장 OA-15245 시간대별 이용정보 2025년 12개월 (CP949, 약 3.4GB).
# 한 줄은 대여 한 건이 아니라 (날짜 · 시 · 대여소 · 이용권 · 성별 · 연령대) 한 묶음이고,
# 그 묶음의 대여 수가 «이용건수» 칸에 있다. 그래서 줄 수가 아니라 이용건수를 더한다.
# 대여소는 대여 시작 대여소다. 번호가 아니라 **이름**으로 구분한다 — 230번처럼 번호는
# 같아도 이름이 바뀐(자리를 옮긴) 곳은 다른 대여소로 센다. 공휴일은 빼지 않는다
def ddareungi_commute() -> None:
    AM, PM = (7, 8, 9), (17, 18, 19)
    by = Counter()               # (시, 대여소명) → 평일 이용건수
    days = set()
    for m in range(1, 13):
        with io.open(RAW / f"ddareungi_hourly_2025{m:02d}.csv", encoding="cp949",
                     newline="") as fh:
            r = csv.reader(fh)
            h = next(r)          # 7월부터 뒤쪽 칸 이름이 바뀌므로 칸 이름으로 찾는다
            iD, iH, iM, iC = (h.index(c) for c in ("대여일자", "대여시간", "대여소명", "이용건수"))
            for row in r:
                days.add(row[iD])
                hr = int(row[iH])
                if hr in AM or hr in PM:
                    if dt.date.fromisoformat(row[iD]).weekday() < 5:
                        by[hr, row[iM].strip()] += int(row[iC])

    # 기간: 원본에 있는 첫날~마지막 날. 원본이 비어 있는 날은 이어진 구간으로 묶어 밝힌다
    ds = sorted(dt.date.fromisoformat(d) for d in days)
    have = set(ds)
    gaps, run = [], []
    for i in range((ds[-1] - ds[0]).days + 1):
        d = ds[0] + dt.timedelta(i)
        if d not in have:
            run.append(d)
        elif run:
            gaps.append(run)
            run = []
    missing = ", ".join(f"{g[0]:%m-%d}" + (f"~{g[-1]:%m-%d}" if len(g) > 1 else "")
                        for g in gaps)
    period = f"{ds[0]}~{ds[-1]}" + (f"({missing} 없음, {len(ds)}일)" if gaps else "")

    def rank(hours):
        c = Counter()
        for (hr, s), v in by.items():
            if hr in hours:
                c[s] += v
        return c

    def shown(s):
        """화면에 보일 이름 — 앞의 «2715.» 같은 대여소번호를 뗀다 (세는 건 원래 이름으로)."""
        return re.sub(r"^\d+\.\s*", "", s)

    def area(s):
        """보기가 한 역의 출구들로만 채워지지 않게, «○○역» 까지를 같은 곳으로 본다."""
        m = re.match(r"(.+?역)", shown(s))
        return m.group(1) if m else shown(s)

    def top_q(qid, text, hours, label, why):
        c = rank(hours)
        (n1, v1), (n2, v2) = c.most_common(2)
        assert v1 != v2, f"{qid}: 1위가 둘이라 정답을 정할 수 없습니다"
        # 보기는 정답에 더해, 순위가 높은 대여소부터 이미 고른 곳과 같은 역이 아닌 셋.
        # 정답이 늘 첫 칸에 오지 않게 이름순으로 놓는다
        pick = [n1]
        for s, _ in c.most_common():
            if len(pick) == 4:
                break
            if area(s) not in {area(p) for p in pick}:
                pick.append(s)
        opts = sorted(shown(s) for s in pick)
        assert len(set(opts)) == 4, f"{qid}: 보기 이름이 겹칩니다 {opts}"
        return choice(qid, text, opts, shown(n1),
                      f"{period} 평일(월~금) {label} 대여 시작 대여소별 이용건수를 더하면 "
                      f"1위 {shown(n1)} {v1:,}건 (2위 {shown(n2)} {v2:,}건)", why)

    hourly = rank(AM + PM)
    per_h = {hr: sum(v for (h, _), v in by.items() if h == hr) for hr in AM + PM}
    peak = max(per_h, key=per_h.get)
    assert sorted(per_h.values())[-1] != sorted(per_h.values())[-2], "d4: 가장 많은 시간이 둘입니다"
    tot = sum(hourly.values())
    top5 = hourly.most_common(5)
    t5 = sum(v for _, v in top5)
    Y = ds[0].year

    topic(
        "ddareungi-commute", "🚲", "따릉이, 출퇴근엔 어디서",
        f"{ds[0].year}년 평일 출퇴근 시간대, 서울 따릉이 대여소별 대여",
        "서울 열린데이터광장 · 따릉이 이용정보(시간대별)",
        "https://data.seoul.go.kr/dataList/OA-15245/F/1/datasetView.do",
        [
            top_q("d1", f"{Y}년 평일 출퇴근길 따릉이 핫플 1위! 아침 7~9시대와 저녁 5~7시대에 따릉이를 "
                  "가장 많이 빌려 간 대여소는 어디일까요?",
                  AM + PM, "07~09시·17~19시",
                  "자주 지나다니는 동네의 대여소가 가장 붐빈다고 느끼기 쉽습니다. 서울 "
                  "전체로 세면 답이 달라집니다."),
            top_q("d2", f"지각은 안 돼! {Y}년 평일 아침 7~9시대, 따릉이를 가장 많이 빌려 간 대여소는 "
                  "어디일까요?",
                  AM, "07~09시",
                  "아침에는 집 근처에서 빌려 역이나 회사로 갑니다. 그래서 아침에 많이 "
                  "빌리는 곳과 저녁에 많이 빌리는 곳이 다를 수 있습니다."),
            top_q("d3", f"칼퇴 성공! {Y}년 평일 저녁 5~7시대, 따릉이를 가장 많이 빌려 간 대여소는 "
                  "어디일까요?",
                  PM, "17~19시",
                  "퇴근 때는 회사와 역 근처에서 빌리는 사람이 많아, 아침 순위와 같다고 "
                  "볼 수 없습니다."),
            choice("d4", f"{Y}년 평일 출퇴근 여섯 시간대 중 따릉이가 가장 바쁜 피크 타임은 몇 시대일까요?",
                   [f"{hr:02d}시" for hr in AM + PM], f"{peak:02d}시",
                   f"{period} 평일(월~금) 시간대별 이용건수를 더하면 "
                   + " · ".join(f"{hr:02d}시 {per_h[hr]:,}건" for hr in AM + PM),
                   "출근 시각은 몰려 있고 퇴근 시각은 흩어져 있다고 흔히 생각합니다. 어느 "
                   "한 시간이 가장 붐비는지는 세어 봐야 압니다."),
            slider("d5", f"{Y}년 평일 출퇴근 시간에 따릉이가 빌려 나간 대여소는 {len(hourly):,}곳. 그중 "
                   "인기 상위 5곳이 가져간 몫은 전체 대여의 몇 %일까요?",
                   t5 / tot * 100, "%", 0, 20, 0.1,
                   f"{period} 평일(월~금) 07~09시·17~19시 대여 {tot:,}건 중 상위 5개 대여소("
                   + ", ".join(shown(s) for s, _ in top5) + f") {t5:,}건을 나누면 {t5 / tot * 100:.1f}%",
                   f"대여소가 {len(hourly):,}곳이나 돼서, 아무리 붐비는 곳이라도 한 곳이 "
                   "차지하는 몫은 생각보다 작습니다."),
        ],
        caveat=(f"원본에 {missing} 기록이 없습니다(올라온 그대로 둠). " if gaps else "")
               + "공휴일은 빼지 않았고, 대여소는 이름으로 구분해 번호가 같아도 이름이 바뀌면 "
                 "다른 대여소로 셌습니다. 대여 건수는 원본의 줄 수가 아니라 «이용건수» 칸을 "
                 "더한 값입니다. "
               + "다른 곳의 숫자와 다르다면, 여기서는 "
               + (f"{missing}이 빠진 {ds[0].year}년 자료로 " if gaps else f"{ds[0].year}년 자료로 ")
               + "주말을 뺀 출퇴근 시간만, 대여소번호가 아니라 대여소 이름으로 묶어 "
                 "세었기 때문입니다.")


# ── 직장인의 출퇴근 시간 ─────────────────────────────────────────
# 지표누리 통근시간(4260) 통계표 HTML. 인구총조사(5년 주기)라 개인 기록이 아니라
# 통근시간 구간별 통근인구(천 명)와 공표된 평균 통근시간(분/일)만 있다.
# 그래서 평균은 공표값을 그대로 쓴다. 개인별로 정렬해야 하는 중앙값은 묻지 않는다.
# 지표누리 설명에 평균 통근시간은 «집에서 직장까지» 걸리는 시간이라 편도다. 비율의 분모는 원본의 «전체» 줄이다.
# 원본 구간 '15-30분'은 15~29분, '30-45분'은 30~44분으로 본다
COMMUTE_BAND = {"15분 미만": "15분 미만", "15-30분": "15~29분", "30-45분": "30~44분",
                "45-60분": "45~59분", "60-90분": "60분 이상", "90-120분": "60분 이상",
                "120분 이상": "60분 이상"}


def commute_time() -> None:
    page = io.open(RAW / "commute_time.html", encoding="utf-8").read()
    table = re.search(r"<table[^>]*id=\"t_Table_426001\".*?</table>", page, re.S).group(0)
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", table, re.S):
        cells = [html.unescape(re.sub(r"<[^>]*>", "", c)).replace("\xa0", " ").strip()
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        rows.append([c for c in cells if c])
    years = [int(c) for c in rows[0] if c.isdigit()]
    T = {}                       # 항목 → {연도: 값}. 항목 이름은 숫자가 아닌 마지막 칸
    for r in rows[1:]:
        nums = [c for c in r if re.fullmatch(r"[\d,.]+", c)]
        if len(nums) == len(years):
            label = [c for c in r if c not in nums][-1]
            T[label] = {y: float(v.replace(",", "")) for y, v in zip(years, nums)}
    AVG = next(k for k in T if k.startswith("평균 통근시간"))
    assert set(T) - {"전체", AVG} == set(COMMUTE_BAND), f"구간이 예상과 다릅니다: {list(T)}"
    Y = max(years)
    total = T["전체"][Y]

    # 다섯 구간으로 묶는다 (원본 구간 순서 = 짧은 것부터)
    B = Counter()
    for band in COMMUTE_BAND:
        B[COMMUTE_BAND[band]] += T[band][Y]
    groups = list(dict.fromkeys(COMMUTE_BAND.values()))
    under30 = B["15분 미만"] + B["15~29분"]
    over60 = B["60분 이상"]
    top = max(groups, key=B.get)
    assert sorted(B.values())[-1] != sorted(B.values())[-2], "c4: 가장 많은 구간이 둘입니다"
    src = f"{Y}년 인구총조사 통근인구(천 명)"

    topic(
        "commute-time", "🚇", "직장인의 출퇴근 시간",
        f"{Y}년 인구총조사, 통근시간별 통근인구",
        "지표누리 · 국가데이터처 「인구총조사」",
        "https://www.index.go.kr/unify/idx-info.do?idxCd=4260",
        [
            slider("c1", f"지옥철, 꽉 막힌 도로… {Y}년 직장인이 집에서 회사까지 가는 데 걸린 평균 편도 "
                   "통근시간은 몇 분일까요?",
                   T[AVG][Y], "분", 0, 90, 1,
                   f"{Y}년 인구총조사의 공표 평균 통근시간({AVG[len('평균 통근시간'):].strip('()')}) "
                   f"{T[AVG][Y]:.1f}분을 그대로 씀",
                   "출퇴근길이 힘든 날이 기억에 오래 남아, '다들 한 시간은 걸린다'고 느끼기 "
                   "쉽습니다."),
            slider("c2", f"회사가 코앞! {Y}년 편도 통근시간이 30분도 안 걸린 직장인은 전체의 몇 %일까요?",
                   under30 / total * 100, "%", 0, 100, 1,
                   f"{src}에서 15분 미만과 15~29분을 더한 {under30:,.0f}천 명을 전체 "
                   f"{total:,.0f}천 명으로 나누면 {under30 / total * 100:.1f}%",
                   "가까운 곳에서 일하는 사람은 출퇴근 얘기를 잘 하지 않아서, 짧게 다니는 "
                   "사람의 몫을 작게 보기 쉽습니다."),
            slider("c3", f"출근만 했는데 벌써 지친다… {Y}년 편도 통근시간이 1시간 이상인 직장인은 전체의 "
                   "몇 %일까요?",
                   over60 / total * 100, "%", 0, 100, 1,
                   f"{src}에서 60-90분·90-120분·120분 이상을 더한 {over60:,.0f}천 명을 전체 "
                   f"{total:,.0f}천 명으로 나누면 {over60 / total * 100:.1f}%",
                   "한 시간 넘게 걸리는 출퇴근은 화제가 자주 돼서, 실제보다 흔하다고 "
                   "느끼기 쉽습니다."),
            choice("c4", f"{Y}년 직장인이 가장 많이 몰린 대세 편도 통근시간 구간은 어디일까요?",
                   groups, top,
                   f"{src}을 다섯 구간으로 묶으면 "
                   + " · ".join(f"{g} {B[g]:,.0f}" for g in groups) + "천 명",
                   "구간 폭이 다르면 넓은 구간에 사람이 많아 보입니다. '60분 이상'은 다른 "
                   "구간보다 훨씬 넓은 구간입니다."),
        ],
        caveat="인구총조사의 '통근인구'(12세 이상 중 매일 또는 정기적으로 집과 직장을 "
               "오가는 사람)를 직장인으로 봤습니다. 개인 기록이 아니라 천 명 단위 구간 "
               "표라서 평균은 공표값을 그대로 썼습니다. "
               f"통근시간은 집에서 직장까지의 편도 시간입니다(지표누리 설명). 5년마다 하는 조사라 가장 최근 값이 "
               f"{Y}년입니다. "
               f"다른 곳의 숫자와 다르다면, 이 값은 {Y}년"
               + (" 11월 코로나 시기" if Y == 2020 else "")
               + " 한 번의 조사 결과이고 원본 구간 '15-30분'과 '30-45분' 중 정확히 30분이 "
                 "어디에 들어가는지 적혀 있지 않아 30분 미만 비율은 경계를 어떻게 보느냐에 "
                 "따라 달라지기 때문입니다.")


# 한 주제만 다시 계산할 때는 여기서 끝낸다. 아래 다른 주제의 원본은 읽지도 않는다
ALONE = {"marriage-30s": marriage_30s, "ddareungi-commute": ddareungi_commute,
         "commute-time": commute_time}
if "--only" in sys.argv:
    ONLY = sys.argv[sys.argv.index("--only") + 1]
    assert ONLY in ALONE, f"--only 로 따로 계산할 수 있는 주제: {', '.join(ALONE)}"
    ALONE[ONLY]()
    write(TOPICS, ONLY)
    sys.exit(0)


# ════════════════════════════════════════════════════════════════
# 기상 공통
# ════════════════════════════════════════════════════════════════
w = load_json("seoul_weather.json")["daily"]
W = [{"d": dt.date.fromisoformat(t), "hi": hi, "lo": lo, "rain": r}
     for t, hi, lo, r in zip(w["time"], w["temperature_2m_max"],
                             w["temperature_2m_min"], w["precipitation_sum"])]
W24 = [x for x in W if x["d"].year == 2024]


def years(a, b):
    return [x for x in W if a <= x["d"].year <= b]


# ── 1. 서울 기온 ─────────────────────────────────────────────────
# ERA5 는 1950~70년대 구간의 품질이 낮고(초기 확장), 격자 평균이라 도심
# 관측값보다 낮게 나온다. 그래서 '역대 최고기온'이나 '폭염일 추세'처럼
# 그 구간에 기대는 문항은 쓰지 않는다. 열대야·연평균처럼 신호가 뚜렷한 것만 쓴다.
tropical_24 = sum(1 for x in W24 if x["lo"] >= 25)
trop_50s = sum(1 for x in years(1950, 1959) if x["lo"] >= 25) / 10
trop_10s = sum(1 for x in years(2015, 2024) if x["lo"] >= 25) / 10
t_ratio = trop_10s / trop_50s if trop_50s else 0
mean_50s = mean((x["hi"] + x["lo"]) / 2 for x in years(1950, 1959))
mean_10s = mean((x["hi"] + x["lo"]) / 2 for x in years(2015, 2024))
warming = mean_10s - mean_50s
below0_24 = sum(1 for x in W24 if x["lo"] < 0)
hot_days = Counter((x["d"].month, x["d"].day)
                   for x in years(1995, 2024) if x["hi"] >= 33)
peak_day = hot_days.most_common(1)[0]
# 한계 문장의 숫자도 손으로 적지 않는다 — 원본에서 가장 더웠던 날을 찾는다
hottest = max(W, key=lambda x: x["hi"])

topic(
    "seoul-heat", "🌡️", "서울은 얼마나 더워졌나",
    "1950년부터 2024년까지, 서울의 매일 기온",
    "Open-Meteo Archive (ERA5 재분석)", "https://open-meteo.com/",
    [
        slider("h1", "2024년 서울에서 열대야(밤 최저기온 25도 이상)는 며칠이었을까요?",
               tropical_24, "일", 0, 60, 1,
               f"2024년 일최저기온 25도 이상인 날 {tropical_24}일",
               "유난히 더웠던 밤 몇 번이 기억을 지배합니다. 실제 일수는 세어 봐야 "
               "압니다."),
        # 보기는 배수에 가장 가까운 것이 정답이 되게 경계를 둔다 (2.8배 → «약 3배»)
        choice("h2", "1950년대와 2015~2024년, 열대야는 몇 배 차이일까요?",
               ["거의 같다", "약 2배", "약 3배", "약 5배"],
               ["거의 같다", "약 2배", "약 3배", "약 5배"][
                   0 if t_ratio < 1.5 else 1 if t_ratio < 2.5
                   else 2 if t_ratio < 4 else 3],
               f"연평균 열대야 1950년대 {trop_50s:.1f}일 → 2015~2024년 "
               f"{trop_10s:.1f}일 ({t_ratio:.1f}배)",
               "'옛날에도 더웠다'는 느낌과 기록은 다릅니다. 기억은 유난히 더웠던 "
               "몇 밤으로 남지만, 기록은 해마다 빠짐없이 셉니다."),
        slider("h3", "1950년대와 비교해 서울의 연평균 기온은 몇 도 올랐을까요?",
               warming, "도", 0, 4, 0.1,
               f"1950년대 {mean_50s:.2f}도 → 2015~2024년 {mean_10s:.2f}도 "
               f"(+{warming:.2f}도)",
               "1~2도는 작아 보이지만, 그 변화가 열대야 일수를 몇 배로 바꿉니다. "
               "평균의 변화와 극단의 변화는 크기가 다릅니다."),
        choice("h4", "최근 30년간 33도 이상인 날이 가장 잦았던 날짜는?",
               ["7월 초", "7월 말", "8월 초", "8월 말"],
               "7월 말" if peak_day[0][0] == 7 and peak_day[0][1] >= 20
               else "8월 초" if peak_day[0][0] == 8 and peak_day[0][1] <= 10
               else "7월 초" if peak_day[0][0] == 7 else "8월 말",
               f"1995~2024년 중 가장 잦았던 날짜는 {peak_day[0][0]}월 "
               f"{peak_day[0][1]}일 ({peak_day[1]}회)",
               "장마가 끝나는 시점과 가장 더운 시점은 다릅니다."),
        slider("h5", "2024년 서울에서 밤 기온이 영하로 내려간 날은 며칠이었을까요?",
               below0_24, "일", 30, 150, 5,
               f"2024년 일최저기온 0도 미만인 날 {below0_24}일",
               "겨울이 짧아졌다고 느끼지만, 영하로 내려가는 날은 여전히 석 달 "
               "치가 넘습니다."),
    ],
    caveat="ERA5는 넓은 격자의 재분석 값이라 도심 관측소와 다르게 나옵니다. "
           f"예컨대 여기서는 역대 최고기온이 {hottest['hi']:.1f}도"
           f"({hottest['d']:%Y년})지만 기상청 서울 관측 기록은 2018년 39.6도입니다. "
           "같은 '서울 기온'도 출처에 따라 다릅니다.")

# ── 2. 비 ────────────────────────────────────────────────────────
rain_days = [sum(1 for x in W if x["d"].year == y and x["rain"] >= 1.0)
             for y in range(1995, 2025)]
rain_avg = mean(rain_days)
by_month = {m: mean([sum(x["rain"] for x in W
                         if x["d"].year == y and x["d"].month == m)
                     for y in range(1995, 2025)]) for m in range(1, 13)}
wettest_m = max(by_month, key=by_month.get)
max_day = max(W, key=lambda x: x["rain"])
ann = {y: sum(x["rain"] for x in W if x["d"].year == y) for y in range(1995, 2025)}
norm = mean(ann.values())
r2024 = ann[2024]


def days_to_half(y):
    v = sorted((x["rain"] for x in W if x["d"].year == y), reverse=True)
    half, s = sum(v) / 2, 0
    for i, r in enumerate(v, 1):
        s += r
        if s >= half:
            return i
    return len(v)


half_days = round(mean(days_to_half(y) for y in range(1995, 2025)))

topic(
    "seoul-rain", "☔", "비는 언제, 얼마나",
    "서울의 하루치 강수량 30년",
    "Open-Meteo Archive (ERA5 재분석)", "https://open-meteo.com/",
    [
        slider("r1", "서울에서 1년 중 비가 온 날(1mm 이상)은 며칠쯤일까요?",
               rain_avg, "일", 40, 160, 5,
               f"1995~2024년 평균 {rain_avg:.1f}일 "
               f"(최소 {min(rain_days)}일 · 최대 {max(rain_days)}일)",
               "비 오는 날은 기억에 오래 남아서 실제보다 많게 느껴집니다."),
        choice("r2", "1년 강수량이 가장 많은 달은?",
               ["6월", "7월", "8월", "9월"], f"{wettest_m}월",
               " · ".join(f"{m}월 {by_month[m]:.0f}mm" for m in (6, 7, 8, 9)),
               "장마가 낀 달과 비가 가장 많이 오는 달이 같지 않을 수 있습니다."),
        slider("r3", "하루에 내린 비의 최대 기록은?",
               max_day["rain"], "mm", 100, 500, 10,
               f"{max_day['d']:%Y년 %m월 %d일} {max_day['rain']:.1f}mm",
               f"가장 많이 온 날 하루에, 비가 가장 많은 {wettest_m}월 한 달 평균"
               f"({by_month[wettest_m]:.0f}mm)의 {max_day['rain'] / by_month[wettest_m] * 100:.0f}%가 "
               "쏟아졌습니다. 비는 고르게 오지 않습니다."),
        slider("r4", "1년 강수량의 절반은 '비 온 날' 며칠 만에 채워질까요?",
               half_days, "일", 3, 40, 1,
               f"많이 온 날부터 더해서 연 강수량의 절반에 도달하는 데 "
               f"평균 {half_days}일 (1995~2024년)",
               "비는 고르게 오지 않습니다. 열흘 남짓이 1년의 절반을 만듭니다."),
        slider("r5", "2024년 서울 강수량은 30년 평균의 몇 %였을까요?",
               r2024 / norm * 100, "%", 50, 180, 5,
               f"2024년 {r2024:.0f}mm · 1995~2024년 평균 {norm:.0f}mm",
               "'올해 비가 많았다'는 체감과 실제 총량은 자주 어긋납니다."),
    ],
    caveat="ERA5 재분석 값입니다. 기상청 관측 강수량과 조금씩 다릅니다.")

# ── 3. 미세먼지 ──────────────────────────────────────────────────
a = load_json("seoul_air.json")["hourly"]
A = [{"t": dt.datetime.fromisoformat(t), "pm25": p25, "pm10": p10}
     for t, p25, p10 in zip(a["time"], a["pm2_5"], a["pm10"])]
A24 = [x for x in A if x["t"].year == 2024]
pm_month = {m: mean([x["pm25"] for x in A if x["t"].month == m])
            for m in range(1, 13)}
worst_m = max(pm_month, key=pm_month.get)
pm_hour = {h: mean([x["pm25"] for x in A if x["t"].hour == h])
           for h in range(24)}
worst_h = max(pm_hour, key=pm_hour.get)
pm24_avg = mean(x["pm25"] for x in A24)


def daily_avg(year):
    d = {}
    for x in A:
        if x["t"].year == year:
            d.setdefault(x["t"].date(), []).append(x["pm25"])
    return {k: mean(v) for k, v in d.items()}


d24 = daily_avg(2024)
d23 = daily_avg(2023)
bad_ratio = sum(1 for v in d24.values() if v > 35) / len(d24) * 100
worse_year = "2023년" if mean(d23.values()) > mean(d24.values()) else "2024년"

topic(
    "seoul-air", "😷", "미세먼지, 언제 나쁜가",
    "서울의 시간별 초미세먼지 2년치",
    "Open-Meteo Air Quality (CAMS)", "https://open-meteo.com/",
    [
        choice("a1", "초미세먼지(PM2.5)가 가장 나쁜 달은?",
               ["1월", "3월", "5월", "11월"],
               f"{worst_m}월" if f"{worst_m}월" in ["1월", "3월", "5월", "11월"]
               else "3월",
               " · ".join(f"{m}월 {pm_month[m]:.1f}" for m in (1, 3, 5, 11))
               + f" (최악은 {worst_m}월 {pm_month[worst_m]:.1f})",
               "황사 뉴스가 많은 달과 실제 수치가 높은 달은 다를 수 있습니다."),
        slider("a2", "2024년 서울의 초미세먼지 연평균 농도는?",
               pm24_avg, "㎍/㎥", 5, 60, 1,
               f"2024년 시간값 {len(A24):,}개의 평균 {pm24_avg:.1f}㎍/㎥ "
               f"(WHO 권고 연평균 5, 국내 기준 15)",
               "'나쁨'인 날이 인상에 남아서 연평균을 높게 잡게 됩니다."),
        choice("a3", "하루 중 초미세먼지가 가장 높은 시간대는?",
               ["새벽 4시", "오전 10시", "오후 3시", "밤 9시"],
               {4: "새벽 4시", 10: "오전 10시", 15: "오후 3시",
                21: "밤 9시"}.get(worst_h, "오전 10시"),
               " · ".join(f"{h}시 {pm_hour[h]:.1f}" for h in (4, 10, 15, 21))
               + f" (최고는 {worst_h}시)",
               "출퇴근 시간이 가장 나쁠 것 같지만 대기가 정체되는 시간은 따로 "
               "있습니다."),
        slider("a4", "2024년 하루 평균이 '나쁨'(35㎍/㎥ 초과)이었던 날의 비율은?",
               bad_ratio, "%", 0, 60, 1,
               f"2024년 {len(d24)}일 중 "
               f"{sum(1 for v in d24.values() if v > 35)}일",
               "마스크를 챙긴 날은 강하게 기억되지만, 1년 전체로 보면 비율이 "
               "다릅니다."),
        choice("a5", "2023년과 2024년 중 초미세먼지가 더 나빴던 해는?",
               ["2023년", "2024년"], worse_year,
               f"연평균 2023년 {mean(d23.values()):.1f} · "
               f"2024년 {mean(d24.values()):.1f}㎍/㎥",
               "체감은 최근 쪽으로 쏠립니다. 두 해 차이는 생각보다 작습니다."),
    ],
    caveat="CAMS 대기질 모델의 추정값입니다. 에어코리아 측정소 실측값과 "
           "다를 수 있습니다.")

# ── 4. 노동시간 ──────────────────────────────────────────────────
wh = [r for r in load_csv("working_hours.csv") if r["working_hours_omm"]]
latest_year = max(int(r["year"]) for r in wh if r["code"] == "KOR")
cur = owid_countries(wh, latest_year, "working_hours_omm")
kor = cur["South Korea"]
rank = sorted(cur.items(), key=lambda kv: -kv[1])
kor_rank = [k for k, _ in rank].index("South Korea") + 1
longer = kor_rank - 1
past = {int(r["year"]): float(r["working_hours_omm"])
        for r in wh if r["code"] == "KOR"}
y30 = latest_year - 30
drop = past[y30] - kor
trio = {c: cur[c] for c in ("South Korea", "Japan", "Germany") if c in cur}
shortest = min(trio, key=trio.get)
name_ko = {"South Korea": "한국", "Japan": "일본", "Germany": "독일"}

topic(
    "working-hours", "⏰", "우리는 얼마나 일하나",
    "나라별 1인당 연간 노동시간",
    "Our World in Data", "https://ourworldindata.org/grapher/annual-working-hours-per-worker",
    [
        slider("w1", f"{latest_year}년 한국의 1인당 연간 노동시간은?",
               kor, "시간", 1200, 2600, 50,
               f"{latest_year}년 한국 {kor:,.0f}시간 "
               f"(주 5일 기준 하루 약 {kor / 250:.1f}시간)",
               "연 단위로 물으면 감이 잘 안 옵니다. 하루로 나눠 보면 체감과 "
               "맞는지 확인할 수 있습니다."),
        slider("w2", f"한국보다 더 오래 일하는 나라는 {len(cur)}개국 중 몇 개일까요?",
               longer, "개국", 0, 60, 1,
               f"{latest_year}년 기준 {len(cur)}개국 중 한국은 {kor_rank}위",
               "'한국이 제일 많이 일한다'는 인상이 강하지만, 비교 대상에 따라 "
               "순위가 달라집니다."),
        slider("w3", f"한국의 노동시간은 30년 전({y30}년)보다 몇 시간 줄었을까요?",
               drop, "시간", 0, 900, 50,
               f"{y30}년 {past[y30]:,.0f}시간 → {latest_year}년 {kor:,.0f}시간",
               "줄어든 폭은 대개 과소평가됩니다. 하루로 치면 크게 달라진 값입니다."),
        choice("w4", "한국·일본·독일 중 가장 적게 일하는 나라는?",
               ["한국", "일본", "독일"], name_ko[shortest],
               " · ".join(f"{name_ko[c]} {trio[c]:,.0f}시간" for c in trio),
               "나라마다 통계 기준이 다릅니다. 순위보다 격차의 크기를 봅니다."),
        slider("w5", "한국과 독일의 연간 노동시간 차이는?",
               abs(cur["South Korea"] - cur["Germany"]), "시간", 0, 900, 50,
               f"한국 {cur['South Korea']:,.0f} · 독일 "
               f"{cur['Germany']:,.0f}시간",
               "두 나라 차이를 주 단위로 나눠 보면 체감이 확 달라집니다."),
    ],
    caveat="이 자료에는 개발도상국이 많이 포함돼 있어, OECD 안에서의 순위와 "
           "전체 순위가 다릅니다. '어느 집단과 비교하느냐'가 순위를 만듭니다.")

# ── 5. 인구와 출산 ───────────────────────────────────────────────
# World Bank·OWID 응답에는 '유럽연합' '고소득국' 같은 **집계치**가 섞여 있다.
# 그대로 순위를 매기면 나라와 대륙을 한 줄에 놓고 세는 셈이 된다.
# (wb_countries() 가 부를 때 쓴다. --only 로 한 주제만 계산할 때 읽지 않도록 여기 둔다)
REAL = {x["id"] for x in load_json("wb_countries.json")[1]
        if x["region"]["id"] != "NA"}

fert =[r for r in load_json("wb_fertility.json")[1] if r["value"] is not None]
f_latest = max(int(r["date"]) for r in fert if r["countryiso3code"] == "KOR")
f_cur = wb_countries(fert, f_latest)
kor_f = f_cur["Korea, Rep."]
f_rank = sorted(f_cur.items(), key=lambda kv: kv[1])
kor_f_rank = [k for k, _ in f_rank].index("Korea, Rep.") + 1
kor_1970 = next(r["value"] for r in fert
                if r["countryiso3code"] == "KOR" and r["date"] == "1970")

pop = load_json("wb_pop_kor.json")[1]
tot = {int(r["date"]): r["value"] for r in pop
       if r["indicator"]["id"] == "SP.POP.TOTL" and r["value"]}
old = {int(r["date"]): r["value"] for r in pop
       if r["indicator"]["id"] == "SP.POP.65UP.TO.ZS" and r["value"]}
urb = {int(r["date"]): r["value"] for r in pop
       if r["indicator"]["id"] == "SP.URB.TOTL.IN.ZS" and r["value"]}
peak_year = max(tot, key=tot.get)
old_latest = max(old)
urb_latest = max(urb)

topic(
    "population", "👶", "인구와 출산",
    "전 세계 출산율과 한국의 인구 구조",
    "World Bank Open Data", "https://data.worldbank.org/",
    [
        slider("p1", f"{f_latest}년 한국의 합계출산율(여성 1명당 출생아 수)은?",
               kor_f, "명", 0.5, 3.0, 0.05,
               f"{f_latest}년 한국 {kor_f:.2f}명",
               "숫자는 자주 들었어도 '여성 1명당'이라는 단위는 잘 안 와닿습니다."),
        slider("p2", f"출산율이 낮은 순으로 세면 한국은 {len(f_cur)}개 나라·지역 중 몇 위일까요?",
               kor_f_rank, "위", 1, 30, 1,
               f"{f_latest}년 기준 {len(f_cur)}곳 중 {kor_f_rank}위 "
               f"(1위 {f_rank[0][0]} {f_rank[0][1]:.2f})",
               "'꼴찌'라고 알고 있지만, 비교 목록에 어떤 나라·지역이 들어가느냐에 "
               "따라 순위가 달라집니다."),
        slider("p3", "1970년 한국의 출산율은 몇 명이었을까요?",
               kor_1970, "명", 1.0, 7.0, 0.1,
               f"1970년 {kor_1970:.2f}명 → {f_latest}년 {kor_f:.2f}명",
               "한 세대 만에 일어난 변화의 크기는 대개 과소평가됩니다."),
        slider("p4", f"{old_latest}년 한국에서 65세 이상 인구의 비율은?",
               old[old_latest], "%", 5, 35, 1,
               f"{old_latest}년 {old[old_latest]:.1f}% "
               f"(World Bank 최신 공표치. 최근 연도는 추계값입니다)",
               "고령화는 '다가올 일'로 느껴지지만 이미 지나온 숫자입니다."),
        slider("p5", f"{urb_latest}년 한국에서 도시에 사는 사람의 비율은?",
               urb[urb_latest], "%", 50, 100, 1,
               f"{urb_latest}년 {urb[urb_latest]:.1f}% "
               f"(World Bank 최신 공표치. 최근 연도는 추계값입니다)",
               "'절반쯤'이라고 답하기 쉽지만 한국은 세계에서도 손꼽히는 도시 국가입니다."),
    ])

# ── 6. 인터넷 ────────────────────────────────────────────────────
net = [r for r in load_json("wb_internet.json")[1] if r["value"] is not None]
n_latest = max(int(r["date"]) for r in net if r["countryiso3code"] == "KOR")
n_cur = wb_countries(net, n_latest)
kor_n = n_cur["Korea, Rep."]
n_rank = sorted(n_cur.items(), key=lambda kv: -kv[1])
kor_n_rank = [k for k, _ in n_rank].index("Korea, Rep.") + 1
kor_2000 = next(r["value"] for r in net
                if r["countryiso3code"] == "KOR" and r["date"] == "2000")
world = next((r["value"] for r in net
              if r["countryiso3code"] == "WLD" and int(r["date"]) == n_latest), None)
if world is None:
    world = mean(n_cur.values())
offline = 100 - world

topic(
    "internet", "🌐", "인터넷과 연결",
    "나라별 인터넷 사용 인구 비율",
    "World Bank Open Data", "https://data.worldbank.org/",
    [
        slider("i1", f"{n_latest}년 한국에서 인터넷을 쓰는 사람의 비율은?",
               kor_n, "%", 60, 100, 1,
               f"{n_latest}년 한국 {kor_n:.1f}%",
               "'거의 다'라고 생각하지만 100%는 아닙니다. 남은 몇 %가 누구인지가 "
               "정책의 대상입니다."),
        slider("i2", f"한국보다 인터넷 사용률이 높은 나라는 {len(n_cur)}곳 중 몇 곳일까요?",
               kor_n_rank - 1, "곳", 0, 60, 1,
               f"{n_latest}년 {len(n_cur)}곳 중 한국 {kor_n_rank}위",
               "'IT 강국'이라는 말과 실제 보급률 순위는 다른 이야기입니다."),
        slider("i3", "2000년 한국의 인터넷 사용률은?",
               kor_2000, "%", 0, 100, 5,
               f"2000년 {kor_2000:.1f}% → {n_latest}년 {kor_n:.1f}%",
               "20여 년 전을 떠올릴 때는 지금의 기준으로 과대평가하기 쉽습니다."),
        slider("i4", f"{n_latest}년 전 세계 평균 인터넷 사용률은?",
               world, "%", 20, 100, 5,
               f"{n_latest}년 세계 {world:.1f}%",
               "내 주변이 전부 연결돼 있으면 세계도 그럴 거라고 생각하게 됩니다."),
        slider("i5", "전 세계에서 인터넷을 쓰지 않는 사람은 몇 %일까요?",
               offline, "%", 0, 70, 5,
               f"100 - {world:.1f} = {offline:.1f}%",
               "같은 사실을 뒤집어 물으면 전혀 다른 크기로 느껴집니다."),
    ])

# ── 7. 환율 ──────────────────────────────────────────────────────
fx = load_json("usdkrw.json")["rates"]
FX = sorted((d, v["KRW"]) for d, v in fx.items() if "KRW" in v)
hi_d, hi_v = max(FX, key=lambda x: x[1])
lo_d, lo_v = min(FX, key=lambda x: x[1])
avg_fx = mean(v for _, v in FX)
under1200 = sum(1 for _, v in FX if v < 1200) / len(FX) * 100
last_d, last_v = FX[-1]
era = ("1997~1999년 외환위기" if hi_d < "2005" else
       "2008~2009년 금융위기" if hi_d < "2012" else
       "2020년 코로나" if hi_d < "2022" else "2022년 이후")

topic(
    "usdkrw", "💵", "원달러 환율 26년",
    "1999년부터 오늘까지의 원달러 환율",
    "Frankfurter (유럽중앙은행 고시)", "https://frankfurter.dev/",
    [
        slider("x1", "1999년 이후 원달러 환율의 최고 기록은?",
               hi_v, "원", 1100, 1800, 25,
               f"{hi_d} {hi_v:,.2f}원",
               "최고치는 위기의 기억과 함께 남지만, 정확한 시점은 자주 헷갈립니다."),
        choice("x2", "그 최고치를 찍은 시기는?",
               ["1997~1999년 외환위기", "2008~2009년 금융위기",
                "2020년 코로나", "2022년 이후"], era,
               f"최고 {hi_v:,.2f}원 ({hi_d}). 이 데이터는 1999년부터라 "
               f"1997~98년 외환위기 구간은 포함되어 있지 않습니다",
               "데이터가 시작하는 시점을 확인하지 않으면 '역대 최고'를 잘못 "
               "말하게 됩니다."),
        slider("x3", "26년간의 평균 환율은?",
               avg_fx, "원", 900, 1500, 25,
               f"{FX[0][0]} ~ {FX[-1][0]} 거래일 {len(FX):,}일 평균 "
               f"{avg_fx:,.0f}원 (최저 {lo_v:,.0f}원 · {lo_d})",
               "최근 값이 기준점이 되어 과거 평균을 높게 잡게 됩니다."),
        slider("x4", "환율이 1,200원 아래였던 날은 전체의 몇 %일까요?",
               under1200, "%", 0, 100, 5,
               f"거래일 {len(FX):,}일 중 1,200원 미만은 "
               f"{sum(1 for _, v in FX if v < 1200):,}일",
               "'원래 1,100원대였는데'라는 감각이 맞는지 비율로 확인해 봅니다."),
        slider("x5", f"{last_d} 기준 환율은?",
               last_v, "원", 1100, 1800, 25,
               f"{last_d} {last_v:,.2f}원",
               "가장 최근 값조차 기억은 며칠 전 뉴스에 묶여 있습니다."),
    ])

# ── 8. 도시 비교 ─────────────────────────────────────────────────
CITY = {}
for cid in ("seoul", "tokyo", "london", "singapore"):
    _d = load_json(f"city_{cid}.json")["daily"]
    CITY[cid] = [{"d": dt.date.fromisoformat(t), "hi": a, "lo": b, "r": c}
                 for t, a, b, c in zip(_d["time"], _d["temperature_2m_max"],
                                       _d["temperature_2m_min"],
                                       _d["precipitation_sum"])]
CN = {"seoul": "서울", "tokyo": "도쿄", "london": "런던", "singapore": "싱가포르"}
YRS = 30
c_rain = {k: sum(x["r"] for x in v) / YRS for k, v in CITY.items()}
c_days = {k: sum(1 for x in v if x["r"] >= 1) / YRS for k, v in CITY.items()}
c_temp = {k: mean((x["hi"] + x["lo"]) / 2 for x in v) for k, v in CITY.items()}
c_hot = {k: max(x["hi"] for x in v) for k, v in CITY.items()}
c_jan = {k: mean(x["lo"] for x in v if x["d"].month == 1) for k, v in CITY.items()}
dry = min(c_rain, key=c_rain.get)
hottest = max(c_hot, key=c_hot.get)
colder = "서울" if c_jan["seoul"] < c_jan["tokyo"] else "도쿄"

topic(
    "cities", "🏙️", "서울·도쿄·런던·싱가포르",
    "네 도시의 30년 평년값 (1991~2020)",
    "Open-Meteo Archive (ERA5 재분석)", "https://open-meteo.com/",
    [
        choice("c1", "1년 강수량이 가장 적은 도시는?",
               ["서울", "도쿄", "런던", "싱가포르"], CN[dry],
               " · ".join(f"{CN[k]} {c_rain[k]:,.0f}mm" for k in CITY),
               "비가 자주 오는 것과 많이 오는 것은 다릅니다. 런던은 자주 오지만 "
               "적게 옵니다."),
        slider("c2", "런던에서 1년에 비가 오는 날(1mm 이상)은 며칠일까요?",
               c_days["london"], "일", 40, 220, 5,
               f"런던 {c_days['london']:.0f}일 · 서울 {c_days['seoul']:.0f}일 "
               f"(강수량은 런던 {c_rain['london']:,.0f}mm · "
               f"서울 {c_rain['seoul']:,.0f}mm)",
               "런던은 서울보다 비 오는 날이 많은데 총량은 절반입니다. "
               "'며칠 왔나'와 '얼마나 왔나'는 다른 질문입니다."),
        choice("c3", "30년간 가장 높은 기온을 기록한 도시는?",
               ["서울", "도쿄", "런던", "싱가포르"], CN[hottest],
               " · ".join(f"{CN[k]} {c_hot[k]:.1f}도" for k in CITY),
               "적도에 가까울수록 덥다고 생각하지만, 최고기온 기록은 중위도 "
               "도시에서 나옵니다."),
        slider("c4", "서울의 연평균 기온은?",
               c_temp["seoul"], "도", 5, 30, 0.5,
               " · ".join(f"{CN[k]} {c_temp[k]:.1f}도" for k in CITY),
               "여름과 겨울의 기억이 강해서 연평균은 감이 잘 안 옵니다."),
        choice("c5", "1월 밤이 더 추운 도시는?",
               ["서울", "도쿄"], colder,
               f"1월 평균 최저기온 서울 {c_jan['seoul']:.1f}도 · "
               f"도쿄 {c_jan['tokyo']:.1f}도",
               "위도가 비슷해도 대륙의 영향을 받는 도시가 훨씬 춥습니다."),
    ],
    caveat="ERA5 재분석 값이고, 도시별로 관측소 위치와 기준이 다릅니다.")

# ── 9. 지진 ──────────────────────────────────────────────────────
Q = [f["properties"] for f in load_json("quakes.geojson")["features"]]
QK = [f["properties"] for f in load_json("quakes_korea.geojson")["features"]]
n_years = 25
per_year = len(Q) / n_years
m7 = sum(1 for p in Q if p["mag"] >= 7.0) / n_years
biggest = max(Q, key=lambda p: p["mag"])


def region(place):
    return (place or "").split(",")[-1].strip()


top_region = Counter(region(p["place"]) for p in Q).most_common(1)[0]
region_ko = {"Japan": "일본", "Indonesia": "인도네시아", "Chile": "칠레",
             "Philippines": "필리핀"}
kr_band = ("50건 미만" if len(QK) < 50 else "50~150건" if len(QK) <= 150
           else "150~400건" if len(QK) <= 400 else "400건 이상")

topic(
    "quakes", "🌎", "지진은 얼마나 자주",
    "2000~2024년 전 세계 지진 기록",
    "USGS 지진 카탈로그", "https://earthquake.usgs.gov/",
    [
        slider("q1", "규모 5.5 이상 지진은 전 세계에서 1년에 몇 번쯤 일어날까요?",
               per_year, "회", 50, 1200, 50,
               f"2000~2024년 {len(Q):,}건 ÷ {n_years}년 = "
               f"연평균 {per_year:.0f}회",
               "뉴스에 나오는 지진만 세면 실제보다 훨씬 적게 잡게 됩니다."),
        slider("q2", "규모 7.0 이상은 1년에 몇 번쯤일까요?",
               m7, "회", 0, 40, 1,
               f"2000~2024년 규모 7.0 이상 "
               f"{sum(1 for p in Q if p['mag'] >= 7.0)}건, 연평균 {m7:.1f}회",
               "규모는 로그 척도입니다. 0.5만 올라가도 횟수가 크게 줄어듭니다."),
        choice("q3", "규모 5.5 이상 지진이 가장 자주 기록된 나라는?",
               ["일본", "인도네시아", "칠레", "필리핀"],
               region_ko.get(top_region[0], "인도네시아"),
               f"1위 {top_region[0]} {top_region[1]:,}건",
               "지진 하면 떠오르는 나라와 실제로 가장 많이 기록되는 곳은 "
               "다를 수 있습니다."),
        slider("q4", "2000년 이후 기록된 가장 큰 지진의 규모는?",
               biggest["mag"], "", 7.0, 9.9, 0.1,
               f"규모 {biggest['mag']} · "
               f"{dt.datetime.fromtimestamp(biggest['time'] / 1000, dt.UTC):%Y-%m-%d} "
               f"{biggest['place']}",
               "규모 9는 8보다 약 32배 큰 에너지입니다."),
        choice("q5", "한반도 주변(위도 33~39.5도)에서 25년간 기록된 규모 3.0 이상 지진은?",
               ["50건 미만", "50~150건", "150~400건", "400건 이상"], kr_band,
               f"USGS 기준 {len(QK)}건. 이 관측망은 작은 지진을 모두 잡지는 "
               f"못하므로 기상청 집계와 다릅니다",
               "'어느 기관이 센 숫자인가'를 확인하지 않으면 같은 현상도 다른 "
               "값이 됩니다."),
    ],
    caveat="USGS 카탈로그는 작은 지진을 모두 담지 못합니다. 한반도 지진은 "
           "기상청 집계가 더 많습니다.")

# ── 10. 수명 ─────────────────────────────────────────────────────
le = [r for r in load_csv("life_expectancy.csv") if r["life_expectancy_0"]]
l_latest = max(int(r["year"]) for r in le if r["code"] == "KOR")
l_cur = owid_countries(le, l_latest, "life_expectancy_0")
kor_l = l_cur["South Korea"]
l_rank = sorted(l_cur.items(), key=lambda kv: -kv[1])
kor_l_rank = [k for k, _ in l_rank].index("South Korea") + 1
_kle = {r["year"]: float(r["life_expectancy_0"]) for r in le if r["code"] == "KOR"}
kor_1950, kor_1953, kor_1955 = _kle["1950"], _kle["1953"], _kle["1955"]
wld = next(float(r["life_expectancy_0"]) for r in le
           if r["code"] == "OWID_WRL" and int(r["year"]) == l_latest)
trio_l = {c: l_cur[c] for c in ("South Korea", "Japan", "United States")
          if c in l_cur}
top_l = max(trio_l, key=trio_l.get)
name_l = {"South Korea": "한국", "Japan": "일본", "United States": "미국"}

topic(
    "life", "🩺", "얼마나 오래 사나",
    "나라별 기대수명 1950~현재",
    "Our World in Data", "https://ourworldindata.org/grapher/life-expectancy",
    [
        slider("l1", f"{l_latest}년 한국의 기대수명은?",
               kor_l, "세", 60, 95, 1,
               f"{l_latest}년 한국 {kor_l:.1f}세",
               "기대수명은 '지금 태어난 아이가 평균적으로 살 햇수'입니다. "
               "지금 살아 있는 사람의 예상 수명과는 다릅니다."),
        slider("l2", f"기대수명이 긴 순으로 세면 한국은 {len(l_cur)}곳 중 몇 위일까요?",
               kor_l_rank, "위", 1, 60, 1,
               f"{l_latest}년 {len(l_cur)}곳 중 {kor_l_rank}위 "
               f"(1위 {l_rank[0][0]} {l_rank[0][1]:.1f}세)",
               "상위권인 것은 맞지만 몇 위인지는 대개 크게 빗나갑니다."),
        slider("l3", "1950년 한국의 기대수명은?",
               kor_1950, "세", 20, 70, 1,
               f"1950년 {kor_1950:.1f}세. 한국전쟁 기간의 사망이 반영된 값이라 "
               f"1953년 {kor_1953:.1f}세, 1955년 {kor_1955:.1f}세로 빠르게 "
               f"회복합니다. {l_latest}년은 {kor_l:.1f}세",
               "숫자가 튀면 사건을 의심해야 합니다. 이 값은 오류가 아니라 "
               "전쟁의 기록입니다."),
        choice("l4", "한국·일본·미국 중 기대수명이 가장 긴 나라는?",
               ["한국", "일본", "미국"], name_l[top_l],
               " · ".join(f"{name_l[c]} {trio_l[c]:.1f}세" for c in trio_l),
               "가장 잘사는 나라가 가장 오래 사는 나라는 아닙니다."),
        slider("l5", f"{l_latest}년 세계 평균 기대수명은?",
               wld, "세", 50, 90, 1,
               f"{l_latest}년 세계 평균 {wld:.1f}세 · 한국 {kor_l:.1f}세",
               "내가 사는 곳의 수준을 세계 평균으로 착각하기 쉽습니다."),
    ])

# ── 11. 서울의 눈 ────────────────────────────────────────────────
# '눈 온 날' = 하루 강설량 1cm 이상. ERA5 는 0.01cm 같은 작은 값도 남기므로
# 기준을 0 으로 두면 눈이라 부르기 어려운 날까지 세게 된다
_s = load_json("seoul_snow.json")["daily"]
SN = [{"d": dt.date.fromisoformat(t), "snow": s}
      for t, s in zip(_s["time"], _s["snowfall_sum"])]
SNOW_CM = 1.0
snowy = [x for x in SN if x["snow"] >= SNOW_CM]
sn_years = sorted({x["d"].year for x in SN})
snow_avg = len(snowy) / len(sn_years)
snow_90s = sum(1 for x in snowy if 1990 <= x["d"].year <= 1999) / 10
snow_10s = sum(1 for x in snowy if 2015 <= x["d"].year <= 2024) / 10
s_ratio = snow_10s / snow_90s if snow_90s else 0
max_snow = max(SN, key=lambda x: x["snow"])
# 첫눈은 달력 연도로 세면 해마다 1월이 된다. 겨울 시즌(8/1~다음 해 7/31)으로 센다.
# 원본이 1990-01-01 부터라 1989/90 겨울은 앞부분이 없어서 뺀다
seasons = range(sn_years[0], sn_years[-1])
first_snow = {}
for y in seasons:
    days = [x["d"] for x in snowy if dt.date(y, 8, 1) <= x["d"] < dt.date(y + 1, 8, 1)]
    if days:
        first_snow[y] = days[0]
first_m = Counter(d.month for d in first_snow.values())
first_peak = first_m.most_common(1)[0]
snow_by_m = {m: sum(x["snow"] for x in SN if x["d"].month == m) / len(sn_years)
             for m in range(1, 13)}
snowiest_m = max(snow_by_m, key=snow_by_m.get)

topic(
    "seoul-snow", "❄️", "서울에는 눈이 얼마나 오나",
    f"{sn_years[0]}년부터 {sn_years[-1]}년까지, 서울의 하루 강설량",
    "Open-Meteo 과거 날씨 API · ERA5",
    "https://open-meteo.com/en/docs/historical-weather-api",
    [
        slider("s1", f"{sn_years[0]}~{sn_years[-1]}년, 서울에서 한 해에 눈이 온 날은 "
               "평균 며칠일까요?",
               snow_avg, "일", 0, 30, 1,
               f"{sn_years[0]}~{sn_years[-1]}년 하루 강설량 {SNOW_CM:g}cm 이상인 날 "
               f"{len(snowy)}일을 {len(sn_years)}년으로 나눠 연평균 {snow_avg:.1f}일",
               "눈 오는 날은 풍경이 달라져 오래 기억에 남습니다. 그래서 실제보다 "
               "자주 왔다고 느낍니다."),
        # 경계: 0.5배 이하 «절반 이하», 0.9배 미만 «조금 줄었다», 1.1배 이하 «거의 같다»
        choice("s2", "1990년대와 비교해 2015~2024년, 한 해 눈 온 날은 어떻게 달라졌을까요?",
               ["절반 이하로 줄었다", "조금 줄었다", "거의 같다", "늘었다"],
               ["절반 이하로 줄었다", "조금 줄었다", "거의 같다", "늘었다"][
                   0 if s_ratio <= 0.5 else 1 if s_ratio < 0.9
                   else 2 if s_ratio <= 1.1 else 3],
               f"하루 강설량 {SNOW_CM:g}cm 이상인 날을 10년씩 세어 나눈 연평균 "
               f"1990~1999년 {snow_90s:.1f}일 → 2015~2024년 {snow_10s:.1f}일 "
               f"({s_ratio:.2f}배)",
               "'요즘은 눈이 안 온다'는 말은 자주 듣지만, 줄어든 폭은 세어 봐야 "
               "압니다."),
        slider("s3", f"{sn_years[0]}~{sn_years[-1]}년, 서울에서 하루에 가장 많이 내린 눈은 "
               "몇 cm일까요?",
               max_snow["snow"], "cm", 0, 40, 0.5,
               f"{sn_years[0]}~{sn_years[-1]}년 {len(SN):,}일의 하루 강설량 중 최댓값은 "
               f"{max_snow['d']:%Y년 %m월 %d일} {max_snow['snow']:.1f}cm",
               "폭설 뉴스의 숫자는 도로와 지붕 위에 쌓인 눈의 깊이입니다. 하루에 "
               "내린 양과는 다릅니다."),
        choice("s4", f"{sn_years[0]}~{sn_years[-1]}년, 서울의 첫눈은 보통 몇 월에 올까요?",
               ["10월", "11월", "12월", "1월"], f"{first_peak[0]}월",
               f"{seasons[0]}~{seasons[-1]}년 겨울 {len(first_snow)}번의 첫눈"
               f"(8월 1일 이후 처음 {SNOW_CM:g}cm 이상 내린 날)을 달별로 세면 "
               + " · ".join(f"{m}월 {first_m[m]}번" for m in (10, 11, 12, 1, 2, 3)
                            if first_m[m]),
               "첫눈 소식은 눈발이 조금 날려도 나옵니다. 제대로 쌓일 만한 눈은 그보다 "
               "늦게 옵니다."),
        choice("s5", "서울에서 눈이 가장 많이 내리는 달은 언제일까요?",
               ["12월", "1월", "2월", "3월"], f"{snowiest_m}월",
               f"{sn_years[0]}~{sn_years[-1]}년 달마다 하루 강설량을 모두 더해 "
               f"{len(sn_years)}년으로 나눈 평균 "
               + " · ".join(f"{m}월 {snow_by_m[m]:.1f}cm" for m in (12, 1, 2, 3)),
               "가장 추운 달과 눈이 가장 많이 오는 달은 같지 않을 수 있습니다. "
               "눈은 추위만이 아니라 수증기가 있어야 내립니다."),
    ],
    caveat="ERA5는 넓은 격자의 재분석 값이라 기상청 서울 관측소의 적설 기록과 다릅니다. "
           "여기서 강설량은 그날 내린 눈의 양(cm)이고, 쌓인 눈의 깊이가 아닙니다.")


marriage_30s()
ddareungi_commute()
commute_time()


# ════════════════════════════════════════════════════════════════
def main() -> None:
    write(TOPICS)


if __name__ == "__main__":
    main()
