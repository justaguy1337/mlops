# Project 2 — Air Quality Index Analysis and Prediction

**Course:** Data Engineering and MLOps  
**Mode:** Individual Project  
**Total Marks:** 100  

> **Assignment Part 1 Submission Deadline:** On or before **7 September 2026** (First Week of September)

---

## 1. Understanding the Project

Develop a pipeline that collects air-pollution and weather data, prepares an analytical warehouse, and produces dashboards for pollution trends. In Part 2, the system should predict AQI values or AQI categories for a selected city or monitoring station.

### Project Objectives

- Ingest pollution and weather data from free public sources.
- Create a time-series ETL pipeline with quality checks.
- Store station-wise and city-wise air-quality data.
- Build an MLOps pipeline for AQI forecasting or classification.

---

## 2. Data Source Information

| Data Source | Information Available | Suggested Use |
|---|---|---|
| **OpenAQ API** | Open air-quality measurements for pollutants and monitoring locations. | Primary API source |
| **CPCB historical data** | India-specific AQI and pollutant observations where downloadable data is available. | Optional national source |
| **Open-Meteo API** | Free weather variables such as temperature, humidity, rainfall, and wind. | Weather enrichment |
| **Kaggle AQI datasets** | Historical CSV datasets for rapid prototyping. | Fallback dataset |

### Dataset Rule

Use only free, legally accessible, public, institutional, or instructor-approved datasets.

Include the **source name and access instructions** in the report.

---

## 3. Data Ingestion Tool Information

Use:

- **Python `requests`** for REST API extraction.
- **Pandas** for CSV processing.
- **Apache Airflow** for scheduled daily or hourly ingestion.

API responses should be stored first in a **raw landing area** before transformation.

### Minimum Ingestion Expectations

- Maintain a raw copy of the extracted data.
- Record:
  - Extraction date
  - Source
  - File/API status
  - Row count
- Handle extraction errors and log failed records.
- Support at least one repeatable or scheduled ingestion workflow.
- Do not manually edit the final analytical dataset.

---

## 4. Suggested Data Architecture Design

The suggested pipeline architecture is:

```text
OpenAQ / CPCB / Open-Meteo
          ↓
Python API Collectors
          ↓
Raw JSON / CSV Landing Zone
          ↓
Airflow ETL
          ↓
Cleaned PostgreSQL Time-Series Tables
          ↓
Analytics Layer
          ↓
Tableau Public / Streamlit
```

Students should prepare their own architecture diagram showing:

1. Source layer
2. Ingestion layer
3. Raw/staging layer
4. Transformation layer
5. Storage layer
6. Analytics layer
7. Later MLOps layer

---

## 5. ETL and Data Engineering Requirements

The ETL pipeline must:

- Normalize timestamps, station names, and pollutant units.
- Remove duplicate observations.
- Validate pollutant ranges and identify missing periods.
- Join pollution and weather data by station and timestamp.
- Calculate hourly/daily pollutant averages and AQI categories.
- Create gold-layer tables for:
  - City
  - Station
  - Pollutant
  - Date analysis

---

## 6. Suggested Data Visualization

Use **Tableau Public** for business-oriented dashboards and comparative analysis, or **Streamlit** when interactive filtering, user input, or future model prediction is central to the application.

### Suggested Dashboard Views / Indicators

- AQI trend by date and station
- Pollutant contribution analysis
- City or station comparison
- Hourly and monthly AQI patterns
- Weather impact on AQI

---

# Assignment Part 1 — Data Pipeline Implementation

## 7. Assignment Part 1

**Deadline:** On or before **7 September 2026**, which falls in the first week of September.

Students must build a complete data pipeline **without adding the final machine-learning deployment at this stage**.

### Required Implementation

- Acquire and document the selected dataset(s).
- Create automated or reproducible ingestion scripts.
- Implement an **Apache Airflow DAG**, or an approved equivalent ETL workflow.
- Create:
  - Raw layer
  - Staging layer
  - Cleaned layer
  - Analytical layer
- Apply data-quality checks and produce a rejected-record or error log.
- Load the transformed data into **PostgreSQL** or another approved open-source database.
- Create at least one analytical table or data mart.
- Develop a **Tableau Public or Streamlit dashboard** with at least five meaningful views or indicators.
- Prepare an architecture diagram and data dictionary.
- Demonstrate one successful end-to-end pipeline execution.

### Part 1 Submission Package

| # | Required Submission |
|---:|---|
| 1 | Source code and ETL scripts |
| 2 | Airflow DAG or approved orchestration workflow |
| 3 | Database schema and sample populated tables |
| 4 | Dataset source information and access instructions |
| 5 | Architecture diagram and pipeline flow |
| 6 | Data dictionary and validation rules |
| 7 | Tableau Public link/file or Streamlit application |
| 8 | Project report of approximately 8–10 pages |
| 9 | Screenshots or execution evidence |
| 10 | README with setup and run instructions |

---

# Assignment Part 2 — MLOps Pipeline Extension

## 8. Assignment Part 2

After completing Part 1, students will extend the same project into an **end-to-end MLOps solution**.

> **Part 2 deadline:** Will be announced separately.

### Requirements

- Predict next-day AQI **or** classify the AQI category.
- Compare regression and classification models.
- Track:
  - RMSE / MAE for regression
  - Precision / Recall / F1 for classification
  - Using MLflow
- Create a reusable feature pipeline for lag and rolling features.
- Deploy the best model with **FastAPI and Docker**.
- Monitor:
  - Missing data
  - Feature drift
  - Forecasting error

### Common Part 2 Requirements

- Create reproducible feature-engineering and model-training pipelines.
- Use a chronological or problem-appropriate train/validation/test split.
- Track experiments, parameters, metrics, and artifacts using **MLflow**.
- Register and version the selected model.
- Serve predictions through **FastAPI** or an approved API framework.
- Containerize the inference service using **Docker**.
- Integrate model output into the Streamlit or Tableau-supported workflow where appropriate.
- Monitor:
  - Input-data quality
  - Drift
  - Model performance
  - Latency
  - Failures
- Define retraining criteria and document the model lifecycle.

---

## 9. Suggested Mark Distribution

| Component | Part 1 | Part 2 |
|---|---:|---:|
| Problem understanding and design | 5 | 5 |
| Data source and ingestion | 10 | 5 |
| ETL, validation, and storage | 20 | 5 |
| Visualization and interpretation | 10 | 5 |
| Documentation and demonstration | 5 | 5 |
| Model development and evaluation | — | 10 |
| MLflow, registry, deployment, and Docker | — | 10 |
| Monitoring and retraining design | — | 5 |
| **Total** | **50** | **50** |

---

## 10. General Instructions

- The project must be completed individually.
- All source code must be written, organized, and explained by the student.
- Public code may be consulted, but copied work without attribution will not be accepted.
- Use environment variables for database credentials and API keys.
- Do not upload private, personally identifiable, or confidential data.
- The final demonstration must show the pipeline from **data ingestion to dashboard output**.
- Late submissions will be handled according to course policy.

---

# Project Implementation Checklist

## Part 1 — Data Engineering

### Data Sources
- [ ] Select a free/public dataset or API.
- [ ] Document the source.
- [ ] Document access instructions.
- [ ] Ensure the dataset follows the assignment's dataset rule.

### Ingestion
- [ ] Build Python API/CSV ingestion scripts.
- [ ] Use `requests` for REST APIs.
- [ ] Use Pandas for CSV processing.
- [ ] Save raw API/CSV data before transformation.
- [ ] Record extraction date.
- [ ] Record source.
- [ ] Record file/API status.
- [ ] Record row count.
- [ ] Implement extraction error handling.
- [ ] Create failed-record/error logs.
- [ ] Make ingestion repeatable/schedulable.

### ETL
- [ ] Normalize timestamps.
- [ ] Normalize station names.
- [ ] Normalize pollutant units.
- [ ] Remove duplicate observations.
- [ ] Validate pollutant ranges.
- [ ] Identify missing periods.
- [ ] Join pollution and weather data by station and timestamp.
- [ ] Calculate hourly pollutant averages.
- [ ] Calculate daily pollutant averages.
- [ ] Calculate AQI categories.
- [ ] Create gold-layer analytical tables.

### Storage
- [ ] Create raw layer.
- [ ] Create staging layer.
- [ ] Create cleaned layer.
- [ ] Create analytical layer.
- [ ] Load transformed data into PostgreSQL or an approved open-source database.
- [ ] Prepare database schema.
- [ ] Populate sample tables.
- [ ] Create at least one analytical table/data mart.

### Orchestration
- [ ] Create an Apache Airflow DAG or approved equivalent.
- [ ] Demonstrate a successful end-to-end execution.

### Visualization
- [ ] Build Tableau Public or Streamlit dashboard.
- [ ] Include at least five meaningful views/indicators:
  - [ ] AQI trend
  - [ ] Pollutant contribution
  - [ ] City/station comparison
  - [ ] Hourly/monthly AQI pattern
  - [ ] Weather impact on AQI

### Documentation
- [ ] Architecture diagram.
- [ ] Pipeline flow.
- [ ] Data dictionary.
- [ ] Validation rules.
- [ ] Dataset source information.
- [ ] Setup/run instructions.
- [ ] Execution screenshots/evidence.
- [ ] 8–10 page project report.
- [ ] README.

---

## Part 2 — MLOps

### Modeling
- [ ] Choose AQI forecasting or AQI classification.
- [ ] Build reproducible feature engineering.
- [ ] Add lag features.
- [ ] Add rolling features.
- [ ] Use chronological/problem-appropriate train/validation/test split.
- [ ] Compare regression and classification models as applicable.
- [ ] Evaluate using required metrics.

### Experiment Tracking
- [ ] Set up MLflow.
- [ ] Track experiments.
- [ ] Track parameters.
- [ ] Track metrics.
- [ ] Track artifacts.
- [ ] Register the selected model.
- [ ] Version the model.

### Deployment
- [ ] Build FastAPI inference service.
- [ ] Containerize with Docker.
- [ ] Serve model predictions through the API.
- [ ] Integrate model output with Streamlit or the supported Tableau workflow.

### Monitoring
- [ ] Monitor input-data quality.
- [ ] Monitor missing data.
- [ ] Monitor feature drift.
- [ ] Monitor model performance.
- [ ] Monitor forecasting error.
- [ ] Monitor API latency.
- [ ] Monitor failures.
- [ ] Define retraining criteria.
- [ ] Document the model lifecycle.

---

# Expected High-Level Architecture

```text
                         ┌─────────────────────┐
                         │   Public Data APIs  │
                         │ OpenAQ / CPCB /     │
                         │ Open-Meteo          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Python Collectors   │
                         │ requests / Pandas   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Raw Landing Zone    │
                         │ JSON / CSV          │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Apache Airflow      │
                         │ ETL / Quality Checks│
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ PostgreSQL          │
                         │ Staging / Cleaned   │
                         │ / Analytical        │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Dashboard           │
                         │ Tableau / Streamlit │
                         └─────────────────────┘

                Part 2 — MLOps Extension
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Feature Pipeline    │
                         │ Lag / Rolling       │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Model Training      │
                         │ + MLflow            │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Model Registry      │
                         │ + Versioning        │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ FastAPI + Docker    │
                         │ Prediction Service  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Dashboard / Client  │
                         └─────────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Monitoring          │
                         │ Quality / Drift /   │
                         │ Performance / Error │
                         └─────────────────────┘
```

## Important Constraints

- Complete **Part 1 first** before adding final ML deployment.
- Keep raw copies of extracted data.
- Do not manually edit the final analytical dataset.
- Use environment variables for database credentials and API keys.
- Do not include private, personally identifiable, or confidential data.
- The final demonstration should cover the flow from **data ingestion → ETL → storage → dashboard**.
- Public code can be consulted, but copied work without attribution is not accepted.
