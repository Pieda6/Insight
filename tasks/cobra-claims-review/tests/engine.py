"""Verifier-side model of COBRA continuation coverage (26 CFR 54.4980B-2, -3, -6, -7, -8), written independently of
the reference solution: each claim is decided on its own by asking, for its date of service, whether the date is
inside the maximum coverage period, before any early termination, and whether every premium from the first COBRA
month through the month of service was paid in time and in full. Dates are compared as days; premiums are exact
fractions."""
import json
import math
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def load(name):
    return json.loads((DATA / name).read_text())


def iso(s):
    return date.fromisoformat(s) if s else None


def months_later(x, n):
    """The same day n months later (x is always the first of a month here)."""
    total = x.month - 1 + n
    return date(x.year + total // 12, total % 12 + 1, 1)


def period_last_day(begin, n):
    """A period of n months beginning on the first of a month ends the day before the same day n months later."""
    return months_later(begin, n) - timedelta(days=1)


class Plan:
    def __init__(self):
        plan = load("plan.json")
        self.rates = plan["applicable_premium_single_coverage_cents"]
        self.people = {p["person_id"]: p for p in load("people.json")}
        self.elections = {e["person_id"]: e for e in load("elections.json")}
        self.members = {}
        for p in self.people.values():
            self.members.setdefault(p["family_id"], []).append(p)
        self.events = {}
        for e in load("events.json"):
            self.events.setdefault(e["family_id"], []).append(e)
        for v in self.events.values():
            v.sort(key=lambda e: e["date"])
        self.paid = {(x["person_id"], x["coverage_month"]): x for x in load("premium_payments.json")}

    def owed(self, option, month_first, percent):
        exact = Fraction(self.rates[option][str(month_first.year)] * percent, 100)
        return math.floor(exact + Fraction(1, 2))

    def family_facts(self, fid):
        evs = self.events[fid]
        first = evs[0]
        qe_date = iso((first["fmla_leave"] or {}).get("last_day") or first["date"])
        begin = months_later(qe_date.replace(day=1), 1)
        eighteen = first["event"] in ("termination", "reduction_of_hours")
        disabled = []
        if eighteen:
            for p in self.members[fid]:
                s = p["ssa_disability_determination"]
                if s and p["person_id"] in self.elections:
                    first_60_end = begin + timedelta(days=59)
                    if iso(s["disabled_since"]) <= first_60_end \
                            and (iso(s["notice_to_plan_date"]) - iso(s["determination_date"])).days <= 60 \
                            and iso(s["notice_to_plan_date"]) <= period_last_day(begin, 18):
                        disabled.append(p["person_id"])
        return first, qe_date, begin, eighteen, disabled

    def max_end(self, pid):
        person = self.people[pid]
        fid = person["family_id"]
        first, qe_date, begin, eighteen, disabled = self.family_facts(fid)
        if not eighteen:
            return period_last_day(begin, 36)
        end = period_last_day(begin, 29 if disabled else 18)
        role = person["relationship"]
        if role == "employee":
            return end
        allowed = {"spouse": ("death", "divorce"), "child": ("death", "child_reaches_26")}[role]
        notice = iso(self.elections[pid]["second_event_notice_date"])
        extended = end
        for e in self.events[fid][1:]:
            if e["event"] == "child_reaches_26" and (e["person_id"] != pid
                                                     or person.get("incapable_of_self_support_because_of_disability")):
                continue
            if e["event"] in allowed:
                when = iso(e["date"])
                if begin <= when <= end and notice is not None and (notice - when).days <= 60:
                    extended = max(extended, period_last_day(begin, 36))
        employee = next(p for p in self.members[fid] if p["relationship"] == "employee")
        med = iso(employee["medicare_entitlement_date"])
        if med is not None and med < qe_date:
            extended = max(extended, period_last_day(med, 36))
        return extended

    def covered(self, pid, when):
        person = self.people[pid]
        fid = person["family_id"]
        first, qe_date, begin, eighteen, disabled = self.family_facts(fid)
        if when < begin:                              # still under active coverage
            return True
        el = self.elections.get(pid)
        if el is None or el["elected_on"] is None:
            return False
        elected = iso(el["elected_on"])
        if (elected - max(begin, iso(el["election_notice_date"]))).days > 60:
            return False
        if not begin <= when <= self.max_end(pid):
            return False
        waived = el["waived_on"] is not None
        if waived and when < elected:
            return False
        for key in ("other_group_health_coverage_start", "medicare_entitlement_date"):
            starts = iso(person[key])
            if starts is not None and starts > elected and when >= starts:
                return False
        month = elected.replace(day=1) if waived else begin
        while month <= when:
            in_extension = period_last_day(begin, 18) < month <= period_last_day(begin, 29)
            percent = 150 if pid in disabled and in_extension else 102
            need = self.owed(el["coverage_option"], month, percent)
            pay = self.paid.get((pid, f"{month.year:04d}-{month.month:02d}"))
            if pay is None:
                return False
            if iso(pay["sent_on"]) > max(month + timedelta(days=30), elected + timedelta(days=45)):
                return False
            missing = need - pay["amount_cents"]
            if missing > 0:
                if Fraction(missing) > min(Fraction(5000), Fraction(need, 10)):
                    return False
                if pay["shortfall_notice_date"] is not None:
                    fixed = iso(pay["deficiency_sent_on"])
                    if fixed is None or (fixed - iso(pay["shortfall_notice_date"])).days > 30:
                        return False
            month = months_later(month, 1)
        return True


    def payments(self):
        """Plan payment per claim. Ledgers per person and calendar year hold every covered claim, under active
        coverage or COBRA (54.4980B-5 credits amounts before COBRA); each claim reads the ledger as it stood."""
        benefits = load("plan.json")["benefits_per_person_per_calendar_year"]
        claims = load("claims.json")
        history = {}
        for c in claims:
            history.setdefault(c["person_id"], []).append(c)
        result = {}
        for pid, mine in history.items():
            option = self.elections[pid]["coverage_option"]
            mine.sort(key=lambda c: c["date_of_service"])
            deductible_met, out_of_pocket = {}, {}
            for c in mine:
                when = iso(c["date_of_service"])
                if not self.covered(pid, when):
                    result[c["claim_id"]] = Fraction(0)
                    continue
                b = benefits[option][str(when.year)]
                allowed = Fraction(c["allowed_amount_cents"])
                before_d = deductible_met.get(when.year, Fraction(0))
                before_o = out_of_pocket.get(when.year, Fraction(0))
                ded = min(allowed, b["deductible_cents"] - before_d)
                coins = math.floor((allowed - ded) * b["coinsurance_percent"] / 100 + Fraction(1, 2))
                member = min(ded + coins, b["out_of_pocket_maximum_cents"] - before_o)
                deductible_met[when.year] = before_d + ded
                out_of_pocket[when.year] = before_o + member
                result[c["claim_id"]] = allowed - member
        return result


def expected():
    def money(x):
        assert x.denominator == 1
        return f"{int(x) // 100}.{int(x) % 100:02d}"
    return {k: {"plan_payment": money(v)} for k, v in Plan().payments().items()}
