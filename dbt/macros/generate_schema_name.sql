{#- Par défaut dbt préfixe le schéma personnalisé par celui du profil (staging_marts, etc.).
    Ici le schéma configuré (+schema) est utilisé tel quel : staging, marts. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
