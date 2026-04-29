\# 📂 Raw Data



This directory contains the original, unmodified datasets used as inputs for the bike demand prediction system.



\---



\## 📌 Description



The raw data represents the \*\*initial ingestion layer\*\* of the pipeline and is preserved in its original format to ensure reproducibility and traceability.



No transformations, cleaning, or feature engineering steps are applied at this stage.



\---



\## 📄 Files



\### 1. `seoul\_bike\_sharing.csv`

\- Core dataset containing historical bike rental data

\- Includes:

&#x20; - Date and time information

&#x20; - Weather conditions (temperature, humidity, wind speed)

&#x20; - Holiday and seasonal indicators

&#x20; - Bike rental counts



\---



\### 2. `selected\_cities.csv`

\- List of cities used for API-based forecasting

\- Supports real-time prediction workflows

\- Used in conjunction with OpenWeather API



\---



\## ⚙️ Usage



This data is used in:



\- \*\*Data Collection / Ingestion\*\*

\- \*\*Exploratory Data Analysis (EDA)\*\*

\- \*\*Initial feature extraction\*\*



\---



\## ⚠️ Notes



\- Files in this folder should remain \*\*unchanged\*\*

\- Any preprocessing must be done in the `data/processed/` directory

\- Acts as the \*\*single source of truth\*\* for the pipeline



