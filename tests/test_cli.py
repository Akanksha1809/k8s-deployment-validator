import json

from k8s_validator.cli import EXIT_ERROR, EXIT_FAILED, EXIT_OK, main


def test_good_examples_pass_strict(examples_dir, capsys):
    assert main([str(examples_dir / "good"), "--strict", "--no-color"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "0 critical, 0 warning(s)" in out
    assert "FAIL" not in out


def test_bad_examples_fail(examples_dir, capsys):
    assert main([str(examples_dir / "bad"), "--no-color"]) == EXIT_FAILED
    out = capsys.readouterr().out
    for rule in ("image-tag", "privileged", "run-as-root", "resources", "probes", "replicas", "labels"):
        assert rule in out


def test_warnings_only_exit_zero_unless_strict(tmp_path):
    manifest = tmp_path / "svc.yaml"
    manifest.write_text("apiVersion: v1\nkind: Service\nmetadata: {name: svc}\nspec: {selector: {app: x}}\n")
    assert main([str(manifest), "--no-color"]) == EXIT_OK
    assert main([str(manifest), "--no-color", "--strict"]) == EXIT_FAILED


def test_json_output(examples_dir, capsys):
    main([str(examples_dir / "bad"), "-o", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["critical"] > 0
    assert {"rule", "severity", "kind", "name", "file", "container"} <= payload["findings"][0].keys()


def test_missing_path_returns_error(tmp_path, capsys):
    assert main([str(tmp_path / "nope")]) == EXIT_ERROR
    assert "error:" in capsys.readouterr().err
