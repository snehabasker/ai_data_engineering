select line_id, order_id, track_id, unit_price, quantity, 'unknown_track' as reject_reason
from {{ ref('stg_order_lines') }}
where is_orphan_track
