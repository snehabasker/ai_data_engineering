-- All lines of accepted orders. Lines whose track is unknown are kept here (so order totals still reconcile)
-- and flagged; the fact table excludes them and quarantine_order_lines reports them.
select
    cast(l.line_id as integer)                as line_id,
    cast(l.order_id as integer)               as order_id,
    cast(l.track_id as integer)               as track_id,
    {{ parse_money('l.unit_price') }}         as unit_price,
    cast(l.quantity as integer)               as quantity,
    t.track_id is null                        as is_orphan_track
from {{ source('raw', 'order_lines') }} l
join {{ ref('stg_orders') }} o on o.order_id = cast(l.order_id as integer)
left join {{ ref('stg_tracks') }} t on t.track_id = try_cast(l.track_id as integer)
