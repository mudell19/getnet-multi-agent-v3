from getnet_multi_agent.format.quality import MAX_WORDS, check_answer, fix_answer, word_count


def test_fr035_fix_replaces_em_and_en_dashes():
    text, violations = fix_answer("Seu dinheiro cai amanhã — antes das 12h – sem custo.")
    assert "—" not in text and "–" not in text
    assert text == "Seu dinheiro cai amanhã, antes das 12h, sem custo."
    assert violations == ["dash"]


def test_fr035_fix_digit_range_keeps_hyphen():
    text, violations = fix_answer("O prazo é de 1–2 dias úteis, ou 10 — 20 dias.")
    assert text == "O prazo é de 1-2 dias úteis, ou 10-20 dias."
    assert violations == ["dash"]


def test_fr035_fix_removes_bold_and_reports():
    text, violations = fix_answer("Use o **Pix** ou o __cartão__ e *aguarde*.")
    assert text == "Use o Pix ou o cartão e aguarde."
    assert violations == ["bold"]


def test_fr035_fix_headers_bullets_blank_lines():
    raw = "## Como receber\n\n\n\n* Pix na hora\n• Cartão em 1 dia\n"
    text, violations = fix_answer(raw)
    assert text == "Como receber\n\n- Pix na hora\n- Cartão em 1 dia"
    assert violations == ["header"]


def test_fr035_fix_clean_text_untouched():
    clean = "Your sales of R$ 1,250.00 arrive on 27 Nov 2026."
    assert fix_answer(clean) == (clean, [])


def test_fr035_check_flags_iso_date():
    assert "iso_date" in check_answer("O dinheiro cai em 2026-11-27 na sua conta.", "pt")


def test_fr027_check_flags_unformatted_amount():
    assert "unformatted_amount" in check_answer("Você recebe R$ 1250.5 amanhã na conta.", "pt")
    assert "unformatted_amount" in check_answer("You get R$ 1.250,00 tomorrow.", "en")


def test_fr035_check_flags_wrong_language():
    en_text = "Your money will arrive tomorrow in your account."
    assert "language_mismatch" in check_answer(en_text, "pt")
    assert "language_mismatch" not in check_answer("Ok, obrigado.", "en")


def test_fr035_check_flags_dash_bold_table():
    found = check_answer("Taxa — **baixa**\n| a | b |", "pt")
    assert {"dash", "bold", "table"} <= set(found)


def test_fr035_check_passes_clean_pt():
    text = "Suas vendas de R$ 1.250,00 caem na sua conta em sexta-feira, 27/11/2026."
    assert check_answer(text, "pt") == []


def test_fr035_check_passes_clean_en():
    text = "Your sales of R$ 1,250.00 will be in your account on Friday, 27 Nov 2026."
    assert check_answer(text, "en") == []


def test_fr035_word_count_and_limit():
    assert word_count("one two  three\nfour") == 4
    assert MAX_WORDS == 120
