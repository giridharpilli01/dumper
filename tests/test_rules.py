from pathlib import Path
from dump import Rule, Action, Target, RuleEngine, Settings

def test_rule_specificity():
    p_rule = Rule(Action.INCLUDE, Target.PATH, "a/b/c", normalized_path=Path("/a/b/c"))
    glob_rule = Rule(Action.EXCLUDE, Target.FILENAME, "*_test.py")
    exact_file = Rule(Action.EXCLUDE, Target.FILENAME, "test.py")
    ext_rule = Rule(Action.EXCLUDE, Target.EXTENSION, ".log")

    assert p_rule.specificity() > exact_file.specificity()
    assert exact_file.specificity() > glob_rule.specificity()
    assert glob_rule.specificity() > ext_rule.specificity()

def test_precedence_most_specific_and_equal_include_preference(tmp_path: Path):
    settings = Settings()
    out_dir = tmp_path / "output"

    f1 = tmp_path / "src" / "generated" / "special.py"
    rules = [
        Rule(Action.INCLUDE, Target.PATH, str(tmp_path / "src"), normalized_path=tmp_path / "src"),
        Rule(Action.EXCLUDE, Target.PATH, str(tmp_path / "src" / "generated"), normalized_path=tmp_path / "src" / "generated"),
        Rule(Action.INCLUDE, Target.PATH, str(f1), normalized_path=f1),
    ]

    res = RuleEngine.evaluate_file(f1, rules, settings, out_dir)
    assert res.eligible is True
    assert res.winning_rule == rules[2]

    # Equal specificity test
    f2 = tmp_path / "src" / "sample.log"
    equal_rules = [
        Rule(Action.EXCLUDE, Target.EXTENSION, ".log"),
        Rule(Action.INCLUDE, Target.EXTENSION, ".log"),
    ]
    res2 = RuleEngine.evaluate_file(f2, equal_rules, settings, out_dir)
    assert res2.eligible is True  # Equal specificity -> INCLUDE wins

def test_explain_file_detailed_inspection(tmp_path: Path):
    settings = Settings()
    out_dir = tmp_path / "output"
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    target = src_dir / "app.py"
    target.write_text("print('hello')", encoding="utf-8")
    
    rules = [Rule(Action.INCLUDE, Target.PATH, str(src_dir), normalized_path=src_dir)]

    explanation = RuleEngine.explain_file(target, rules, settings, out_dir)
    assert explanation["effective_eligible"] is True
    assert len(explanation["matching_rules"]) == 1
    assert "Matched manifest rule" in explanation["reason"]