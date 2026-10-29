"""Módulo gerador de dados sintéticos para o ecossistema HomeFix.

Gera 5 tabelas relacionais em formato CSV com ruídos e inconsistências
controladas (datas mistas, moedas como texto, variações de caixa e acentuação),
mantendo 100% de integridade referencial entre as chaves primárias e estrangeiras.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Constantes de configuração e reprodutibilidade
SEED_DEFAULT = 42
TOTAL_CLIENTS = 100
TOTAL_CONTRACTORS = 30
TOTAL_ORDERS = 500

CIDADES_SP = [
    "São Paulo",
    "Campinas",
    "Santos",
    "Sorocaba",
    "Ribeirão Preto",
    "São Bernardo do Campo",
    "Santo André",
    "Osasco",
    "São José dos Campos",
]

ESPECIALIDADES_BASE = [
    "Elétrica",
    "Hidráulica",
    "Pintura",
    "Climatização",
    "Marcenaria",
    "Alvenaria",
    "Limpeza",
]

ESPECIALIDADES_VARIACOES = {
    "Elétrica": ["Elétrica", "Eletrica", "ELETRICA", "eletrica"],
    "Hidráulica": ["Hidráulica", "Hidraulica", "HIDRAULICA", "hidraulica"],
    "Pintura": ["Pintura", "pintura", "PINTURA"],
    "Climatização": ["Climatização", "Climatizacao", "CLIMATIZACAO", "climatizacao"],
    "Marcenaria": ["Marcenaria", "marcenaria", "MARCENARIA"],
    "Alvenaria": ["Alvenaria", "alvenaria", "ALVENARIA"],
    "Limpeza": ["Limpeza", "limpeza", "LIMPEZA"],
}

STATUS_VARIACOES = {
    "CONCLUIDO": ["CONCLUIDO", "Concluído", "concluido", "Concluido"],
    "CANCELADO": ["CANCELADO", "Cancelado", "cancelado"],
    "EM_ANDAMENTO": ["EM_ANDAMENTO", "Em Andamento", "em_andamento"],
    "ABERTO": ["ABERTO", "Aberto", "aberto"],
}

BOOLEANOS_POSITIVOS = ["TRUE", "true", "Sim", "1"]
BOOLEANOS_NEGATIVOS = ["FALSE", "false", "Não", "0"]

NOMES_PRIMEIROS = [
    "Lucas",
    "Ana",
    "Carlos",
    "Mariana",
    "Bruno",
    "Camila",
    "Rodrigo",
    "Juliana",
    "Felipe",
    "Beatriz",
    "Gabriel",
    "Larissa",
    "Thiago",
    "Fernanda",
    "Rafael",
    "Aline",
    "Mateus",
    "Priscila",
    "Leonardo",
    "Renata",
    "Diego",
    "Patricia",
    "Marcelo",
    "Carolina",
    "Eduardo",
    "Vanessa",
    "Alexandre",
    "Tatiane",
    "Gustavo",
    "Daniela",
    "Vinicius",
    "Carla",
    "Andre",
    "Renan",
    "Sabrina",
    "Fabio",
    "Jessica",
]

SOBRENOMES = [
    "Silva",
    "Santos",
    "Oliveira",
    "Souza",
    "Rodrigues",
    "Ferreira",
    "Alves",
    "Pereira",
    "Lima",
    "Gomes",
    "Costa",
    "Ribeiro",
    "Martins",
    "Carvalho",
    "Almeida",
    "Lopes",
    "Soares",
    "Fernandes",
    "Vieira",
    "Barbosa",
    "Rocha",
    "Dias",
    "Nascimento",
    "Andrade",
    "Moreira",
    "Nunes",
    "Marques",
    "Machado",
]

ITENS_POR_ESPECIALIDADE = {
    "Elétrica": [
        ("Troca de disjuntor bipolar", "PARTS", 65.0),
        ("Instalação de tomada 20A", "PARTS", 25.0),
        ("Troca de fiação do chuveiro", "LABOR", 150.0),
        ("Instalação de luminária plafon", "LABOR", 90.0),
        ("Manutenção em quadro de distribuição", "LABOR", 280.0),
    ],
    "Hidráulica": [
        ("Substituição de reparo de descarga", "PARTS", 45.0),
        ("Troca de sifão sanfonado", "PARTS", 30.0),
        ("Instalação de torneira monocomando", "LABOR", 120.0),
        ("Desentupimento de ralo ou pia", "LABOR", 180.0),
        ("Reparo de vazamento em tubulação", "LABOR", 250.0),
    ],
    "Pintura": [
        ("Lata de tinta acrílica fosca 18L", "PARTS", 320.0),
        ("Massa corrida e lixa", "PARTS", 75.0),
        ("Pintura de teto e paredes", "LABOR", 350.0),
        ("Aplicação de verniz em esquadrias", "LABOR", 190.0),
    ],
    "Climatização": [
        ("Carga de gás refrigerante R410A", "PARTS", 180.0),
        ("Suporte metálico condensadora", "PARTS", 85.0),
        ("Higienização completa de ar condicionado", "LABOR", 220.0),
        ("Instalação de split 12000 BTUs", "LABOR", 450.0),
    ],
    "Marcenaria": [
        ("Kit de corrediças telescópicas", "PARTS", 60.0),
        ("Dobradiças com amortecedor", "PARTS", 40.0),
        ("Ajuste de portas e gavetas de armário", "LABOR", 160.0),
        ("Instalação de prateleiras suspensas", "LABOR", 130.0),
    ],
    "Alvenaria": [
        ("Saco de cimento e argamassa", "PARTS", 55.0),
        ("Revestimento cerâmico metro quadrado", "PARTS", 70.0),
        ("Assentamento de piso cerâmico", "LABOR", 300.0),
        ("Pequeno reparo em alvenaria e reboco", "LABOR", 240.0),
    ],
    "Limpeza": [
        ("Kit de produtos químicos profissionais", "PARTS", 95.0),
        ("Limpeza pós-obra pesada", "LABOR", 380.0),
        ("Higienização de estofados e carpetes", "LABOR", 260.0),
        ("Limpeza de vidros e janelas em altura", "LABOR", 200.0),
    ],
}


def format_currency_with_noise(value: float, rng: random.Random) -> str:
    """Aplica ruídos intencionais na formatação de valores monetários.

    Args:
        value: Valor float numérico.
        rng: Instância de gerador aleatório para reprodutibilidade.

    Returns:
        String contendo o valor em diferentes formatos realistas.
    """
    fmt_choice = rng.choice(
        ["brl_symbol_comma", "brl_dot", "brl_comma", "plain_dot", "symbol_no_space"]
    )
    int_part = int(value)
    dec_part = round((value - int_part) * 100)

    if fmt_choice == "brl_symbol_comma":
        # Ex: R$ 1.250,50 ou R$ 150,00
        formatted_num = f"{int_part:,}".replace(",", ".") + f",{dec_part:02d}"
        return f"R$ {formatted_num}"
    if fmt_choice == "brl_dot":
        # Ex: R$ 150.00
        return f"R$ {value:.2f}"
    if fmt_choice == "brl_comma":
        # Ex: 150,50
        formatted_num = f"{int_part:,}".replace(",", ".") + f",{dec_part:02d}"
        return formatted_num
    if fmt_choice == "symbol_no_space":
        # Ex: R$150
        return f"R${int_part}"
    # plain_dot: 150.00
    return f"{value:.2f}"


def format_date_with_noise(dt: datetime, rng: random.Random) -> str:
    """Aplica padrões heterogêneos de formatação para datas.

    Args:
        dt: Objeto datetime a ser formatado.
        rng: Instância de gerador aleatório.

    Returns:
        String representando a data em formato misto.
    """
    pattern = rng.choice(["ISO", "BR", "US_DASH", "ISO_SLASH"])
    if pattern == "ISO":
        return dt.strftime("%Y-%m-%d")
    if pattern == "BR":
        return dt.strftime("%d/%m/%Y")
    if pattern == "US_DASH":
        return dt.strftime("%m-%d-%Y")
    return dt.strftime("%Y/%m/%d")


def format_phone_with_noise(ddd: str, number: str, rng: random.Random) -> str:
    """Gera telefone com ou sem máscara de formatação.

    Args:
        ddd: Código DDD (ex: '11').
        number: 9 dígitos do telefone celular.
        rng: Gerador aleatório.

    Returns:
        String de telefone mascarada ou dígitos brutos.
    """
    if rng.choice([True, False]):
        return f"({ddd}) {number[:5]}-{number[5:]}"
    return f"{ddd}{number}"


def generate_clients(total: int, rng: random.Random) -> list[dict[str, Any]]:
    """Gera lista de registros sintéticos de clientes.

    Args:
        total: Quantidade de clientes a gerar.
        rng: Instância do gerador aleatório.

    Returns:
        Lista de dicionários representando cada cliente.
    """
    clients: list[dict[str, Any]] = []
    base_date = datetime(2023, 1, 1)

    for client_id in range(1, total + 1):
        primeiro_nome = rng.choice(NOMES_PRIMEIROS)
        sobrenome = rng.choice(SOBRENOMES)
        full_name = f"{primeiro_nome} {sobrenome}"
        email = f"{primeiro_nome.lower()}.{sobrenome.lower()}{client_id}@exemplo.com.br"
        ddd = rng.choice(["11", "12", "13", "14", "15", "16", "19"])
        phone_raw = f"9{rng.randint(10000000, 99999999)}"
        phone = format_phone_with_noise(ddd, phone_raw, rng)
        city = rng.choice(CIDADES_SP)
        signup_dt = base_date + timedelta(days=rng.randint(0, 450))

        clients.append(
            {
                "client_id": client_id,
                "client_name": full_name,
                "client_email": email,
                "client_phone": phone,
                "client_city": city,
                "client_state": "SP",
                "signup_date": format_date_with_noise(signup_dt, rng),
            }
        )

    return clients


def generate_contractors(total: int, rng: random.Random) -> list[dict[str, Any]]:
    """Gera lista de prestadores credenciados com variações de categorias.

    Args:
        total: Quantidade de prestadores.
        rng: Gerador aleatório.

    Returns:
        Lista de dicionários representando prestadores.
    """
    contractors: list[dict[str, Any]] = []

    for contractor_id in range(1, total + 1):
        nome = f"{rng.choice(NOMES_PRIMEIROS)} {rng.choice(SOBRENOMES)}"
        esp_base = rng.choice(ESPECIALIDADES_BASE)
        esp_com_ruido = rng.choice(ESPECIALIDADES_VARIACOES[esp_base])
        hourly_rate_raw = round(rng.uniform(60.0, 180.0), 2)
        hourly_rate_str = format_currency_with_noise(hourly_rate_raw, rng)
        exp_years = rng.randint(2, 25)
        city = rng.choice(CIDADES_SP)
        is_active_val = rng.choice(
            BOOLEANOS_POSITIVOS if rng.random() > 0.1 else BOOLEANOS_NEGATIVOS
        )

        contractors.append(
            {
                "contractor_id": contractor_id,
                "contractor_name": nome,
                "specialty": esp_com_ruido,
                "hourly_rate": hourly_rate_str,
                "experience_years": exp_years,
                "city": city,
                "state": "SP",
                "is_active": is_active_val,
            }
        )

    return contractors


def generate_service_orders_and_items(
    total_orders: int,
    clients: list[dict[str, Any]],
    contractors: list[dict[str, Any]],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Gera ordens de serviço e seus respectivos itens respeitando integridade referencial.

    Args:
        total_orders: Total de chamados/ordens a gerar.
        clients: Lista de clientes existentes (para FK client_id).
        contractors: Lista de prestadores existentes (para FK contractor_id).
        rng: Gerador aleatório.

    Returns:
        Tupla contendo (lista de ordens, lista de itens de serviço).
    """
    orders: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    client_ids = [c["client_id"] for c in clients]
    contractor_ids = [k["contractor_id"] for k in contractors]
    contractor_spec_map = {k["contractor_id"]: k["specialty"] for k in contractors}

    item_id_counter = 1
    base_date = datetime(2023, 6, 1)

    for order_id in range(1, total_orders + 1):
        client_id = rng.choice(client_ids)
        contractor_id = rng.choice(contractor_ids)
        spec_prestador = contractor_spec_map[contractor_id]

        # Encontra a especialidade base para pegar itens correspondentes
        spec_base = "Elétrica"
        for base_key, variants in ESPECIALIDADES_VARIACOES.items():
            if spec_prestador in variants:
                spec_base = base_key
                break

        # Datas da ordem
        order_days = rng.randint(0, 360)
        dt_order = base_date + timedelta(days=order_days)
        dt_scheduled = dt_order + timedelta(days=rng.randint(1, 5))

        # Status com probabilidade realista
        status_key = rng.choices(
            ["CONCLUIDO", "CANCELADO", "EM_ANDAMENTO", "ABERTO"],
            weights=[0.70, 0.12, 0.10, 0.08],
            k=1,
        )[0]
        status_str = rng.choice(STATUS_VARIACOES[status_key])

        # Se concluído, tem data de conclusão
        if status_key == "CONCLUIDO":
            dt_completion = dt_scheduled + timedelta(days=rng.randint(0, 2))
            completion_str = format_date_with_noise(dt_completion, rng)
            cancellation_reason = ""
        elif status_key == "CANCELADO":
            completion_str = ""
            cancellation_reason = rng.choice(
                [
                    "Cliente desistiu",
                    "Prestador indisponível",
                    "Preço elevado",
                    "Problema de agenda",
                    "Serviço resolvido previamente",
                ]
            )
        else:
            completion_str = ""
            cancellation_reason = ""

        # Geração dos itens desta ordem
        catalogo_itens = ITENS_POR_ESPECIALIDADE.get(
            spec_base, ITENS_POR_ESPECIALIDADE["Elétrica"]
        )
        qtd_itens = rng.randint(1, 4)
        itens_selecionados = rng.sample(
            catalogo_itens, k=min(qtd_itens, len(catalogo_itens))
        )

        total_itens_calculado = 0.0
        for desc, tp_item, preco_base in itens_selecionados:
            qtd = rng.randint(1, 3) if tp_item == "PARTS" else 1
            unit_price = round(preco_base * rng.uniform(0.9, 1.15), 2)
            tot_price = round(qtd * unit_price, 2)
            total_itens_calculado += tot_price

            # Variações no tipo do item
            tipo_variado = tp_item
            if tp_item == "LABOR":
                tipo_variado = rng.choice(
                    ["LABOR", "Mão de Obra", "Mao de Obra", "Serviço"]
                )
            elif tp_item == "PARTS":
                tipo_variado = rng.choice(["PARTS", "Peça", "Peca", "Material"])

            items.append(
                {
                    "item_id": item_id_counter,
                    "order_id": order_id,
                    "item_description": desc,
                    "item_type": tipo_variado,
                    "quantity": qtd,
                    "unit_price": format_currency_with_noise(unit_price, rng),
                    "total_price": format_currency_with_noise(tot_price, rng),
                }
            )
            item_id_counter += 1

        total_quoted_raw = round(total_itens_calculado * rng.uniform(0.95, 1.05), 2)
        total_quoted_str = format_currency_with_noise(total_quoted_raw, rng)

        if status_key == "CONCLUIDO":
            total_final_raw = round(total_itens_calculado, 2)
            total_final_str = format_currency_with_noise(total_final_raw, rng)
        elif status_key == "CANCELADO":
            total_final_str = "0.00"
        else:
            total_final_str = ""

        orders.append(
            {
                "order_id": order_id,
                "client_id": client_id,
                "contractor_id": contractor_id,
                "order_date": format_date_with_noise(dt_order, rng),
                "scheduled_date": format_date_with_noise(dt_scheduled, rng),
                "completion_date": completion_str,
                "order_status": status_str,
                "service_category": spec_prestador,
                "total_quoted_amount": total_quoted_str,
                "total_final_amount": total_final_str,
                "cancellation_reason": cancellation_reason,
            }
        )

    return orders, items


def generate_reviews(
    orders: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Gera avaliações para ordens concluídas ou com tentativa/cancelamento.

    Args:
        orders: Lista de ordens de serviço para atrelar a avaliação.
        rng: Gerador aleatório.

    Returns:
        Lista de avaliações geradas.
    """
    reviews: list[dict[str, Any]] = []
    review_id_counter = 1

    elogios = [
        "Excelente atendimento, serviço rápido e muito profissional!",
        "Muito atencioso, explicou todo o conserto.",
        "Trabalho impecável e pontual.",
        "Recomendo fortemente, qualidade excelente.",
        "Serviço bem feito e preço justo.",
    ]
    neutros = [
        "Serviço padrão, atendeu a expectativa.",
        "Ficou bom, porém atrasou 20 minutos no início.",
        "Razoável, resolveu o problema inicial.",
    ]
    reclamacoes = [
        "Demorou mais de 2 horas além do combinado para chegar.",
        "Deixou resíduo de poeira no piso e o parafuso folgado.",
        "Cobrou valor adicional sem combinar previamente.",
        "Serviço precisou de novo ajuste 3 dias depois.",
        "Tivemos um pequeno vazamento após o término do serviço.",
    ]

    for order in orders:
        status = order["order_status"].upper()
        # Apenas concluidos e alguns cancelados recebem avaliação
        if "CONCLUID" in status:
            if rng.random() > 0.85:
                continue  # Nem todos os clientes avaliam
        elif "CANCEL" in status:
            if rng.random() > 0.25:
                continue  # Poucas avaliações em cancelamentos
        else:
            continue

        is_incident = rng.random() < 0.15  # 15% de incidentes operacionais

        if is_incident:
            rating = rng.choice([1, 2])
            comment = rng.choice(reclamacoes)
            incident_flag = rng.choice(BOOLEANOS_POSITIVOS)
            incident_type = rng.choice(
                [
                    "Atraso excessivo",
                    "Dano material",
                    "Serviço incompleto",
                    "Cobrança indevida",
                ]
            )
        else:
            rating = rng.choices([3, 4, 5], weights=[0.15, 0.35, 0.50], k=1)[0]
            comment = rng.choice(elogios) if rating >= 4 else rng.choice(neutros)
            incident_flag = rng.choice(BOOLEANOS_NEGATIVOS)
            incident_type = "Nenhum"

        # Data de review pouco após a ordem
        dt_rev = datetime(2023, 7, 1) + timedelta(days=rng.randint(10, 360))

        reviews.append(
            {
                "review_id": review_id_counter,
                "order_id": order["order_id"],
                "rating": rating,
                "review_comment": comment,
                "incident_reported": incident_flag,
                "incident_type": incident_type,
                "review_date": format_date_with_noise(dt_rev, rng),
            }
        )
        review_id_counter += 1

    return reviews


def save_dataset_to_csv(filepath: Path, records: list[dict[str, Any]]) -> None:
    """Salva uma lista de registros em arquivo CSV com codificação UTF-8.

    Args:
        filepath: Caminho do arquivo a ser salvo.
        records: Lista de dicionários representando as linhas.
    """
    if not records:
        return

    filepath.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0].keys())

    with open(filepath, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def validate_referential_integrity(
    clients: list[dict[str, Any]],
    contractors: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    items: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
) -> bool:
    """Valida que todas as chaves estrangeiras existem em suas respectivas tabelas pai.

    Args:
        clients: Lista de clientes.
        contractors: Lista de prestadores.
        orders: Lista de ordens de serviço.
        items: Lista de itens de serviço.
        reviews: Lista de avaliações.

    Returns:
        True se todas as FKs forem válidas e as PKs forem únicas.

    Raises:
        ValueError: Caso seja detectada violação de integridade.
    """
    client_ids = {c["client_id"] for c in clients}
    contractor_ids = {k["contractor_id"] for k in contractors}
    order_ids = {o["order_id"] for o in orders}

    # Unicidade das PKs
    if len(client_ids) != len(clients):
        raise ValueError("client_id contém duplicatas!")
    if len(contractor_ids) != len(contractors):
        raise ValueError("contractor_id contém duplicatas!")
    if len(order_ids) != len(orders):
        raise ValueError("order_id contém duplicatas!")
    if len({i["item_id"] for i in items}) != len(items):
        raise ValueError("item_id contém duplicatas!")
    if len({r["review_id"] for r in reviews}) != len(reviews):
        raise ValueError("review_id contém duplicatas!")

    # FKs de orders
    for o in orders:
        if o["client_id"] not in client_ids:
            raise ValueError(
                f"Ordem {o['order_id']} possui client_id inexistente: {o['client_id']}"
            )
        if o["contractor_id"] not in contractor_ids:
            raise ValueError(
                f"Ordem {o['order_id']} possui contractor_id inexistente: {o['contractor_id']}"
            )

    # FKs de items
    for item in items:
        if item["order_id"] not in order_ids:
            raise ValueError(
                f"Item {item['item_id']} possui order_id inexistente: {item['order_id']}"
            )

    # FKs de reviews
    for rev in reviews:
        if rev["order_id"] not in order_ids:
            raise ValueError(
                f"Review {rev['review_id']} possui order_id inexistente: {rev['order_id']}"
            )

    return True


def run_mock_generator(
    output_dir: Path | str = "data/raw",
    seed: int = SEED_DEFAULT,
    num_clients: int = TOTAL_CLIENTS,
    num_contractors: int = TOTAL_CONTRACTORS,
    num_orders: int = TOTAL_ORDERS,
) -> dict[str, int]:
    """Orquestra a geração dos 5 datasets sintéticos e salva os arquivos CSV.

    Args:
        output_dir: Diretório onde os arquivos CSV serão salvos.
        seed: Semente pseudo-aleatória.
        num_clients: Total de clientes.
        num_contractors: Total de prestadores.
        num_orders: Total de ordens de serviço.

    Returns:
        Dicionário com a contagem de registros gerados por entidade.
    """
    rng = random.Random(seed)
    target_path = Path(output_dir)

    # 1. Geração das entidades mestres
    clients = generate_clients(num_clients, rng)
    contractors = generate_contractors(num_contractors, rng)

    # 2. Geração das entidades transacionais
    orders, items = generate_service_orders_and_items(
        num_orders, clients, contractors, rng
    )

    # 3. Geração das avaliações
    reviews = generate_reviews(orders, rng)

    # 4. Verificação de integridade referencial estrita
    validate_referential_integrity(clients, contractors, orders, items, reviews)

    # 5. Persistência dos 5 CSVs
    save_dataset_to_csv(target_path / "clients.csv", clients)
    save_dataset_to_csv(target_path / "contractors.csv", contractors)
    save_dataset_to_csv(target_path / "service_orders.csv", orders)
    save_dataset_to_csv(target_path / "service_items.csv", items)
    save_dataset_to_csv(target_path / "reviews.csv", reviews)

    return {
        "clients": len(clients),
        "contractors": len(contractors),
        "service_orders": len(orders),
        "service_items": len(items),
        "reviews": len(reviews),
    }


if __name__ == "__main__":
    counts = run_mock_generator()
    print("[OK] Geracao de dados sinteticos concluida com sucesso:")
    for entity, count in counts.items():
        print(f"  - {entity}.csv: {count} registros")
