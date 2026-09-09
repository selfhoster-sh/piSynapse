"""Signature normalization (collective-learning Phase 2)."""
from textnorm import normalize_signature as sig


def test_plain_text_unchanged_apart_from_casefold():
    assert sig("Notları listele") == "notları listele"
    assert sig("  hava   nasıl? ") == "hava nasıl?"


def test_email_masked():
    assert sig("Ahmet'e ahmet.yilmaz@example.com adresine mail at") == \
        "ahmet'e [email] adresine mail at"


def test_url_masked():
    assert sig("şu siteye bak https://ornek.com/sayfa?q=1 tamam") == \
        "şu siteye bak [url] tamam"


def test_phone_masked():
    assert sig("beni +90 555 123 45 67 numaradan ara") == "beni [phone] numaradan ara"
    assert sig("beni 0555 123 45 67 numaradan ara") == "beni [phone] numaradan ara"


def test_date_masked():
    assert sig("yarın 12.03.2026 toplantı ekle") == "yarın [date] toplantı ekle"


def test_long_numbers_masked_short_kept():
    assert sig("12345678901 nolu hastaya bak") == "[number] nolu hastaya bak"
    assert sig("2. notu oku") == "2. notu oku"


def test_cross_user_contact_variants_share_signature():
    a = sig("ahmet@example.com adresine mail at")
    b = sig("mehmet@example.com adresine mail at")
    assert a == b == "[email] adresine mail at"


def test_bare_names_stay_documented_residual():
    # No NER at Pi budget: bare names still split signatures. Quorum +
    # admin review (Phase 3/4) mitigate; contact details never leak either way.
    assert "ahmet" in sig("ahmet'e mail at")


def test_idempotent_and_empty_safe():
    once = sig("Mail at john@x.com 0555 111 22 33")
    assert sig(once) == once
    assert sig("") == ""
    assert sig("   ") == ""
