-- The cleaned order total must equal the sum of its cleaned lines (incl. orphan-track lines). Catches parsing bugs
-- in either money column. Returns rows on failure.
select o.order_id, o.total, sum(l.unit_price * l.quantity) as lines_total
from {{ ref('stg_orders') }} o
join {{ ref('stg_order_lines') }} l using (order_id)
group by 1, 2
having abs(o.total - sum(l.unit_price * l.quantity)) > 0.005
