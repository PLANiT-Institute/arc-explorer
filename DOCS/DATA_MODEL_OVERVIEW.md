## Summary

Through your Sandbox, you have access to the Arc DATA_EXCHANGE_LAYER schema.
This schema is based on a normalised database but has been enriched with additional columns, making it easier to query by reducing the number of joins needed.

## Data Scoring Flow
High-level description of how raw data is transformed into company scores.



## Data Processing Flow

```mermaid
flowchart LR

    %% --- Core Layer ---
    subgraph Core["Core"]
        Emissions[Emissions Tables]
        Financial[Financial Tables]
        Governance[Governance Tables]

        CoreNote["Raw data from data providers, data usually has units."]
    end

    %% --- Indicators Layer ---
    subgraph IndicatorsLayer["Indicators"]
        Indicators[Indicators]

        IndicatorsNote["Indicators can be transformed raw data or sourced directly from raw data, usually no units."]
    end

    %% --- Arc Metrics Layer ---
    subgraph ArcMetrics["Arc Metrics"]
        Submetrics[Submetrics]
        Metrics[Metrics]

        MetricsNote["Submetrics are aggregated into final Arc metrics."]
    end

    %% --- Flow ---
    Emissions --> Indicators
    Financial --> Indicators
    Governance --> Indicators

    Indicators --> Submetrics
    Submetrics --> Metrics

```

## Data Model