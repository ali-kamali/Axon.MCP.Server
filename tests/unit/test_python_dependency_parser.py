from pathlib import Path

from src.parsers.python_dependency_parser import PythonDependencyParser


def test_parse_requirements_txt_handles_inline_comments_and_markers(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text(
        """
flask==2.3.3 # pinned for prod
uvicorn[standard]>=0.23 ; python_version >= \"3.10\"
-r base.txt
        """.strip(),
        encoding="utf-8",
    )

    parser = PythonDependencyParser()
    packages = parser.parse_requirements_txt(req)

    assert len(packages) == 2
    assert packages[0].package_name == "flask"
    assert packages[0].version == "2.3.3"
    assert packages[0].version_constraint == "==2.3.3"

    assert packages[1].package_name == "uvicorn"
    assert packages[1].version is None
    assert packages[1].version_constraint == ">=0.23"


def test_parse_pep_508_string_strips_environment_markers() -> None:
    parser = PythonDependencyParser()

    package = parser._parse_pep_508_string(
        'pydantic>=2.5 ; python_version >= "3.10"',
        "pyproject.toml",
    )

    assert package is not None
    assert package.package_name == "pydantic"
    assert package.version_constraint == ">=2.5"


def test_parse_requirements_txt_handles_line_continuations_and_hashes(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text(
        (
            "charset-normalizer==3.3.2 \\\n"
            "  --hash=sha256:abc123 \\\n"
            "  --hash=sha256:def456\n"
        ),
        encoding="utf-8",
    )

    parser = PythonDependencyParser()
    packages = parser.parse_requirements_txt(req)

    assert len(packages) == 1
    assert packages[0].package_name == "charset-normalizer"
    assert packages[0].version == "3.3.2"
    assert packages[0].version_constraint == "==3.3.2"


def test_parse_file_dispatch_for_python_dependency_files(tmp_path: Path) -> None:
    parser = PythonDependencyParser()

    req = tmp_path / "dev-requirements.txt"
    req.write_text("pytest==8.0.0\n", encoding="utf-8")

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
dependencies = ["fastapi>=0.100"]
        """.strip(),
        encoding="utf-8",
    )

    pipfile = tmp_path / "Pipfile"
    pipfile.write_text(
        """
[packages]
requests = "==2.31.0"
[dev-packages]
black = "*"
        """.strip(),
        encoding="utf-8",
    )

    req_packages = parser.parse_file(req)
    pyproject_packages = parser.parse_file(pyproject)
    pipfile_packages = parser.parse_file(pipfile)

    assert [p.package_name for p in req_packages] == ["pytest"]
    assert [p.package_name for p in pyproject_packages] == ["fastapi"]
    assert {p.package_name for p in pipfile_packages} == {"requests", "black"}
