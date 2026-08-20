## Table Descriptions

## Tables

### Core Reference Tables
(Shared definitions, lookup tables, and metadata)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| COMPANY | Identifying information about the company including Company ID, LEI, Name, HQ | Sobeys Inc, Italy | Definition | Yes |
| COMPANY_SCORE | Company's overall score and metadata (grade, score date, sector) | Noble Energy, 0 | Values | Yes |
| COMPANY_SECTOR | Company sector data | GS Holdings, Oil and Gas | Values | Yes |
| CURRENCY | Currency data including name and symbol | USD | Definition | No |
| DATE | Date information (e.g. quarter_number, month_number) | 36161 | Definition | No |
| DEX_COUNTRY | Dex country definitions and metadata | Panama, PA, PAN | Definition | No |
| DEX_COUNTRY_REGION | Dex country and corresponding region definitions | Panama, Central America | Definition | No |
| REGION | Regions assigned to companies in Arc's data | Polynesia | Definition | No |

---

### Dataset & Provider Metadata
(Where data comes from and how it is packaged)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| DATASET | Package of data provided by a data provider | Lobby Map | Definition | No |
| DATA_PROVIDER | Organisation that delivers datasets | Influence Map | Definition | No |
| DATA_PROVIDER_DATASET | Relationship between datasets and data providers | Lobby Map, Influence Map | Definition | No |

---

### Flags, Grades & Methodologies
(Scoring context, labels, and rules)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| FLAG | Possible flags used by Arc | Analysis missing metrics | Definition | No |
| FLAG_VALUE | Display text for flags | Missing metric categories | Values | No |
| GRADE | Grades available in Arc scoring | D | Definition | No |
| METHODOLOGY | Methodologies used for assessments | FAIRR Protein Producer Index Methodology | Definition | No |
| SCORING_RULE | Rules applied during scoring | Moderate, default | Definition | No |

---

### Sectors, Scenarios & Context
(Classifications and analytical context)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| SECTOR | Underlying sectors in Arc data (Climate Arc used for scoring) | Tobacco, CK SEI | Definition | No |
| SCENARIO | Scenarios used for assessing company metrics | NZE2050, TPI | Definition | No |
| CONTEXT_XREF | Contextual cross-reference metadata | – | Definition | No |
| XREF | Generic cross-reference table | – | Definition | No |

---

### Emissions Data
(Emissions definitions, benchmarks, history, and targets)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| EMISSION | Emission datapoint types and providers | Scope 2 Market-Based Emissions | Definition | No |
| EMISSION_BENCHMARK | Emission benchmarks and scenarios | Aluminium_01/02/2020, Below 2 Degrees | Definition | No |
| EMISSION_BENCHMARK_VALUE | Target benchmark values | Autos_01/02/2023 – 250 | Values | No |
| EMISSION_HIST | Historic emissions metadata | Air France, disclosure date | Values | Yes |
| EMISSION_HIST_VALUE | Historic emission values | Air France, 2023, 975 | Values | Yes |
| EMISSION_TARGET | Emission targets set by companies | Air France, Scope 3, WBA | Values | Yes |
| EMISSION_TARGET_VALUE | Numeric emission target values | Air France, 2035, 20000 | Values | Yes |

---

### Financial Data
(Financial classifications, benchmarks, and history)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| FINANCIAL | Financial datapoint types and taxonomy | Sustainable Capital Expenditure | Definition | No |
| FINANCIAL_CATEGORY | Categories of financial indicators | Total Revenue | Definition | No |
| FINANCIAL_TAXONOMY | Financial taxonomies used by Arc | Corporate Knights Taxonomy | Definition | No |
| FINANCIAL_TAXONOMY_ELEMENT | Financial taxonomy hierarchy elements | Buildings, Building materials | Definition | No |
| FINANCIAL_BENCHMARK | Financial benchmarks used in Arc | Corporate Knights Benchmark | Definition | No |
| FINANCIAL_BENCHMARK_VALUE | Financial benchmark values | NZE2050, Revenue Ratio, 0.1 | Values | No |
| FINANCIAL_HIST | Historic financial datapoints | Air France, Total Acquisition | Values | Yes |
| FINANCIAL_HIST_VALUE | Financial indicator values | Air France, Total Acquisition, 7 | Values | Yes |

---

### Governance
(Governance criteria)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| GOVERNANCE_CRITERIA | Governance assessment criteria | Reports Scope 3 emissions? | Definition | No |
| GOVERNANCE_CRITERIA_VALUE | Company responses to governance criteria | Air France, Yes | Values | Yes |

---

### Metrics, Submetrics & Indicators
(How companies are scored)

| Table Name | Description / Primary Datapoint | Example of Primary Datapoint | Table Type | Company-Level |
|-----------|----------------------------------|------------------------------|------------|---------------|
| INDICATOR | Indicators used in Transition Arc | Trend in Scope 1 & 2 emissions | Definition | No |
| INDICATOR_SCORE | Indicator scores per company | Air France, ratio 0.03 | Values | Yes |
| METRIC | Metrics used in Transition Arc | Shipping emissions scored by WBA | Definition | No |
| METRIC_CATEGORY | Metric categories | Emissions | Definition | No |
| METRIC_SCORE | Metric scores per company | Air France, Emissions, 0.7 | Values | Yes |
| SUBMETRIC | Submetrics feeding into metrics | Trend in Scope 1 & 2 emissions | Definition | Yes |
| SUBMETRIC_SCORE | Submetric scores per company | Air France, Governance, 0.7 | Values | Yes |