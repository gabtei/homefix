"""Suíte de testes unitários e de integração para o gerador de dados sintéticos.

Valida regras de integridade referencial, unicidade de chaves primárias,
presença de anomalias controladas e persistência correta dos 5 arquivos CSV.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime
from pathlib import Path

import pytest

from scripts.generate_mock_data import (
    SEED_DEFAULT,
    format_currency_with_noise,
    format_date_with_noise,
    format_phone_with_noise,
    generate_clients,
    generate_contractors,
    generate_reviews,
    generate_service_orders_and_items,
    run_mock_generator,
    save_dataset_to_csv,
    validate_referential_integrity,
)


@pytest.fixture
def rng() -> random.Random:
    """Fixture que retorna um gerador determinístico."""
    return random.Random(SEED_DEFAULT)


def test_format_currency_with_noise(rng: random.Random) -> None:
    """Testa a geração de strings monetárias com diferentes estilos."""
    values = [150.0, 1250.50, 80.0]
    for val in values:
        formatted = format_currency_with_noise(val, rng)
        assert isinstance(formatted, str)
        assert len(formatted) > 0


def test_format_date_with_noise(rng: random.Random) -> None:
    """Testa formatos mistos de data gerados."""
    sample_dt = datetime(2023, 5, 20)
    for _ in range(10):
        formatted = format_date_with_noise(sample_dt, rng)
        assert any(sep in formatted for sep in ["-", "/"])


def test_format_phone_with_noise(rng: random.Random) -> None:
    """Testa formatação de telefones com e sem máscara."""
    phone = format_phone_with_noise("11", "987654321", rng)
    assert "987654321" in phone or "(11)" in phone


def test_generate_clients(rng: random.Random) -> None:
    """Valida schema e unicidade dos clientes gerados."""
    total = 20
    clients = generate_clients(total, rng)

    assert len(clients) == total
    client_ids = [c["client_id"] for c in clients]
    assert len(set(client_ids)) == total
    assert client_ids == list(range(1, total + 1))

    for c in clients:
        assert "@" in c["client_email"]
        assert c["client_state"] == "SP"
        assert len(c["client_name"]) > 3
        assert len(c["signup_date"]) > 5


def test_generate_contractors(rng: random.Random) -> None:
    """Valida schema e unicidade dos prestadores gerados."""
    total = 10
    contractors = generate_contractors(total, rng)

    assert len(contractors) == total
    ids = [k["contractor_id"] for k in contractors]
    assert len(set(ids)) == total

    for k in contractors:
        assert k["state"] == "SP"
        assert k["experience_years"] >= 1
        assert len(k["specialty"]) > 2
        assert len(k["hourly_rate"]) > 0


def test_generate_service_orders_and_items(rng: random.Random) -> None:
    """Valida ordens e itens com integridade de relacionamento."""
    clients = generate_clients(15, rng)
    contractors = generate_contractors(5, rng)

    orders, items = generate_service_orders_and_items(30, clients, contractors, rng)

    assert len(orders) == 30
    assert len(items) >= 30

    client_ids = {c["client_id"] for c in clients}
    contractor_ids = {k["contractor_id"] for k in contractors}
    order_ids = {o["order_id"] for o in orders}

    assert len(order_ids) == 30

    for o in orders:
        assert o["client_id"] in client_ids
        assert o["contractor_id"] in contractor_ids
        assert len(o["order_status"]) > 0
        if "CONCLUID" in o["order_status"].upper():
            assert len(o["completion_date"]) > 0

    for item in items:
        assert item["order_id"] in order_ids
        assert item["quantity"] >= 1


def test_generate_reviews(rng: random.Random) -> None:
    """Valida avaliações atreladas às ordens."""
    clients = generate_clients(10, rng)
    contractors = generate_contractors(5, rng)
    orders, _ = generate_service_orders_and_items(25, clients, contractors, rng)

    reviews = generate_reviews(orders, rng)
    order_ids = {o["order_id"] for o in orders}

    assert len(reviews) > 0
    review_ids = [r["review_id"] for r in reviews]
    assert len(set(review_ids)) == len(reviews)

    for rev in reviews:
        assert rev["order_id"] in order_ids
        assert 1 <= rev["rating"] <= 5
        assert len(rev["review_comment"]) > 0


def test_validate_referential_integrity_success(rng: random.Random) -> None:
    """Testa validação sem erros de integridade."""
    clients = generate_clients(5, rng)
    contractors = generate_contractors(3, rng)
    orders, items = generate_service_orders_and_items(10, clients, contractors, rng)
    reviews = generate_reviews(orders, rng)

    assert (
        validate_referential_integrity(clients, contractors, orders, items, reviews)
        is True
    )


def test_validate_referential_integrity_fk_error(rng: random.Random) -> None:
    """Testa detecção de erro quando FK aponta para ID inexistente."""
    clients = generate_clients(5, rng)
    contractors = generate_contractors(3, rng)
    orders, items = generate_service_orders_and_items(10, clients, contractors, rng)
    reviews = generate_reviews(orders, rng)

    # Injeta FK inválida em orders
    orders[0]["client_id"] = 9999
    with pytest.raises(ValueError, match="client_id inexistente"):
        validate_referential_integrity(clients, contractors, orders, items, reviews)


def test_validate_referential_integrity_all_fk_and_pk_errors(
    rng: random.Random,
) -> None:
    """Testa detecção de erros em todas as PKs e FKs."""
    clients = generate_clients(5, rng)
    contractors = generate_contractors(3, rng)
    orders, items = generate_service_orders_and_items(10, clients, contractors, rng)
    reviews = generate_reviews(orders, rng)

    # Duplicata contractor_id
    contractors_dup = contractors + [contractors[0].copy()]
    with pytest.raises(ValueError, match="contractor_id contém duplicatas"):
        validate_referential_integrity(clients, contractors_dup, orders, items, reviews)

    # Duplicata order_id
    orders_dup = orders + [orders[0].copy()]
    with pytest.raises(ValueError, match="order_id contém duplicatas"):
        validate_referential_integrity(clients, contractors, orders_dup, items, reviews)

    # Duplicata item_id
    items_dup = items + [items[0].copy()]
    with pytest.raises(ValueError, match="item_id contém duplicatas"):
        validate_referential_integrity(clients, contractors, orders, items_dup, reviews)

    # Duplicata review_id
    reviews_dup = reviews + [reviews[0].copy()]
    with pytest.raises(ValueError, match="review_id contém duplicatas"):
        validate_referential_integrity(clients, contractors, orders, items, reviews_dup)

    # FK contractor inválida
    orders_bad_contractor = [dict(o) for o in orders]
    orders_bad_contractor[0]["contractor_id"] = 9999
    with pytest.raises(ValueError, match="contractor_id inexistente"):
        validate_referential_integrity(
            clients, contractors, orders_bad_contractor, items, reviews
        )

    # FK item inválida
    items_bad = [dict(i) for i in items]
    items_bad[0]["order_id"] = 9999
    with pytest.raises(ValueError, match="order_id inexistente"):
        validate_referential_integrity(clients, contractors, orders, items_bad, reviews)

    # FK review inválida
    reviews_bad = [dict(r) for r in reviews]
    reviews_bad[0]["order_id"] = 9999
    with pytest.raises(ValueError, match="order_id inexistente"):
        validate_referential_integrity(clients, contractors, orders, items, reviews_bad)


def test_save_dataset_to_csv(tmp_path: Path) -> None:
    """Testa persistência física em CSV e caso vazio."""
    out_file = tmp_path / "sub" / "test.csv"
    data = [{"id": 1, "name": "Teste A"}, {"id": 2, "name": "Teste B"}]

    save_dataset_to_csv(out_file, data)
    assert out_file.exists()

    with open(out_file, encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 2
        assert reader[0]["name"] == "Teste A"

    # Salvar lista vazia não deve falhar
    empty_file = tmp_path / "empty.csv"
    save_dataset_to_csv(empty_file, [])
    assert not empty_file.exists()


def test_run_mock_generator_e2e(tmp_path: Path) -> None:
    """Testa orquestrador ponta a ponta com persistência em diretório temporário."""
    counts = run_mock_generator(
        output_dir=tmp_path,
        seed=123,
        num_clients=10,
        num_contractors=4,
        num_orders=15,
    )

    assert counts["clients"] == 10
    assert counts["contractors"] == 4
    assert counts["service_orders"] == 15
    assert counts["service_items"] >= 15
    assert counts["reviews"] >= 1

    expected_files = [
        "clients.csv",
        "contractors.csv",
        "service_orders.csv",
        "service_items.csv",
        "reviews.csv",
    ]
    for filename in expected_files:
        file_path = tmp_path / filename
        assert file_path.exists()
        assert file_path.stat().st_size > 0
