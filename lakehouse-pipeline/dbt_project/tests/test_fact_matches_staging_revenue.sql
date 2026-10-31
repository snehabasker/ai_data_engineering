-- Fact revenue + quarantined-line revenue must equal staged line revenue (nothing lost or invented between layers).
with s as (select sum(unit_price * quantity) as v from {{ ref('stg_order_lines') }}),
     f as (select sum(revenue) as v from {{ ref('fct_sales') }}),
     q as (select coalesce(sum(unit_price * quantity), 0) as v from {{ ref('quarantine_order_lines') }})
select s.v as staged, f.v as fact, q.v as quarantined
from s, f, q
where abs(s.v - (f.v + q.v)) > 0.005
