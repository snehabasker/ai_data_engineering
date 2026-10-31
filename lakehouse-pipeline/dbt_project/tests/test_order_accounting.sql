-- Every distinct raw order id must land in exactly one of: accepted (stg_orders) or quarantine. Returns rows on failure.
with raw_ids as (select distinct cast(order_id as integer) as order_id from {{ source('raw', 'orders') }}),
landed as (
    select order_id from {{ ref('stg_orders') }}
    union all
    select order_id from {{ ref('quarantine_orders') }}
)
select r.order_id, count(l.order_id) as times_landed
from raw_ids r left join landed l using (order_id)
group by 1
having count(l.order_id) <> 1
