select d.year_month, f.billing_country,
       sum(f.revenue) as revenue, sum(f.quantity) as units, count(distinct f.order_id) as orders
from {{ ref('fct_sales') }} f
join {{ ref('dim_date') }} d using (date_key)
group by 1, 2
