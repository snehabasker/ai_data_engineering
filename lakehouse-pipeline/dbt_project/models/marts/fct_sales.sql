-- Grain: one row per order line of an accepted order whose track is known.
select
    l.line_id,
    l.order_id,
    o.customer_id                                  as customer_key,
    l.track_id                                     as track_key,
    cast(strftime(o.order_date, '%Y%m%d') as integer) as date_key,
    o.billing_country,
    l.quantity,
    l.unit_price,
    l.quantity * l.unit_price                      as revenue
from {{ ref('stg_order_lines') }} l
join {{ ref('stg_orders') }} o using (order_id)
where not l.is_orphan_track
