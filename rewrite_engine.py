import re


def rewrite_sentence(sentence, suggestion_type, required_term=None):
    text = sentence

    replacements = {
        "absolute": [
            (r"\bnever\b", "is designed to help avoid"),
            (r"\balways\b", "is intended to"),
            (r"\bno matter what\b", "in many situations")
        ],
        "guarantee": [
            (r"\bguarantees?\b", "is designed to support"),
            (r"\bguaranteed\b", "designed to support"),
            (r"\brisk[- ]free\b", "designed with care"),
            (r"\b100%\s*safe\b", "designed with safety in mind"),
            (r"\b100%\s*effective\b", "designed to be effective"),
            (r"\b100%\s*secure\b", "designed with security in mind"),
            (r"\b100%\s*cure\b", "designed to support wellbeing")
        ],
        "superiority": [
            (r"\bbest\b", "a valuable"),
            (r"\bnumber one\b", "a trusted"),
            (r"\bno\.?\s*1\b", "a trusted"),
            (r"\bunbeatable\b", "competitive")
        ],
        "pressure": [
            (r"\bbuy now or\b", "You can explore the product and"),
            (r"\bact immediately\b", "Consider taking the next step"),
            (r"\blast chance\b", "Learn more about this opportunity"),
            (r"\bdon't miss out\b", "Explore what is available")
        ],
        "health": [
            (r"\bcures?\b", "may support"),
            (r"\bcured\b", "may support"),
            (r"\btreats\b", "may help manage"),
            (r"\bheals\b", "may support recovery")
        ],
        "restricted": [
            (r"\bguaranteed\b", "designed to support"),
            (r"\brisk[- ]free\b", "carefully designed"),
            (r"\b100% cure\b", "supportive solution")
        ]
    }

    for pattern, replacement in replacements.get(suggestion_type, []):
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    if suggestion_type == "required" and required_term:
        text = text.rstrip(".!?") + f", with {required_term}."

    if text == sentence:
        text = (
            "Please revise this sentence to make the claim "
            "clear, accurate and aligned with the brand guidelines."
        )

    return text