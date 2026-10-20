FROM python:3.14-slim

# dbt-core est figé explicitement : sans cela pip résout vers une préversion (1.13.0b1)
RUN pip install --no-cache-dir "dbt-core==1.12.6" "dbt-postgres==1.11.0"

WORKDIR /usr/app
# Le conteneur tourne avec l'uid de l'hôte (cf. docker-compose) : HOME doit être inscriptible
ENV DBT_PROFILES_DIR=/usr/app \
    HOME=/tmp \
    DO_NOT_TRACK=1

ENTRYPOINT ["dbt"]
