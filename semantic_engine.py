import re


def analyse_content(content, guidelines):
    findings = []

    sentences = re.split(r'(?<=[.!?])\s+', content.strip())

    patterns = [
        {
            "pattern": r"\b(never|always|no matter what)\b",
            "title": "Absolute claim",
            "severity": "high",
            "reason": "The sentence makes an absolute promise that may be difficult to substantiate.",
            "suggestion_type": "absolute"
        },
        {
            "pattern": r"\b(guarantee|guaranteed|risk[- ]free|100%\s*(safe|effective|secure|cure))\b",
            "title": "Unsupported guarantee",
            "severity": "high",
            "reason": "The wording promises a result or level of safety without supporting evidence.",
            "suggestion_type": "guarantee"
        },
        {
            "pattern": r"\b(best|number one|no\.?\s*1|unbeatable)\b",
            "title": "Unsubstantiated superiority",
            "severity": "medium",
            "reason": "The content claims superiority without providing evidence.",
            "suggestion_type": "superiority"
        },
        {
            "pattern": r"\b(buy now or|act immediately|last chance|don't miss out)\b",
            "title": "High-pressure language",
            "severity": "medium",
            "reason": "The wording may pressure readers instead of informing them.",
            "suggestion_type": "pressure"
        },
        {
            "pattern": r"\b(cure|cures|cured|treats|heals)\b",
            "title": "Potential health claim",
            "severity": "high",
            "reason": "This wording may imply a medical outcome and requires appropriate evidence.",
            "suggestion_type": "health"
        }
    ]

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        for rule in patterns:
            if re.search(rule["pattern"], sentence, re.IGNORECASE):
                findings.append({
                    "title": rule["title"],
                    "severity": rule["severity"],
                    "message": rule["reason"],
                    "original": sentence,
                    "suggestion_type": rule["suggestion_type"]
                })

        for term in guidelines.get("forbidden_terms", []):
            if term and re.search(
                rf"\b{re.escape(term)}\b",
                sentence,
                re.IGNORECASE
            ):
                if not any(
                    item["original"] == sentence and
                    item["title"] == "Restricted brand term"
                    for item in findings
                ):
                    findings.append({
                        "title": "Restricted brand term",
                        "severity": "high",
                        "message": f"The term '{term}' is restricted by the brand guidelines.",
                        "original": sentence,
                        "suggestion_type": "restricted"
                    })

    for term in guidelines.get("required_terms", []):
        if term and term.lower() not in content.lower():
            findings.append({
                "title": "Missing required term",
                "severity": "low",
                "message": f"The brand guideline requires the phrase '{term}'.",
                "original": content,
                "suggestion_type": "required",
                "required_term": term
            })

    return findings


def calculate_score(findings):
    score = 100

    deductions = {
        "high": 25,
        "medium": 15,
        "low": 7
    }

    for finding in findings:
        score -= deductions.get(finding["severity"], 3)

    return max(0, score)