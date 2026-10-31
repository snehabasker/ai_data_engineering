select customer_id as customer_key, first_name, last_name, first_name || ' ' || last_name as full_name, city, country
from {{ ref('stg_customers') }}
