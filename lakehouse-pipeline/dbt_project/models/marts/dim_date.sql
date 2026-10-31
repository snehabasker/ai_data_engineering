-- Calendar spanning the accepted orders, padded to whole years.
with bounds as (
    select make_date(year(min(order_date)), 1, 1) as d0, make_date(year(max(order_date)), 12, 31) as d1
    from {{ ref('stg_orders') }}
)
select
    cast(strftime(d, '%Y%m%d') as integer) as date_key,
    d                                      as date_day,
    year(d)                                as year,
    quarter(d)                             as quarter,
    month(d)                               as month,
    strftime(d, '%Y-%m')                   as year_month,
    dayofweek(d) in (0, 6)                 as is_weekend
from bounds, unnest(generate_series(d0, d1, interval 1 day)) as t(d)
