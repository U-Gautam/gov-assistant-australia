"""Simple, inspectable FTS5 retrieval with narrow topic/intent safeguards."""

from __future__ import annotations

import math
import re
import sqlite3


STOP_WORDS = set(
    "a about an and are as at be by can could do does for from have how i in is it me my of on or our the their there these this to was were what when where which while who with you your"
    .split()
)
FOLD = {
    "oct": "october", "visas": "visa", "students": "student", "families": "family",
    "changes": "change", "changed": "change", "changing": "change", "recent": "change",
    "rules": "rule", "applications": "application", "applying": "apply",
    "lodged": "lodge", "lodging": "lodge", "transferring": "transfer",
    "providers": "provider", "children": "child", "dependants": "dependant",
}


def terms(value: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return list(dict.fromkeys(FOLD.get(word, word) for word in words if word not in STOP_WORDS))


def asks_about_other_october_change(question: str) -> bool:
    """Do not present the reviewed 2 October rules as a change on another day."""
    if not re.search(r"\b(change|changed|changes|new|update|updated|reform|rule|rules)\b", question):
        return False
    dates = re.findall(r"\b([0-3]?\d)(?:st|nd|rd|th)?\s+oct(?:ober)?(?:\s*,?\s*2026)?\b", question)
    dates += re.findall(r"\boct(?:ober)?\s+([0-3]?\d)(?:st|nd|rd|th)?(?:\s*,?\s*2026)?\b", question)
    return any(int(day) != 2 for day in dates)


def asks_about_post_study(question: str) -> bool:
    """Recognise graduation plans without treating a college as a provider transfer."""
    context = re.search(r"\b(international|overseas|australia|australian|visa)\b", question)
    graduation = re.search(r"\bgraduat(?:e|es|ed|ing|ion)\b", question) and not re.search(
        r"\bgraduate\s+(student|course|degree|program)\b", question
    )
    completed_course = (
        re.search(r"\b(complet(?:e|ed|ing)|finish(?:ed|ing)?)\b", question)
        and re.search(r"\b(course|studies|study|degree|diploma|qualification|college|university)\b", question)
    )
    return bool(context and (graduation or completed_course))


def broad_graduation_question(question: str) -> bool:
    """A short graduation prompt is a request for a starting point, not an error."""
    return bool(re.fullmatch(
        r"(?:graduation|graduating|graduated|graduate|after graduation|after graduating|"
        r"(?:i am|i['’]m) graduating|(?:i have|i['’]ve|i just) graduated|after i graduate)[!?.]*",
        question.strip(), re.IGNORECASE,
    ))


def asks_about_provider_transfer(question: str) -> bool:
    """Require a transfer action; naming a college alone is not enough."""
    return bool(
        re.search(r"\b(transfer|transfers|transferred|transferring|school change)\b", question)
        or re.search(
            r"\b(change|changing|switch|switching|move|moving)(?:\s+\w+){0,4}\s+"
            r"(provider|providers|college|colleges|school|schools)\b",
            question,
        )
    )


def route_question(question: str, selected_topic: str) -> tuple[str | None, set[str], str]:
    """Recognise only the small set of processes for which reviewed notes exist."""
    q = question.lower()
    if re.search(r"\b(tfn|tax file number)\b", q):
        if re.search(r"\b(lost|forgot|forgotten|misplaced|recover|existing|find)\b", q):
            return "tax", {"tfn_find"}, "tfn_find"
        if re.search(r"\b(apply|applying|get|obtain|new|free|cost)\b", q):
            return "tax", {"tfn_apply"}, "tfn_apply"
        return "tax", set(), "unsupported_tax_intent"
    if re.search(r"\bmygov\b", q) and re.search(r"\b(ato|australian taxation office)\b", q) and re.search(r"\b(link|connect)\b", q):
        return "tax", {"ato_link"}, "ato_link"
    if re.search(r"\bincome statements?\b", q) and re.search(r"\b(where|view|see|access|find|check)\b", q):
        return "tax", {"income_statement"}, "income_statement"
    if re.search(r"\bsuper(?:annuation)?\b", q) and re.search(r"\b(lost|missing|unclaimed)\b", q):
        return "tax", {"super_lost"}, "super_lost"
    if re.search(r"\b(abn|australian business number)\b", q):
        return "tax", {"abn_basics"}, "abn_basics"
    if re.search(r"\bsuper(?:annuation)?\b", q) and re.search(r"\b(leave|leaving|depart|departing|back|withdraw|dasp)\b", q):
        return "tax", {"super_dasp"}, "super_dasp"
    if re.search(r"\btax return\b", q) and re.search(r"\b(need|whether|must|should|required)\b", q) and re.search(r"\b(lodge|lodging|lodged)\b", q):
        return "tax", {"tax_need_lodge"}, "tax_need_lodge"
    if re.search(r"\btax return\b", q) and re.search(r"\b(progress|status|track|tracked|already lodged|checked|check)\b", q):
        return "tax", {"tax_return_progress"}, "tax_return_progress"
    tax_refund = bool(re.search(r"\brefund\b", q) and not re.search(r"\bvisa\b", q))
    if tax_refund and re.search(r"\b(check|track|status|progress)\b", q):
        return "tax", {"tax_return_progress"}, "tax_return_progress"
    if (tax_refund and re.search(r"\b(how long|when|get|arrive|receive|delay|processing time)\b", q)) or (
        "tax return" in q and re.search(r"\b(how long|delay|processing time)\b", q)
    ):
        return "tax", {"tax_refund_time"}, "tax_refund_time"
    if re.search(r"\b(tax return|tax time)\b", q) and re.search(r"\b(due|deadline|by when|last day)\b", q):
        return "tax", {"tax_due_date"}, "tax_due_date"
    if re.search(r"\b(tax return|tax time)\b", q) and re.search(r"\b(prepare|documents|information|records|before lodging)\b", q):
        return "tax", {"tax_prepare"}, "tax_prepare"
    if re.search(r"\b(tax[- ]?free threshold|earn tax[- ]?free|before (?:i )?pay tax)\b", q):
        return "tax", {"tax_free_threshold"}, "tax_free_threshold"
    if re.search(r"\b(tax|deduction|deductions)\b", q) and re.search(r"\b(deduction|deductions|expenses|receipts)\b", q):
        return "tax", {"tax_deductions"}, "tax_deductions"
    if re.search(r"\b(international students?|visa holders?|temporary residents?)\b", q) and re.search(r"\b(pay tax|tax on|taxed|income tax)\b", q):
        return "tax", {"tax_visa_holder"}, "tax_visa_holder"
    if re.search(r"\b(?:non[- ]?lodg(?:e|ment)|do(?:n't| not) need to lodge)\b", q):
        return "tax", {"tax_nonlodgment"}, "tax_nonlodgment"
    if re.search(r"\bmygov\b", q) and re.search(r"\b(create|make|open|set up|sign up|register)\b", q):
        return "tax", {"mygov_create"}, "mygov_create"
    if re.search(r"\bmygov\b", q) and re.search(r"\b(what|how|account|used for|do)\b", q):
        return "tax", {"mygov_basics"}, "mygov_basics"
    if re.search(r"\b(tax resident|tax residency|resident for tax purposes|residency for tax)\b", q):
        return "tax", {"tax_residency"}, "tax_residency"
    if re.search(r"\bsuper(?:annuation)?\b", q) and re.search(r"\b(what|how|work|employer|contribution|visa holder)\b", q):
        return "tax", {"super_basics"}, "super_basics"
    if re.search(r"\btax return\b", q) and re.search(r"\b(how|where|lodge|file|submit|complete|online)\b", q):
        return "tax", {"tax_lodge"}, "tax_lodge"
    if re.search(r"\b(?:what is|what does|explain|meaning of)\s+(?:a\s+|the\s+)?tax return\b", q):
        return "tax", {"tax_return_basics"}, "tax_return_basics"
    if re.search(r"\b(income tax|how tax works|why .*pay tax|tax on (?:my )?(?:income|pay|wages)|tax rates?)\b", q):
        return "tax", {"tax_basics"}, "tax_basics"
    if re.search(r"\bvisa\b", q) and re.search(r"\brefund\b", q) and not re.search(r"\btax\b", q):
        return "visa", {"visa_refund"}, "visa_refund"
    if re.search(r"\b(tax|ato|super|mygov)\b", q) or (tax_refund and not re.search(r"\bvisa\b", q)):
        return "tax", set(), "unsupported_tax_intent"
    if re.search(r"\b(coe|confirmation of enrolment|confirmation of enrollment)\b", q):
        return "visa", {"student_coe"}, "student_coe"
    if re.search(r"\b(oshc|overseas student health cover|health insurance)\b", q) and re.search(r"\b(student|visa|oshc|overseas)\b", q):
        return "visa", {"student_oshc"}, "student_oshc"
    if re.search(r"\b(485|temporary graduate visa)\b", q) and re.search(r"\b(requirement|requirements|eligible|eligibility|qualify|how long|apply|application|after study)\b", q):
        return "visa", {"graduate_study_requirement"}, "graduate_study_requirement"
    if re.search(r"\b(visa|immiaccount)\b", q) and re.search(r"\b(address|contact details)\b", q) and re.search(r"\b(update|change|changed|new)\b", q):
        return "visa", {"visa_address_update"}, "visa_address_update"
    if re.search(r"\bvisa\b", q) and re.search(r"\b(refus(?:e|ed|al)|reject(?:ed|ion)?|denied|appeal|review rights)\b", q):
        return "visa", {"visa_refusal"}, "visa_refusal"
    if re.search(r"\b(bridging visa|bva)\b", q):
        return "visa", {"bridging_visa_basics"}, "bridging_visa_basics"
    if re.search(r"\bvisa\b", q) and re.search(r"\b(status|progress|pending)\b", q) and re.search(r"\b(application|applied|lodged|online|immiaccount)\b", q):
        return "visa", {"visa_application_status"}, "visa_application_status"
    if re.search(r"\bvisa\b", q) and re.search(r"\b(condition|conditions|vevo)\b", q) and re.search(r"\b(hold|held|have|current|already|granted|vevo)\b", q):
        return "visa", {"visa_vevo"}, "visa_vevo"
    if re.search(r"\bvisa\b", q) and re.search(r"\b(passport|travel document)\b", q) and re.search(r"\b(update|change|changed)\b", q) and re.search(r"\b(application|applied|lodged|lodging)\b", q):
        return "visa", {"visa_passport_update"}, "visa_passport_update"
    if re.search(r"\bvisa\b", q) and re.search(r"\b(health|medical|examination|examinations)\b", q):
        return "visa", {"visa_health"}, "visa_health"
    if re.search(r"\bvisa\b", q) and re.search(r"\b(fee|cost|price|pricing|charge)\b", q) and re.search(r"\b(processing|time|times)\b", q):
        return "visa", {"visa_fee_time"}, "visa_fee_time"
    if re.search(r"\b(visa|visas)\b", q) and re.search(r"\b(holiday|visit|tourism)\b", q) and re.search(r"\b(compare|options|finder|which)\b", q):
        return "visa", {"visa_finder"}, "visa_finder"
    if re.search(r"\bvisitor visa\b", q) and re.search(r"\b(expire|expiring|expires|stay longer|extend|extension)\b", q):
        return "visa", {"visitor_stay_longer"}, "visitor_stay_longer"
    if re.search(r"\bvisitor visa\b", q) and re.search(r"\b(apply|applying|submit|lodge|tourist)\b", q):
        return "visa", {"visitor_apply"}, "visitor_apply"
    if re.search(r"\b(?:what is|explain|meaning of)\s+(?:a\s+|the\s+)?visitor visa\b", q):
        return "visa", {"visitor_visa_basics"}, "visitor_visa_basics"
    if re.search(r"\b(?:what is|explain|meaning of)\s+(?:a\s+|the\s+)?student visa\b", q):
        return "visa", {"student_visa_basics"}, "student_visa_basics"
    if selected_topic == "visa" and re.search(r"\bgraduat(?:e|es|ed|ing|ion)\b", q) and re.search(r"\b(work|working|hours?|employment)\b", q):
        return "visa", {"student_work_after_study"}, "student_work_after_study"
    student = bool(re.search(r"\b(students?|guardian|subclass 500|subclass 590)\b", q))
    dated_change = bool(re.search(r"\b(2 oct|oct 2|2 october|october 2)\b", q)) and "visa" in q
    post_study = asks_about_post_study(q) or broad_graduation_question(q)
    if student or dated_change or post_study:
        if asks_about_other_october_change(q):
            return "visa", set(), "unreviewed_change_date"
        if post_study:
            return "visa", {"student_post_study"}, "student_post_study"
        if re.search(r"\b(work|working|hours?|employment)\b", q):
            return "visa", {"student_work"}, "student_work"
        if re.search(r"\b(fee|cost|price|refund|processing|appeal|cancel)\b", q):
            return "visa", set(), "unsupported_visa_intent"
        if re.search(r"\b(family|partner|spouse|child|children|dependant|dependent|subsequent entrant)\b", q):
            return "visa", {"student_family"}, "student_family"
        if asks_about_provider_transfer(q):
            return "visa", {"student_transfer"}, "student_transfer"
        if re.search(r"\b(apply|applying|application|lodge|lodging|onshore|offshore|location)\b", q):
            if re.search(r"\b(onshore|offshore|inside australia|in australia|while in australia|another|further|location)\b", q):
                return "visa", {"student_location"}, "student_location"
            return "visa", {"student_application"}, "student_application"
        if re.search(r"\b(change|changed|changes|new|recent|rule|rules|reform|update|updated|2026|october|oct)\b", q):
            return "visa", {"student_changes", "student_location", "student_family", "student_transfer"}, "student_changes"
        return "visa", set(), "unsupported_visa_intent"
    if re.search(r"\b(visa|immigration|visitor|tourist)\b", q):
        return "visa", set(), "unsupported_visa_intent"
    return selected_topic if selected_topic in {"tax", "visa"} else None, set(), "outside_scope"


def search_sources(
    connection: sqlite3.Connection, question: str, topic: str = "tax", limit: int = 5
) -> tuple[list[dict], str]:
    domain, allowed_intents, route = route_question(question, topic)
    if not allowed_intents or domain is None:
        return [], route
    query_terms = terms("graduation" if broad_graduation_question(question) else question)
    if not query_terms:
        return [], "no_search_terms"
    # Quoting every token makes user input data, never FTS query syntax.
    match = " OR ".join(f'"{word}"' for word in query_terms)
    intent_marks = ",".join("?" for _ in allowed_intents)
    rows = connection.execute(
        f"""SELECT c.*, bm25(source_fts, 2.5, 1.3, 1.0, 1.8) AS fts_rank
             FROM source_fts JOIN source_chunks AS c ON c.id = source_fts.rowid
             WHERE source_fts MATCH ? AND c.status='approved' AND c.topic=?
                   AND c.intent IN ({intent_marks})
             ORDER BY fts_rank LIMIT 20""",
        (match, domain, *sorted(allowed_intents)),
    ).fetchall()
    required = 1 if len(query_terms) == 1 else max(2, math.ceil(len(query_terms) * 0.5))
    results = []
    for row in rows:
        haystack = set(terms(" ".join(str(row[field]) for field in ("title", "section", "body", "keywords"))))
        overlap = len(set(query_terms) & haystack)
        if overlap < required:
            continue
        result = dict(row)
        result["term_overlap"] = overlap
        result["query_term_count"] = len(query_terms)
        results.append(result)
    # For broad change questions, put the overview first; within each group,
    # lexical coverage and FTS5's BM25 score decide the order.
    results.sort(key=lambda item: (
        0 if (
            route == "student_changes" and item["intent"] == "student_changes" and "Overview" in item["section"]
            or route == "student_post_study" and "vevo" in item["section"].lower()
        ) else 1,
        -item["term_overlap"], item["fts_rank"],
    ))
    return results[:limit], "matched" if results else "weak_or_no_match"
