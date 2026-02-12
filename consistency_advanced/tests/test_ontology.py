from consistency_advanced.ontology.compatibility import build_hierarchy_index, is_subsumed, purpose_in_closure
from consistency_advanced.ontology.loader import load_rules, load_vocab


def test_hierarchy_subsumption():
    vocab = load_vocab("consistency_advanced/ontology/vocab.json")
    rules = load_rules("consistency_advanced/ontology/compatibility_rules.json")
    index = build_hierarchy_index(vocab, rules)

    assert is_subsumed("subject:device_identifier", "subject:cookie_id", index)
    assert is_subsumed("purpose:advertising", "purpose:marketing", index)
    assert not is_subsumed("purpose:service_provision", "purpose:advertising", index)


def test_purpose_closure():
    vocab = load_vocab("consistency_advanced/ontology/vocab.json")
    rules = load_rules("consistency_advanced/ontology/compatibility_rules.json")
    index = build_hierarchy_index(vocab, rules)

    allowed = ["purpose:advertising"]
    assert purpose_in_closure("purpose:marketing", allowed, index)
    assert not purpose_in_closure("purpose:analytics", allowed, index)


def test_vocab_dir_loads():
    vocab = load_vocab("consistency_advanced/ontology/vocab")
    assert any(term.uri == "basis:consent" for term in vocab.legal_bases)
    assert any(term.uri == "recipient:partner" for term in vocab.recipients)
