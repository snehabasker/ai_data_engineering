-- Rejected orders, kept with the reason and the raw date string for triage / replay.
select order_id, customer_id, order_date_raw, total, billing_country, reject_reason, loaded_at
from {{ ref('orders_validated') }}
where reject_reason is not null
