# Especificação Técnica 01: Motor de Geração de Dados Sintéticos (Mock Data Engine)

## 1. Visão Geral e Contexto de Negócio

O objetivo desta especificação é definir a estrutura, os esquemas, as regras de integridade e os tipos de anomalias controladas para a geração dos **5 conjuntos de dados sintéticos** em formato CSV que alimentam a plataforma analítica **HomeFix** (Marketplace de Serviços Residenciais & Comerciais).

Para espelhar a realidade de um ambiente de dados de produção transacional antes da etapa de engenharia e sanitização, os dados brutos gerados conterão ruídos intencionais (datas em formatos múltiplos, valores monetários como string com símbolo `R$` e separadores regionais, variações tipográficas e de caixa em categorias e status). Contudo, **as chaves relacionais (PKs e FKs) serão estritamente preservadas e consistentes**, assegurando integridade referencial de 100%.

---

## 2. Dicionário de Entidades, Grãos e Chaves

| Tabela | Grão (O que representa 1 linha) | Chave Primária (PK) | Chaves Estrangeiras (FK) | Volume Alvo |
| :--- | :--- | :--- | :--- | :--- |
| **`clients`** | 1 cliente cadastrado no marketplace | `client_id` (INT) | Nenhuma | 100 registros |
| **`contractors`** | 1 prestador autônomo credenciado | `contractor_id` (INT) | Nenhuma | 30 registros |
| **`service_orders`** | 1 ordem de serviço / chamado aberto | `order_id` (INT) | `client_id`, `contractor_id` | 500 registros |
| **`service_items`** | 1 tarefa ou peça faturada em uma ordem | `item_id` (INT) | `order_id` | ~1.200 registros |
| **`reviews`** | 1 avaliação pós-serviço e reporte de incidentes | `review_id` (INT) | `order_id` | ~400 registros |

---

## 3. Esquemas Detalhados das 5 Tabelas

### 3.1 Tabela `clients` (`data/raw/clients.csv`)

| Campo | Tipo Bruto | Descrição | Regras e Inconsistências Controladas |
| :--- | :--- | :--- | :--- |
| `client_id` | `INT` | Identificador único do cliente | Sequencial `1..N`, sem nulos, chave primária estrita. |
| `client_name` | `VARCHAR` | Nome completo do cliente | Nomes brasileiros realistas. |
| `client_email` | `VARCHAR` | E-mail de contato | Formato de e-mail válido. |
| `client_phone` | `VARCHAR` | Telefone de contato | Formatos mistos: mascarado `(11) 98765-4321` ou bruto `11987654321`. |
| `client_city` | `VARCHAR` | Cidade de residência | Ex.: São Paulo, Campinas, Santos, Sorocaba, Ribeirão Preto. |
| `client_state` | `VARCHAR` | Unidade federativa | Constante `SP`. |
| `signup_date` | `VARCHAR` | Data de cadastro | Formatos mistos: `YYYY-MM-DD`, `DD/MM/YYYY`, `MM-DD-YYYY`, `YYYY/MM/DD`. |

### 3.2 Tabela `contractors` (`data/raw/contractors.csv`)

| Campo | Tipo Bruto | Descrição | Regras e Inconsistências Controladas |
| :--- | :--- | :--- | :--- |
| `contractor_id` | `INT` | Identificador único do prestador | Sequencial `1..M`, sem nulos, chave primária estrita. |
| `contractor_name` | `VARCHAR` | Nome completo do profissional | Nomes realistas. |
| `specialty` | `VARCHAR` | Especialidade principal | Variações tipográficas e de acento: `Elétrica`, `Eletrica`, `ELETRICA`, `Hidráulica`, `Hidraulica`, `Pintura`, `Climatização`, `Climatizacao`, `Marcenaria`, `Alvenaria`, `Limpeza`. |
| `hourly_rate` | `VARCHAR` | Valor da hora técnica | Moedas em string: `R$ 80,00`, `80.00`, `R$ 120,50`, `120,50`, `R$80`. |
| `experience_years` | `INT` | Anos de experiência | Inteiro entre 1 e 25. |
| `city` | `VARCHAR` | Cidade base de atendimento | Cidades do estado de SP. |
| `state` | `VARCHAR` | Estado | Constante `SP`. |
| `is_active` | `VARCHAR` | Indicador de status cadastral | Representações mistas de booleano: `TRUE`, `true`, `Sim`, `1`, `FALSE`, `0`, `Não`. |

### 3.3 Tabela `service_orders` (`data/raw/service_orders.csv`)

| Campo | Tipo Bruto | Descrição | Regras e Inconsistências Controladas |
| :--- | :--- | :--- | :--- |
| `order_id` | `INT` | Identificador único da OS | Sequencial `1..K`, sem nulos, chave primária estrita. |
| `client_id` | `INT` | FK do cliente solicitante | Valor existente em `clients.client_id`. |
| `contractor_id` | `INT` | FK do prestador alocado | Valor existente em `contractors.contractor_id`. |
| `order_date` | `VARCHAR` | Data de abertura do chamado | Formatos mistos de datas (`YYYY-MM-DD`, `DD/MM/YYYY`, `YYYY/MM/DD`). |
| `scheduled_date` | `VARCHAR` | Data agendada para execução | Data igual ou posterior a `order_date`. |
| `completion_date` | `VARCHAR` | Data de conclusão efetiva | Preenchida para concluídas; vazia para ordens abertas/canceladas. |
| `order_status` | `VARCHAR` | Status atual da ordem | Inconsistências de caixa e acento: `CONCLUIDO`, `Concluído`, `concluido`, `CANCELADO`, `Cancelado`, `EM_ANDAMENTO`, `Em Andamento`, `ABERTO`, `aberto`. |
| `service_category` | `VARCHAR` | Categoria do serviço | Categoria do chamado, correlacionada à especialidade do prestador. |
| `total_quoted_amount` | `VARCHAR` | Valor orçado inicialmente | Formatos de moeda: `R$ 250,00`, `250.00`, `R$ 1.200,00`, etc. |
| `total_final_amount` | `VARCHAR` | Valor final faturado | Moeda formatada para concluídas; vazio ou `0.00` para canceladas. |
| `cancellation_reason` | `VARCHAR` | Motivo de cancelamento | Preenchido quando status for cancelado ("Cliente desistiu", "Prestador indisponível", "Preço elevado"). |

### 3.4 Tabela `service_items` (`data/raw/service_items.csv`)

| Campo | Tipo Bruto | Descrição | Regras e Inconsistências Controladas |
| :--- | :--- | :--- | :--- |
| `item_id` | `INT` | Identificador único do item | Sequencial `1..L`, chave primária estrita. |
| `order_id` | `INT` | FK da ordem de serviço | Valor existente em `service_orders.order_id`. |
| `item_description` | `VARCHAR` | Descrição do item/peça | Descrição textual da tarefa ou material aplicado. |
| `item_type` | `VARCHAR` | Natureza do item | Variações textuais: `LABOR`, `Mão de Obra`, `Mao de Obra`, `PARTS`, `Peça`, `Peca`, `Material`. |
| `quantity` | `INT` | Quantidade | Inteiro positivo (1 a 10). |
| `unit_price` | `VARCHAR` | Valor unitário do item | Formatos de moeda em string (`R$ 45,00`, `45.00`, etc.). |
| `total_price` | `VARCHAR` | Valor total (`quantity * unit_price`) | Formatos de moeda em string correspondentes ao cálculo. |

### 3.5 Tabela `reviews` (`data/raw/reviews.csv`)

| Campo | Tipo Bruto | Descrição | Regras e Inconsistências Controladas |
| :--- | :--- | :--- | :--- |
| `review_id` | `INT` | Identificador único da avaliação | Sequencial `1..R`, chave primária estrita. |
| `order_id` | `INT` | FK da ordem de serviço | Valor existente em `service_orders.order_id` (1 avaliação por ordem). |
| `rating` | `INT` | Nota de satisfação (CSAT) | Inteiro de 1 a 5 estrelas. |
| `review_comment` | `VARCHAR` | Comentário do cliente | Texto descritivo com elogios, críticas ou relatos neutros. |
| `incident_reported` | `VARCHAR` | Houve incidente operacional? | Formatos mistos: `TRUE`, `FALSE`, `Sim`, `Não`, `1`, `0`. |
| `incident_type` | `VARCHAR` | Classificação do incidente | `Atraso excessivo`, `Dano material`, `Serviço incompleto`, `Cobrança indevida`, ou `Nenhum`. |
| `review_date` | `VARCHAR` | Data de publicação da avaliação | Formatos mistos de datas (`YYYY-MM-DD`, `DD/MM/YYYY`, etc.). |

---

## 4. Tipos e Padrões de Inconsistências Intencionais

1. **Campos Monetários:**
   - Exemplo 1: `R$ 150,00`
   - Exemplo 2: `150.00`
   - Exemplo 3: `R$ 1.450,50`
   - Exemplo 4: `120,50`
   - Exemplo 5: `R$85`

2. **Campos Temporais (Datas):**
   - Padrão ISO: `2024-03-15`
   - Padrão Brasileiro: `15/03/2024`
   - Padrão Americano: `03-15-2024`
   - Padrão com barras invertidas ou ano inicial: `2024/03/15`

3. **Valores Booleanos:**
   - Positivos: `TRUE`, `true`, `Sim`, `1`
   - Negativos: `FALSE`, `false`, `Não`, `0`

4. **Categorias e Status Textuais:**
   - Minúsculas, maiúsculas, com ou sem acentos (`eletrica`, `Elétrica`, `ELETRICA`, `concluido`, `CONCLUIDO`, `Concluído`).

---

## 5. Requisitos de Implementação do Módulo Gerador

1. **Reprodutibilidade:** Fixar `random.seed(42)` para garantir geração determinística.
2. **Modularidade:** Funções dedicadas para geração de cada entidade com docstrings padrão Google e tipagem estrita (`typing`).
3. **Persistência:** Exportação direta para arquivos `.csv` com codificação `UTF-8` no diretório `data/raw/`.
4. **Validação:** Verificação automática da integridade referencial ao término da geração antes da gravação em disco.
