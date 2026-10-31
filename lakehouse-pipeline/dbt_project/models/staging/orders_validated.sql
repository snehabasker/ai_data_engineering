{{ config(materialized='table') }}

-- Deduplicate (latest delivery wins), clean, then flag rule violations. Nothing is dropped silently:
-- stg_orders and quarantine_orders are the two halves of this table (see test_order_accounting).
with ranked as (
    select *, row_number() over (partition by order_id order by loaded_at desc) as rn
    from {{ source('raw', 'orders') }}
),

cleaned as (
    select
        cast(order_id as integer)                         as order_id,
        try_cast(nullif(trim(customer_id), '') as integer) as customer_id,
        {{ parse_date('order_date') }}                    as order_date,
        trim(billing_country)                             as billing_country_raw,
        {{ parse_money('total') }}                        as total,
        order_date                                        as order_date_raw,
        loaded_at
    from ranked
    where rn = 1
)

select
    c.* exclude (billing_country_raw),
    coalesce(a.canonical, {{ title_case("c.billing_country_raw") }}) as billing_country,
    case
        when c.customer_id is null          then 'missing_customer'
        when c.order_date is null           then 'unparseable_date'
        when c.order_date > current_date    then 'future_date'
        when c.total is null                then 'missing_total'
    end as reject_reason
from cleaned c
left join {{ ref('country_aliases') }} a on a.alias = lower(c.billing_country_raw)
