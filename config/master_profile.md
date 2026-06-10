<!--
  Master CV / profile source. Curate bullets here; used as the canonical narrative
  for tailoring and applications.
-->
Itish Singh
Data Scientist | MLOps| AWS | AI/ML
Leeds · 07920 842809 · itishsingh96@gmail.com
linkedin.com/in/itish-singh-09853733 · https://github.com/itsitish

## Career summary

- Full-stack data scientist with 6+ years building and deploying ML systems end-to-end in Python, PySpark, and SQL on AWS. Shipped RNN forecasters, signal decomposition pipelines, and serverless inference architectures serving 60,000+ households Skilled in the entire lifecyle from feature engineering and distributed data processing to SageMaker training, deployment, and production monitoring.


## Education

- MSc, Data Science and Analytics, University of Leeds, Sep 2021 - Sep 2022
Focus: Statistical Modelling, Deep Learning, NLP, Time-series forecasting

- B.Tech, Computer Science, Galgotias University, May 2015 - May 2019
Focus: Python, SQL, MongoDB, Data Structures


## Skills

- Agentic AI & LLMs: GPT Agents, RAG, Vector Databases, Prompt Engineering, CursorAI, Claude API, OpenClaw, HuggingFace, OpenAI API, pgvector, langchain
- Data Science & ML: Gradient Boosting, Regression, Forecasting, Clustering, Deep Learning (RNNs, CNNs), Hypothesis Testing, A/B Testing
- Programming & Tools: Python (PyTorch, pandas, scikit-learn, FastAPI), SQL, Git, Jira, Scrum/Kanban, Unit Testing, CI/CD
- Distributed Processing: PySpark, AWS Glue, Lambdas
- Data Platforms: PostgreSQL, DynamoDB, Athena, RDS, Aurora, S3 Data Lake, Parquet
- Cloud Infrastructure: AWS, Terraform, Docker, Quicksight (Model Monitoring, BI Dashboards), Serverless Architecture
- Collaboration: Cross-functional Team Leadership, Scrum Master, Stakeholder Management, Roadmap Definition

## Experience

### Data Scientist, Chameleon Technology, Dec 2022 - Present, Harrogate, England

Full-stack data scientist owning the complete lifecycle — data pipelines, feature engineering, model research, productionisation, API/microservice deployment, and monitoring — across a smart energy platform serving 60,000+ households.
- Built a PyTorch LSTM forecasting system for UK energy demand — pretrained across thousands of households then fine-tuned per home type, achieving a 20% MAPE reduction; deployed on SageMaker with drift-monitored retraining via distributed computing
- Fine tuned clustering algorithms by performing A/B testing and improving user feedback scores by 15%
- Developed and evaluated gradient boosting ensemble models for user clustering, improving marketing campaign engagement metrics by 10%
- Researched mould-risk conditions from humidity and temperature sensor data; hypothesised and validated statistical alert thresholds; deployed a SageMaker-based compliance solution under Awaab's Law for external customers
- Developed an LLM-powered recommendation framework using RAG and vector embeddings to surface personalised user-facing energy insights, leveraging OpenAI API, pgvector, langchain. Currently migrating to a self hosted LLama model for generaive layer
- Built an offline LLM evaluation pipeline for the RAG recommender, scoring faithfulness, answer relevance, and retrieval precision on a curated eval set using LLM-as-judge, tracked per prompt and model version to gate the OpenAI to self-hosted LLama migration
- Built NLP pipelines to analyse unstructured enterprise data from Confluence documentation, PDFs, and distributed README files, generating structured insights and comprehensive analysis for product cataloguing
- Architected PySpark pipelines on AWS Glue to produce analytics-ready datasets for multiple ML applications; built aggregation jobs feeding TimescaleDB hypertables for downstream training and inference
- Distributed a Python-packaged linear regression model across large-scale half-hourly smart meter streams using PySpark on AWS Glue, processing ~350M+ interval records for scheduled batch inference at scale
- Integrated and configured Model Context Protocol (MCP) workflows between Notion and CursorAI, enabling AI-assisted concurrent documentation updates, delivery tracking, and cross-tool context synchronization
- Designed a real-time mould-risk detection system using high-performance SQL materialised views and validated thresholds to flag at-risk properties
- Wrote complex SQL queries to aggregate, validate, and transform smart meter data across multiple source systems, underpinning model training and compliance workflows
- Achieved a 99% reduction in infrastructure costs and 8x improvement in inference latency by re-architecting a monolithic NILM server into a three-stage serverless pipeline (extraction to inference to persistence), each stage an independent AWS Lambda with parallel, independently scalable execution
- Owned end-to-end delivery of the Home Energy Management System — optimisation models, scheduling APIs, and automated heat pump & EV charge controls — reducing user energy costs by 15%
- Designed a reinforcement learning scheduling agent using SAC to optimise EV and heat pump controls against dynamic energy tariffs, framing the problem as an MDP with cost minimisation reward and comfort constraints, reducing user energy costs by 15%
- Deployed Dockerised models to AWS via Terraform (IaC), enabling reproducible releases and simplified auto-scaling
- Built and deployed event-driven microservices integrating SQS, Kinesis, DynamoDB, Lambda, and API Gateway
- Modernised ML delivery with CI/CD pipelines and automated code quality standards, reducing production regressions
- Designed an agentic testing harness using GPT agents to automate integration testing workflows and surface results to Slack; packaged as reusable Cursor skills for team-wide adoption
- Published BI dashboards in QuickSight for model monitoring and stakeholder visibility
- Acted as Scrum Master and technical mentor; defined team roadmap and upskilled members in AWS, MLOps, and scalable Python; led technical hiring from competency definition through interviews
- Contributed modular React components and Jest unit tests to the internal web application

### Founding Engineer, TripSync, Jul 2021 - Dec 2021, Agra, India

Founding engineer for a consumer IoT startup bringing budget smart-lighting automation to the Indian market, covering data modelling, pipeline design, and mobile application delivery.
- Researched and implemented signal-based music visualisation models using audio volume and frequency bands as real-time features
- Built event-driven data pipelines capturing app interaction and IoT device telemetry to enable experimentation and product iteration
- Designed and developed a cross-platform mobile application in React Native for BLE/IoT device control and automation
- Designed and maintained CI/CD pipelines using GitHub Actions to automate testing, version control workflows, and deployment processes across environments

### Data Analyst, Wipro Technologies, Jul 2019 - Jul 2021, Hyderabad, India

Data analyst embedded in the British Petroleum account, delivering across energy management, trading, and EV charging applications — spanning data analytics, ETL pipeline development and dashboarding
- Analysed energy consumption and EV charging data to surface usage patterns, peak demand windows, and load-shifting opportunities
- Wrote complex SQL queries to aggregate and validate meter and charging data across multiple source systems, supporting downstream modelling and reporting
- Built Python data pipelines aggregating smart meter and charging data from hybrid cloud sources into S3, improving reliability for downstream modelling workflows
- Migrated manual Excel-based analysis to reproducible Python notebooks, improving scalability and auditability
- Contributed to hybrid mobile and web applications built in Angular and Ionic
- Deployed serveral internal tooling features in Python as cloud functions in Azure 
- Delivered analytical findings to stakeholders via Tableau dashboards


## Projects

- Weather Nowcasting (ConvLSTM): Developed a deep learning architecture to capture spatial and temporal features in MET Office weather dataset and predict the future conditions of a region. Calculated F-scores and various other accuracy metrics for further optimisation

- Image Caption Generation (NLP): Engineered and optimized a deep learning model to create captions for an input image. Optimised for accuracy by using several key performance indicators

- Agentic Market Research Pipeline: Used OpenClaw and HuggingFace to orchestrate multi-agent workflows, scraping and summarising stock market blog posts into structured insights — demonstrating hands-on agentic AI capability applied to unstructured financial content.

- Self-hosted Job-Search Platform (FastAPI): Built a Python/FastAPI app with SQLite and worker-backed background tasks, wrapping a human-in-the-loop Cursor + GPT layer for prompt and document work focused on tracking and consistency.

- 


## Achievements

- AWS Certified Cloud Practitioner
- Member of the Energy Systems Catapult - ADViCE Data Science Sharing circle
