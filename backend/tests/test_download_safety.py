from core.downloads import content_disposition


def test_content_disposition_blocks_header_and_path_injection():
    value = content_disposition(
        "attachment", '..\\statement\";\r\nX-Evil: yes.csv', "statement.csv")

    assert "\r" not in value
    assert "\n" not in value
    assert "\\" not in value
    assert "../" not in value
    assert value.startswith('attachment; filename="')
    assert "filename*=UTF-8''" in value


def test_content_disposition_preserves_unicode_via_rfc5987():
    value = content_disposition("inline", "वेतन पर्ची.pdf", "payslip.pdf")

    assert value.startswith('inline; filename="')
    assert "%E0%A4%B5" in value


def test_content_disposition_rejects_unknown_disposition():
    value = content_disposition("unexpected", "report.csv")

    assert value.startswith("attachment;")
