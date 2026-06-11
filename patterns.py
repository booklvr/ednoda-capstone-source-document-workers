"""
- Author: Tianhao Cao
- Last Updates: 2026-05-06
29 spaCy DependencyMatcher grammar patterns for ESL sentence tagging.

See docs/grammar_tagging.md for the full template reference and coverage benchmarks.
"""

import spacy
from spacy.matcher import DependencyMatcher

nlp = spacy.load("en_core_web_sm")
matcher = DependencyMatcher(nlp.vocab)

# ---------------------------------------------------------------------------
# Original 4 templates
# ---------------------------------------------------------------------------

# 1. Present Simple Question with do/does (e.g., "Do you like pizza?")
pattern_present_simple_q = [
    {"RIGHT_ID": "root_node", "RIGHT_ATTRS": {}},
    {
        "LEFT_ID": "root_node",
        "REL_OP": ">",
        "RIGHT_ID": "aux_do",
        "RIGHT_ATTRS": {"LOWER": {"IN": ["do", "does"]}, "DEP": "aux"},
    },
    {
        "LEFT_ID": "root_node",
        "REL_OP": ">",
        "RIGHT_ID": "punct",
        "RIGHT_ATTRS": {"ORTH": "?"},
    },
]

# 2. There is/are ___ (e.g., "There is a dog.")
pattern_there_be = [
    {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be"}},
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "there_expl",
        "RIGHT_ATTRS": {"LOWER": "there", "DEP": "expl"},
    },
]

# 3. Comparative: ___ is -er than ___ (e.g., "A lion is bigger than a dog.")
pattern_comparative = [
    {"RIGHT_ID": "adj_comp", "RIGHT_ATTRS": {"TAG": "JJR"}},
    {
        "LEFT_ID": "adj_comp",
        "REL_OP": ">",
        "RIGHT_ID": "than",
        "RIGHT_ATTRS": {"LOWER": "than", "DEP": "prep"},
    },
]

# 4. Present Continuous: subject is ___-ing (e.g., "She is listening to music.")
pattern_present_continuous = [
    {"RIGHT_ID": "verb_ing", "RIGHT_ATTRS": {"TAG": "VBG"}},
    {
        "LEFT_ID": "verb_ing",
        "REL_OP": ">",
        "RIGHT_ID": "aux_be",
        "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "aux"},
    },
]

# ---------------------------------------------------------------------------
# New templates derived from corpus analysis (frequency-ordered)
# ---------------------------------------------------------------------------

# 5. Be + attribute noun statement (e.g., "My name is Tom.", "This is my dad.")
#    ROOT=be, nsubj + attr
pattern_be_attr_statement = [
    {"RIGHT_ID": "be_root", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
    {
        "LEFT_ID": "be_root",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "be_root",
        "REL_OP": ">",
        "RIGHT_ID": "attr_noun",
        "RIGHT_ATTRS": {"DEP": "attr"},
    },
]

# 6. Be + adjective statement (e.g., "The bus is big.", "You're welcome.")
#    ROOT=be, nsubj + acomp
pattern_be_adjective = [
    {"RIGHT_ID": "be_root", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
    {
        "LEFT_ID": "be_root",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "be_root",
        "REL_OP": ">",
        "RIGHT_ID": "adj_comp",
        "RIGHT_ATTRS": {"DEP": "acomp"},
    },
]

# 7. Can question (e.g., "Can I take pictures?", "Can you help me?")
#    ROOT=VERB, aux=can + ?
pattern_can_question = [
    {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "modal_can",
        "RIGHT_ATTRS": {"LOWER": "can", "DEP": "aux"},
    },
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "quest_mark",
        "RIGHT_ATTRS": {"ORTH": "?"},
    },
]

# 8. Like statement (e.g., "I like milk.", "I don't like pizza.")
#    ROOT=like, nsubj + dobj
pattern_like_statement = [
    {"RIGHT_ID": "like_verb", "RIGHT_ATTRS": {"LEMMA": "like", "DEP": "ROOT"}},
    {
        "LEFT_ID": "like_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "like_verb",
        "REL_OP": ">",
        "RIGHT_ID": "obj",
        "RIGHT_ATTRS": {"DEP": "dobj"},
    },
]

# 9. Be from place (e.g., "I'm from Canada.", "She's from Korea.")
#    ROOT=be, nsubj + prep(from)
pattern_be_from_place = [
    {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "from_prep",
        "RIGHT_ATTRS": {"LOWER": "from", "DEP": "prep"},
    },
]

# 10. Have statement (e.g., "I have scissors.", "The car has a siren.")
#     ROOT=have, nsubj + dobj
pattern_have_statement = [
    {"RIGHT_ID": "have_verb", "RIGHT_ATTRS": {"LEMMA": "have", "DEP": "ROOT"}},
    {
        "LEFT_ID": "have_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "have_verb",
        "REL_OP": ">",
        "RIGHT_ID": "obj",
        "RIGHT_ATTRS": {"DEP": "dobj"},
    },
]

# 11. Wh-question with be (e.g., "How are you?", "Where is the bathroom?")
#     ROOT=be + wh-word(advmod) + ?
pattern_wh_question_be = [
    {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "wh_word",
        "RIGHT_ATTRS": {"DEP": "advmod", "TAG": {"IN": ["WRB", "WP"]}},
    },
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "quest_mark",
        "RIGHT_ATTRS": {"ORTH": "?"},
    },
]

# 12. Can ability statement (e.g., "I can swim.", "I can't ski.")
#     ROOT=VERB, aux=can + nsubj  (no question mark — distinguishes from can_question)
pattern_can_ability = [
    {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "modal_can",
        "RIGHT_ATTRS": {"LOWER": "can", "DEP": "aux"},
    },
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
]

# 13. Want statement (e.g., "I want a comic book.", "I want a puppy.")
#     ROOT=want, nsubj + dobj
pattern_want_statement = [
    {"RIGHT_ID": "want_verb", "RIGHT_ATTRS": {"LEMMA": "want", "DEP": "ROOT"}},
    {
        "LEFT_ID": "want_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "want_verb",
        "REL_OP": ">",
        "RIGHT_ID": "obj",
        "RIGHT_ATTRS": {"DEP": "dobj"},
    },
]

# 14. Let's suggestion (e.g., "Let's go shopping.", "Let's play a board game.")
#     ROOT=let + ccomp(go/play/...)
pattern_lets_suggestion = [
    {"RIGHT_ID": "let_verb", "RIGHT_ATTRS": {"LOWER": "let", "DEP": "ROOT"}},
    {
        "LEFT_ID": "let_verb",
        "REL_OP": ">",
        "RIGHT_ID": "suggestion_verb",
        "RIGHT_ATTRS": {"DEP": "ccomp"},
    },
]

# 15. Going to future (e.g., "I'm going to visit my grandparents.", "She's going to stay home.")
#     ROOT=go(ing) + aux=be + xcomp
pattern_going_to_future = [
    {"RIGHT_ID": "going_verb", "RIGHT_ATTRS": {"LEMMA": "go", "DEP": "ROOT"}},
    {
        "LEFT_ID": "going_verb",
        "REL_OP": ">",
        "RIGHT_ID": "be_aux",
        "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "aux"},
    },
    {
        "LEFT_ID": "going_verb",
        "REL_OP": ">",
        "RIGHT_ID": "future_verb",
        "RIGHT_ATTRS": {"DEP": "xcomp"},
    },
]

# 16. Be + prepositional phrase (e.g., "It's on the table.", "She's at school.", "I'm in grade 6.")
#     ROOT=be, nsubj + prep (any preposition — generalises be_from_place)
pattern_be_prepositional = [
    {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "prep",
        "RIGHT_ATTRS": {"DEP": "prep"},
    },
]

# 17. Modal advice / future (e.g., "You should eat vegetables.", "I'll visit my grandpa.")
#     ROOT=VERB, aux=MD (any modal: should/will/would/might/must/shall), nsubj
pattern_should_will_modal = [
    {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "modal",
        "RIGHT_ATTRS": {"TAG": "MD", "DEP": "aux"},
    },
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
]

# 18. Can't / cannot (e.g., "I can't swim.", "You can't bring animals.")
#     ROOT=VERB, aux=can(LEMMA), neg + nsubj
#     Note: "can't" tokenises as "ca"(LEMMA=can) + "n't"(DEP=neg)
pattern_cant_negative = [
    {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"DEP": "ROOT", "POS": "VERB"}},
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "modal_can",
        "RIGHT_ATTRS": {"LEMMA": "can", "DEP": "aux"},
    },
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "negation",
        "RIGHT_ATTRS": {"DEP": "neg"},
    },
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
]

# 19. Imperative with direct object (e.g., "Try this.", "Catch the ball.", "Open the door.")
#     ROOT=VB (base-form verb) + dobj — imperatives have no nsubj
pattern_imperative = [
    {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"TAG": "VB", "DEP": "ROOT"}},
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "obj",
        "RIGHT_ATTRS": {"DEP": "dobj"},
    },
]

# 20. Like + gerund (e.g., "I like playing basketball.", "I like looking at the stars.")
#     ROOT=like, nsubj + xcomp(VBG)
pattern_like_gerund = [
    {"RIGHT_ID": "like_verb", "RIGHT_ATTRS": {"LEMMA": "like", "DEP": "ROOT"}},
    {
        "LEFT_ID": "like_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "like_verb",
        "REL_OP": ">",
        "RIGHT_ID": "gerund",
        "RIGHT_ATTRS": {"DEP": "xcomp", "TAG": "VBG"},
    },
]

# 21. Want + to-infinitive (e.g., "I want to be a scientist.", "I want to go camping.")
#     ROOT=want, nsubj + xcomp (to-inf clause, not bare dobj — different from want_statement)
pattern_want_to_inf = [
    {"RIGHT_ID": "want_verb", "RIGHT_ATTRS": {"LEMMA": "want", "DEP": "ROOT"}},
    {
        "LEFT_ID": "want_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "want_verb",
        "REL_OP": ">",
        "RIGHT_ID": "inf_clause",
        "RIGHT_ATTRS": {"DEP": "xcomp"},
    },
]

# 22. How about + gerund/suggestion (e.g., "How about playing tennis?", "How about reusing papers?")
#     ROOT=about (ADP) + advmod=how + pcomp
pattern_how_about = [
    {"RIGHT_ID": "about_root", "RIGHT_ATTRS": {"LOWER": "about", "DEP": "ROOT"}},
    {
        "LEFT_ID": "about_root",
        "REL_OP": ">",
        "RIGHT_ID": "how_word",
        "RIGHT_ATTRS": {"LOWER": "how", "DEP": "advmod"},
    },
]

# ---------------------------------------------------------------------------
# Register all templates
# ---------------------------------------------------------------------------

matcher.add("present_simple_question", [pattern_present_simple_q])
matcher.add("there_is_are", [pattern_there_be])
matcher.add("comparative", [pattern_comparative])
matcher.add("present_continuous", [pattern_present_continuous])
matcher.add("be_attr_statement", [pattern_be_attr_statement])
matcher.add("be_adjective", [pattern_be_adjective])
matcher.add("can_question", [pattern_can_question])
matcher.add("like_statement", [pattern_like_statement])
matcher.add("be_from_place", [pattern_be_from_place])
matcher.add("have_statement", [pattern_have_statement])
matcher.add("wh_question_be", [pattern_wh_question_be])
matcher.add("can_ability", [pattern_can_ability])
matcher.add("want_statement", [pattern_want_statement])
matcher.add("lets_suggestion", [pattern_lets_suggestion])
matcher.add("going_to_future", [pattern_going_to_future])
matcher.add("be_prepositional", [pattern_be_prepositional])
matcher.add("should_will_modal", [pattern_should_will_modal])
matcher.add("cant_negative", [pattern_cant_negative])
matcher.add("imperative", [pattern_imperative])
matcher.add("like_gerund", [pattern_like_gerund])
matcher.add("want_to_inf", [pattern_want_to_inf])
matcher.add("how_about", [pattern_how_about])

# 23. Simple SVO — past or present (e.g., "I cleaned the street.", "She collects stamps.")
#     ROOT=VBD/VBP/VBZ + nsubj + dobj (no modal aux — those are caught by should_will_modal)
#     VBD=past, VBP=present non-3rd-person, VBZ=3rd-person singular present
pattern_simple_svo = [
    {
        "RIGHT_ID": "root_verb",
        "RIGHT_ATTRS": {
            "DEP": "ROOT",
            "POS": "VERB",
            "TAG": {"IN": ["VBD", "VBP", "VBZ"]},
        },
    },
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "obj",
        "RIGHT_ATTRS": {"DEP": "dobj"},
    },
]

# 24. Looks/sounds/feels + adjective (e.g., "That looks fun.", "It sounds great.")
#     ROOT=look/sound/seem/feel + nsubj + acomp
pattern_looks_sounds_adj = [
    {
        "RIGHT_ID": "sense_verb",
        "RIGHT_ATTRS": {
            "LEMMA": {"IN": ["look", "sound", "seem", "feel", "smell", "taste"]},
            "DEP": "ROOT",
        },
    },
    {
        "LEFT_ID": "sense_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "sense_verb",
        "REL_OP": ">",
        "RIGHT_ID": "adj",
        "RIGHT_ATTRS": {"DEP": "acomp"},
    },
]

# 25. Go to place (e.g., "I go to school.", "I went to a festival.")
#     ROOT=go + nsubj + prep(to)
pattern_go_to_place = [
    {"RIGHT_ID": "go_verb", "RIGHT_ATTRS": {"LEMMA": "go", "DEP": "ROOT"}},
    {
        "LEFT_ID": "go_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "go_verb",
        "REL_OP": ">",
        "RIGHT_ID": "to_prep",
        "RIGHT_ATTRS": {"LOWER": "to", "DEP": "prep"},
    },
]

# 26. Whose question (e.g., "Whose pen is this?", "Whose bag is that?")
#     ROOT=be + attr(NOUN with poss child) + ?
pattern_whose_question = [
    {"RIGHT_ID": "be_verb", "RIGHT_ATTRS": {"LEMMA": "be", "DEP": "ROOT"}},
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "thing",
        "RIGHT_ATTRS": {"DEP": "attr", "POS": "NOUN"},
    },
    {
        "LEFT_ID": "thing",
        "REL_OP": ">",
        "RIGHT_ID": "whose_poss",
        "RIGHT_ATTRS": {"LOWER": "whose", "DEP": "poss"},
    },
    {
        "LEFT_ID": "be_verb",
        "REL_OP": ">",
        "RIGHT_ID": "quest_mark",
        "RIGHT_ATTRS": {"ORTH": "?"},
    },
]

# 27. Don't / negative imperative (e.g., "Don't run.", "Don't worry.")
#     ROOT=VB + neg (no nsubj — negative imperative)
#     "don't" tokenises as "do"(ROOT) + "n't"(neg)
pattern_dont_imperative = [
    {"RIGHT_ID": "root_verb", "RIGHT_ATTRS": {"TAG": "VB", "DEP": "ROOT"}},
    {
        "LEFT_ID": "root_verb",
        "REL_OP": ">",
        "RIGHT_ID": "negation",
        "RIGHT_ATTRS": {"DEP": "neg"},
    },
]

# 28. Short yes/no answer with do (e.g., "Yes, I did.", "No, I don't.")
#     ROOT=do/did + nsubj + intj(yes/no)
pattern_short_answer_do = [
    {"RIGHT_ID": "do_verb", "RIGHT_ATTRS": {"LEMMA": "do", "DEP": "ROOT"}},
    {
        "LEFT_ID": "do_verb",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
    {
        "LEFT_ID": "do_verb",
        "REL_OP": ">",
        "RIGHT_ID": "yes_no",
        "RIGHT_ATTRS": {"LOWER": {"IN": ["yes", "no"]}, "DEP": "intj"},
    },
]

# 29. No, can't response (e.g., "No, you can't.", "Sorry, I can't.")
#     ROOT=can(AUX) + neg + nsubj + intj — standalone can't with interjection
pattern_no_cant_response = [
    {"RIGHT_ID": "can_root", "RIGHT_ATTRS": {"LEMMA": "can", "DEP": "ROOT"}},
    {
        "LEFT_ID": "can_root",
        "REL_OP": ">",
        "RIGHT_ID": "negation",
        "RIGHT_ATTRS": {"DEP": "neg"},
    },
    {
        "LEFT_ID": "can_root",
        "REL_OP": ">",
        "RIGHT_ID": "subj",
        "RIGHT_ATTRS": {"DEP": "nsubj"},
    },
]

matcher.add("simple_svo", [pattern_simple_svo])
matcher.add("looks_sounds_adj", [pattern_looks_sounds_adj])
matcher.add("go_to_place", [pattern_go_to_place])
matcher.add("whose_question", [pattern_whose_question])
matcher.add("dont_imperative", [pattern_dont_imperative])
matcher.add("short_answer_do", [pattern_short_answer_do])
matcher.add("no_cant_response", [pattern_no_cant_response])
This is the grammar templates we have, should we include this in? we are already using this for something else, but remember, we also don't want to be too clean where we may reduce or remove certain things from text chunks which we may want that we have not captured 