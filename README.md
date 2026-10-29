# 🛠️ HomeFix — Inteligência Operacional & Analytics para Marketplaces de Serviços

> *"Transformando a complexidade dos serviços residenciais e comerciais em dados confiáveis, decisões precisas e experiências memoráveis para prestadores e clientes."*

---

## 🌟 Visão Geral do Projeto

O **HomeFix** é uma plataforma moderna e completa de engenharia de dados, analytics e inteligência artificial para um marketplace de serviços residenciais e comerciais (manutenção hidráulica, elétrica, reformas, climatização, limpeza e marcenaria).

Construído sob a metodologia **Spec-Driven Development** (Desenvolvimento Orientado a Especificações), o projeto resolve problemas reais de inconsistência em dados transacionais (moedas em texto, datas heterogêneas, duplicatas e typos), transformando-os através de uma **Arquitetura Medalhão (Bronze $\rightarrow$ Silver $\rightarrow$ Gold)** sobre o motor colunar de alta performance **DuckDB**, disponibilizando um **Servidor MCP nativo do DuckDB** para agentes de IA e um **Dashboard Executivo Interativo em Streamlit**.

---

## ⚙️ O Que o Projeto Faz

- 📥 **Gera e Simula Dados Sintéticos Realistas:** Produz 5 tabelas relacionais (`clients`, `contractors`, `service_orders`, `service_items`, `reviews`) com integridade referencial estrita e ruídos controlados de produção (símbolos monetários `R$`, múltiplos formatos de data, status não padronizados).
- 🥉 **Ingestão Fiel na Camada Bronze:** Carrega dados brutos diretamente para o DuckDB preservando histórico e adicionando carimbo de auditoria temporal (`_ingested_at`).
- 🥈 **Sanitização e Higienização na Camada Silver:** Converte moedas para `DECIMAL(10,2)`, padroniza datas para `DATE` (`YYYY-MM-DD`), normaliza categorias, status e tipos booleanos, e limpa telefones para formato puramente numérico.
- 🥇 **Modelagem Dimensional e Analítica na Camada Gold:** Estrutura dimensões (`dim_clients`, `dim_contractors`), fatos enriquecidos com lead time e tempos de ciclo (`fct_orders`) e sumário executivo mensal (`kpi_monthly_summary`).
- 📊 **Consultas Analíticas Avançadas:** Repositório SQL versionado com métricas de GMV por especialidade (CTEs), scorecard e rankings de prestadores (Window Functions), eficiência operacional e identificação de risco de evasão (Churn pós-incidente).
- 🤖 **Servidor MCP Nativo do DuckDB (Model Context Protocol):** Expõe ferramentas de exploração (`list_tables`, `describe_table`, `get_schema_context`, `execute_query`) para que assistentes de IA (como Antigravity) consultem e interpretem perguntas de negócio em queries SQL dinâmicas.
- 📈 **Dashboard Interativo em Streamlit:** Interface visual executiva para acompanhamento de faturamento, rankings de prestadores, tempos de ciclo e clientes em risco de churn, com filtros interativos e sem dependência de chat.
- 🧪 **Garantia de Qualidade:** Suíte de 42 testes automatizados com cobertura superior a 93% (`pytest-cov`) e linting estrito com `ruff`.

---

## 🧠 Competências e Conceitos Praticados

- 🏗️ **Arquitetura de Dados Medalhão:** Segregação lógica e física em camadas Bronze (raw), Silver (cleansed) e Gold (analytics).
- 🦆 **Processamento Analítico In-Process com DuckDB:** Consultas colunares ultrarrápidas em SQL analítico, operações vetorizadas e banco local embarcado.
- 📐 **Modelagem Dimensional & SQL Moderno:** Criação de tabelas fato e dimensões, Common Table Expressions (CTEs), Window Functions (`ROW_NUMBER()`, `DENSE_RANK()`, `AVG() OVER ()`) e funções temporais (`DATEDIFF`, `STRFTIME`).
- 🤖 **IA Agêntica com Model Context Protocol (MCP):** Implementação de servidor MCP 2.x com protocolo `stdio` para integração de ferramentas analíticas com LLMs.
- 📋 **Spec-Driven Development (SDD):** Desenvolvimento rigoroso e incremental orientado por 5 especificações técnicas formais em Markdown.
- 🐍 **Engenharia de Software em Python 3.12+:** Tipagem estrita com `typing`, docstrings no padrão Google, gerenciamento ultrarrápido com `uv` e linting com `ruff`.
- 🧪 **Test-Driven Design & Qualidade Contínua:** Cobertura de testes superior a 93% utilizando `pytest`, `pytest-cov`, fixtures em memória (`:memory:`) e testes ponta a ponta.
- 📊 **Visualização de Dados Executiva:** Desenvolvimento de dashboards responsivos em `Streamlit` com KPIs, métricas financeiras e gráficos de tendência.

---

## 🏛️ Arquitetura do Sistema

```mermaid
flowchart TD
    subgraph Sourcing["1. Fonte de Dados (Raw CSVs)"]
        CSV["5 Tabelas Relacionais Sintéticas<br/>(clients, contractors, service_orders, service_items, reviews)"]
    end

    subgraph Medallion["2. Pipeline Medalhão (DuckDB Local: homefix.duckdb)"]
        Bronze["Camada Bronze (Raw Ingestion)<br/>Ingestão fiel com metadados de auditoria"]
        Silver["Camada Silver (Cleansing & Standardization)<br/>Tipagem DECIMAL, DATE ISO, normalização de status"]
        Gold["Camada Gold (Dimensional & Analytics)<br/>Dimensões, fatos de ciclo de vida e sumários mensais"]
        Bronze --> Silver --> Gold
    end

    subgraph SQLRepo["3. Repositório Analítico SQL"]
        Q1["kpi_gmv_by_specialty.sql (CTEs)"]
        Q2["kpi_contractor_scorecard.sql (Window Functions)"]
        Q3["kpi_resolution_rate.sql (Eficiência)"]
        Q4["joins_incidents_churn.sql (Múltiplos JOINs)"]
        Gold --> SQLRepo
    end

    subgraph AI["4. IA & Model Context Protocol (MCP)"]
        MCPServer["DuckDB MCP Server (agents/mcp_server.py)<br/>Tools: execute_query, list_tables, describe_table"]
        Bot["DuckDBAnalystBot (agents/bot.py)<br/>Tradução de perguntas de negócio para SQL"]
        Gold --> MCPServer
        MCPServer <--> Bot
    end

    subgraph Presentation["5. Visualização Executiva"]
        Streamlit["Dashboard Streamlit (dashboard/app.py)<br/>KPIs de GMV, Tendências Mensais, Scorecard e Churn"]
        Gold --> Streamlit
    end

    CSV --> Bronze
```

---

## 📊 Glossário de Entidades e Grãos Relacionais

O modelo é composto por 5 entidades relacionais rigorosamente conectadas:

| Tabela | Grão (O que representa 1 linha) | Chave Primária (PK) | Chaves Estrangeiras (FK) |
| :--- | :--- | :--- | :--- |
| **`clients`** | 1 cliente cadastrado no marketplace | `client_id` (INT) | Nenhuma |
| **`contractors`** | 1 prestador autônomo credenciado | `contractor_id` (INT) | Nenhuma |
| **`service_orders`** | 1 ordem de serviço / chamado aberto | `order_id` (INT) | `client_id`, `contractor_id` |
| **`service_items`** | 1 tarefa ou peça faturada em uma ordem | `item_id` (INT) | `order_id` |
| **`reviews`** | 1 avaliação pós-serviço e reporte de incidentes | `review_id` (INT) | `order_id` |

---

## 📁 Estrutura do Repositório

```text
homefix/
├── specs/                     # As 5 especificações técnicas (Spec-Driven)
│   ├── spec-01-mock-data.md
│   ├── spec-02-medallion-pipeline.md
│   ├── spec-03-gold-analytics.md
│   ├── spec-04-mcp-agents.md
│   └── spec-05-dashboard.md
├── scripts/                   # Módulos operacionais do pipeline DuckDB
│   ├── __init__.py
│   ├── connection.py          # Gerenciador de conexão singleton com DuckDB
│   ├── generate_mock_data.py  # Gerador dos 5 CSVs com erros controlados
│   ├── bronze_ingestion.py    # Carga raw CSV -> DuckDB (Schema Bronze)
│   ├── silver_processing.py   # Cleansing e tipagem -> DuckDB (Schema Silver)
│   ├── gold_processing.py     # Criação de views/tabelas analíticas (Schema Gold)
│   └── run_pipeline.py        # Orquestrador sequencial Bronze -> Silver -> Gold
├── data/
│   ├── raw/                   # [Git] 5 CSVs sintéticos com anomalias controladas
│   ├── queries/               # [Git] Consultas analíticas SQL (CTEs, Window Functions)
│   │   ├── kpi_gmv_by_specialty.sql
│   │   ├── kpi_contractor_scorecard.sql
│   │   ├── kpi_resolution_rate.sql
│   │   └── joins_incidents_churn.sql
│   └── warehouse/             # [GitIgnore] Banco binário local homefix.duckdb
├── agents/                    # Servidor MCP do DuckDB & Agente Analítico
│   ├── __init__.py
│   ├── mcp_server.py          # Servidor MCP nativo do DuckDB (stdio)
│   ├── mcp_config.json        # Manifesto de configuração para clientes MCP
│   ├── tools.py               # Ferramentas DuckDB (execute_query, list_tables, etc.)
│   └── bot.py                 # Agente de tradução de perguntas para SQL
├── dashboard/                 # Interface visual com Streamlit
│   ├── __init__.py
│   └── app.py                 # Painel executivo interativo com KPIs e gráficos
├── tests/                     # Suíte de testes automatizados (> 90% cobertura)
│   ├── __init__.py
│   ├── test_generator.py
│   ├── test_pipeline.py
│   ├── test_sql_queries.py
│   ├── test_mcp_agents.py
│   └── test_dashboard_logic.py
├── pyproject.toml             # Dependências gerenciadas via uv
├── uv.lock                    # Lockfile de dependências exatas
├── pytest.ini                 # Configuração de testes com threshold >= 90%
└── README.md                  # Documentação executiva do projeto
```

---

## 🛠️ Tecnologias Utilizadas

- ⚡ **Gerenciador de Pacotes e Runtime:** [uv](https://github.com/astral-sh/uv) (Python 3.12+)
- 🦆 **Banco de Dados Analítico:** [DuckDB](https://duckdb.org/) (colunar, in-process)
- 🐼 **Manipulação de Dados:** [Pandas](https://pandas.pydata.org/) & [Pydantic](https://docs.pydantic.dev/)
- 🔌 **Protocolo de IA:** [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) SDK 2.x
- 📊 **Interface Visual:** [Streamlit](https://streamlit.io/)
- 🧪 **Testes & Qualidade:** [Pytest](https://pytest.org/), [pytest-cov](https://pytest-cov.readthedocs.io/) e [Ruff](https://astral.sh/ruff)

---

## 🚀 Como Executar o Projeto

### Pré-requisitos
Ter o [uv](https://docs.astral.sh/uv/getting-started/installation/) instalado na máquina.

### 1. Clonar e Instalar Dependências
```bash
git clone https://github.com/gabtei/homefix.git
cd homefix
uv sync
```

### 2. Executar o Pipeline Completo (Bronze $\rightarrow$ Silver $\rightarrow$ Gold)
```bash
uv run python scripts/run_pipeline.py
```

### 3. Executar a Suíte de Testes Automatizados (Cobertura > 90%)
```bash
uv run pytest
```

### 4. Iniciar o Dashboard Interativo Streamlit
```bash
uv run streamlit run dashboard/app.py
```

### 5. Iniciar o Servidor DuckDB MCP
```bash
uv run python agents/mcp_server.py
```

---

## 📋 Fases Desenvolvidas

1. **Fase 1: Motor de Dados Sintéticos & Spec-01** — Geração de 5 tabelas relacionais com dados sintéticos realistas e inconsistências controladas.
2. **Fase 2: Arquitetura Medalhão (Bronze & Silver) & Spec-02** — Ingestão no DuckDB e higienização robusta (moedas decimais, datas ISO e normalização categórica).
3. **Fase 3: Camada Gold & Consultas Analíticas & Spec-03** — Modelagem dimensional, CTEs, Window Functions e KPIs de negócio (GMV, CSAT, Resolução, Churn).
4. **Fase 4: Servidor DuckDB MCP & IA Agêntica & Spec-04** — Servidor MCP do DuckDB com catálogo de ferramentas e tradução de perguntas em linguagem natural para SQL.
5. **Fase 5: Dashboard Streamlit & Documentação Final & Spec-05** — Painel visual em Streamlit, orquestrador unificado e cobertura de testes acima de 93%.

---

## 👨‍💻 Autor

**Gabriel Teixeira**  
*Desafio Engenheiro de Dados Júnior*  
- GitHub: [@gabtei](https://github.com/gabtei)
