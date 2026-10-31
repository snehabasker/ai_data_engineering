{# Parse the three date formats seen in the raw extract; unparseable -> NULL (caught by validation, never guessed). #}
{% macro parse_date(col) -%}
cast(coalesce(
    try_strptime(trim({{ col }}), '%Y-%m-%d %H:%M:%S'),
    try_strptime(trim({{ col }}), '%d/%m/%Y'),
    try_strptime(trim({{ col }}), '%b %d, %Y')
) as date)
{%- endmacro %}

{# "$1,234.56" -> 1234.56 ; '' / garbage -> NULL #}
{% macro parse_money(col) -%}
try_cast(nullif(regexp_replace(trim({{ col }}), '[$,]', '', 'g'), '') as decimal(12, 2))
{%- endmacro %}

{# DuckDB has no initcap(): "united kingdom" -> "United Kingdom" #}
{% macro title_case(col) -%}
array_to_string(list_transform(string_split(lower(trim({{ col }})), ' '), lambda w: upper(w[1]) || w[2:]), ' ')
{%- endmacro %}

{# Generic test: every row must satisfy the boolean expression. #}
{% test expression_is_true(model, expression, column_name=none) %}
select * from {{ model }} where not ({{ expression }})
{% endtest %}
