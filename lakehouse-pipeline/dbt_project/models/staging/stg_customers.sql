select
    cast(c.customer_id as integer)                                  as customer_id,
    trim(c.first_name)                                              as first_name,
    trim(c.last_name)                                               as last_name,
    trim(c.city)                                                    as city,
    coalesce(a.canonical, {{ title_case("c.country") }})                 as country
from {{ source('raw', 'customers') }} c
left join {{ ref('country_aliases') }} a on a.alias = lower(trim(c.country))
