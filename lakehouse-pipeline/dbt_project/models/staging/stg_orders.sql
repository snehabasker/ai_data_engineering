select order_id, customer_id, order_date, billing_country, total, loaded_at
from {{ ref('orders_validated') }}
where reject_reason is null
