## Example Queries

##### To see all available tables, on the LEFT HAND PANEL click:
###### > Databases > Objects > ARCDW_PROD > DATE_EXCHANGE_LAYER > Tables

##### To run a query:
1. Highlight the query
2. Press CTRL+ENTER
3.  Run the following:
```sql
USE ROLE planit_sandbox_role;              -- Permissions to access
USE WAREHOUSE planit_sandbox_warehouse;    -- Warehouse-Compute to run queries
```
-----

### Scores & Indicators

##### All indicators and their sectors in Transition Arc
```sql
SELECT
    i.indicator_name,
    i.dataset_display_name,
    i.sector_name,
    i.sector_classification_name
FROM arcdw_prod.data_exchange_layer.indicator i
WHERE i.sector_classification_name = 'Climate Arc';
```

##### Latest scores for a company
```sql
SELECT
    cs.company_name,
    cs.company_score,
    cs.grade_code,
    d.display_name AS score_year,
    cs.scoring_rule_name
FROM arcdw_prod.data_exchange_layer.company_score cs
JOIN arcdw_prod.data_exchange_layer.date d
    ON cs.company_score_date_id = d.date_id
WHERE cs.company_name ILIKE '%Air France%'
  AND cs.default_score = TRUE
  AND cs.scoring_rule_name = 'moderate';
```

-----

### Emissions

##### Historical emissions data for a company
```sql
WITH latest_hist AS (
    SELECT
        company_id,
        emission_id,
        MAX(emission_hist_id) AS emission_hist_id
    FROM arcdw_prod.data_exchange_layer.emission_hist
    GROUP BY company_id, emission_id)

SELECT
    c.company_name,
    ehv.sector_name,
    c.lei,
    ehv.dataset_name,
    e.emission_scope,
    e.intensity,
    e.gas_name,
    e.gas_symbol,
    ehv.emission_date_display_name,
    ehv.emission_value,
    e.description
FROM arcdw_prod.data_exchange_layer.company c
LEFT JOIN latest_hist lh
    ON c.company_id = lh.company_id
LEFT JOIN arcdw_prod.data_exchange_layer.emission_hist eh
    ON eh.emission_hist_id = lh.emission_hist_id
LEFT JOIN arcdw_prod.data_exchange_layer.emission_hist_value ehv
    ON ehv.emission_hist_id = eh.emission_hist_id
LEFT JOIN arcdw_prod.data_exchange_layer.emission e
    ON e.emission_id = eh.emission_id
WHERE c.company_name ILIKE '%BP P.L.C%';

```

##### Company emissions targets
```sql
SELECT
    c.company_name,
    et.target_type,
    et.target_coverage,
    e.emission_scope,
    e.intensity,
    e.description,
    etv.emission_value,
    etv.target_date,
    et.dataset_name
FROM arcdw_prod.data_exchange_layer.company c
INNER JOIN arcdw_prod.data_exchange_layer.emission_target et
    ON c.company_id = et.company_id
LEFT JOIN arcdw_prod.data_exchange_layer.emission_target_value etv
    ON et.emission_target_id = etv.emission_target_id
LEFT JOIN arcdw_prod.data_exchange_layer.emission e
    ON e.emission_id = et.emission_id
WHERE c.company_name ILIKE '%AIRBUS%';
```

##### Compare actual emissions to benchmark values
```sql
WITH latest_benchmarks AS (
    SELECT
        sector_id,
        scenario_name,
        MAX(emission_benchmark_name) AS emission_benchmark_name
    FROM arcdw_prod.data_exchange_layer.emission_benchmark_value
    GROUP BY sector_id, scenario_name),

latest_historys AS (
    SELECT
        company_id,
        sector_id,
        dataset_id,
        emission_id,
        MAX(emission_hist_id) AS emission_hist_id
    FROM arcdw_prod.data_exchange_layer.emission_hist
    GROUP BY company_id, sector_id, dataset_id, emission_id)

SELECT
    ehv.company_name,
    ehv.sector_name,
    e.emission_scope,
    e.description AS emission_description,
    ehv.dataset_name,
    ebv.emission_benchmark_name AS benchmark_name,
    ebv.scenario_name,
    ehv.emission_date_display_name AS year,
    ehv.emission_value AS company_emissions,
    ebv.benchmark_value
FROM arcdw_prod.data_exchange_layer.emission_hist_value ehv
INNER JOIN latest_historys eh
    ON ehv.emission_hist_id = eh.emission_hist_id
INNER JOIN arcdw_prod.data_exchange_layer.emission e
    ON eh.emission_id = e.emission_id
INNER JOIN arcdw_prod.data_exchange_layer.company c
    ON eh.company_id = c.company_id
INNER JOIN arcdw_prod.data_exchange_layer.emission_benchmark eb
    ON eb.emission_id = e.emission_id
   AND eb.sector_id = eh.sector_id
   AND eb.dataset_id = eh.dataset_id
INNER JOIN arcdw_prod.data_exchange_layer.emission_benchmark_value ebv
    ON eb.emission_benchmark_id = ebv.emission_benchmark_id
   AND ehv.emission_date_display_name = ebv.benchmark_date_display_name
INNER JOIN latest_benchmarks AS lb
    ON lb.sector_id = eh.sector_id
    AND lb.scenario_name = ebv.scenario_name
    AND lb.emission_benchmark_name = ebv.emission_benchmark_name
WHERE ehv.company_name ILIKE '%BP P.L.C%'
  AND ebv.scenario_name = 'Below 2 Degrees';
```
##### Latest WBA ACT Core Emissions
```sql
SELECT
    company.company_name
    , company.lei
    , company.hq_country_name
    , company.hq_region_name
    , emissions.sector_name
    , emissions.sector_classification_name
    , emissions.emission_date_display_name
    , emissions.emission_value
    , e_meta.emission_scope
    , e_meta.emission_category
    , e_meta.gas_symbol
    , e_meta.unit_name
FROM data_exchange_layer.emission_hist_value AS emissions
INNER JOIN data_exchange_layer.company USING(company_id)
INNER JOIN data_exchange_layer.emission_hist USING(emission_hist_id)
INNER JOIN data_exchange_layer.emission AS e_meta USING(emission_id)
WHERE dataset_display_name = 'WBA ACT Core'
  AND emissions.emission_date_display_name = (
      SELECT MAX(e2.emission_date_display_name)
      FROM data_exchange_layer.emission_hist_value AS e2
      INNER JOIN data_exchange_layer.emission_hist AS eh2 USING(emission_hist_id)
      WHERE eh2.dataset_display_name = 'WBA ACT Core'
        AND e2.company_id = emissions.company_id
  )
ORDER BY company_name, emission_scope, emission_date_display_name```
---

### Governance 

##### Governance Questions & Answers

```sql 
SELECT 
    gcv.company_name
    , gcv.sector_name
    , gc.governance_criteria_category
    , gc.governance_criteria_name
    , gc.question
    , gcv.criteria_value
    , gcv.dataset_name
    , gcv.publication_date_display_name  
    , gcv.assessment_date_display_name
FROM arcdw_prod.data_exchange_layer.governance_criteria_value AS gcv
LEFT JOIN arcdw_prod.data_exchange_layer.governance_criteria AS gc 
    ON (gcv.governance_criteria_id = gc.governance_criteria_id)
WHERE company_name = 'Bayerische Motoren Werke Aktiengesellschaft'
ORDER BY company_name, question
;
```
---

##### Financial

##### Financial Benchmarks from CK
```sql 
SELECT 
    financial_category_name 
    , financial_benchmark_name
    , ratio
    , sector_name
    , benchmark_value
    , scenario_name
    , reference_name
    , reference_link
    , publication_date_display_name
FROM arcdw_prod.data_exchange_layer.financial_benchmark_value
INNER JOIN arcdw_prod.data_exchange_layer.financial_benchmark USING (financial_benchmark_id) -- USING keyword allows you to join between tables with the same attribute name for the given key.
INNER JOIN arcdw_prod.data_exchange_layer.financial USING (financial_id);
```


##### Financial values
```sql
SELECT 
    company_name
    , financial_category_name
    , financial_taxonomy_element_tier_1
    , financial_taxonomy_element_tier_2
    , taxonomy_name
    , dataset_name
    , sector_name
    , sector_classification_name
    , financial_hist_value
    , financial_date_display_name
    , financial_date_granularity
    , financial_date_assumed
    , financial_date_to_display_name
    , financial_date_to_granularity
    , financial_date_from_display_name
    , financial_date_from_granularity
    , notes
    , reference_name
    , reference_link
    , currency_code
    , ratio
FROM arcdw_prod.data_exchange_layer.financial_hist_value
ORDER BY company_name, financial_category_name, sector_name
;```

##### Financial values
```sql SELECT 
    company_name
    , financial_category_name
    , financial_taxonomy_element_tier_1
    , financial_taxonomy_element_tier_2
    , taxonomy_name
    , dataset_name
    , sector_name
    , sector_classification_name
    , financial_hist_value
    , financial_date_display_name
    , financial_date_granularity
    , financial_date_assumed
    , financial_date_to_display_name
    , financial_date_to_granularity
    , financial_date_from_display_name
    , financial_date_from_granularity
    , notes
    , reference_name
    , reference_link
    , currency_code
    , ratio
FROM arcdw_prod.data_exchange_layer.financial_hist_value
ORDER BY company_name, financial_category_name, sector_name
;```


